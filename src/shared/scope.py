"""Canonical tenant scope handling (M1-lite, ISO-09/ISO-10).

Single source of truth for scope validation and namespace directory layout.
No I/O, no dependencies beyond stdlib — safe to import anywhere.

Scope model: ONE validated segment (e.g. "director-1", "default", "shared")
or the full M2 5-level namespace `c:x/p:y/a:z/s:w/u:v` (levels optional,
order fixed, each segment validated). Filesystem browsable stores remain
single-segment in M2; opaque/hashed stores hash the canonical form.

Security properties:
- `normalize_scope` rejects empty, overlong, reserved, traversal, glob and
  non-matching inputs with `ScopeError`. Callers fail closed (no fallback).
- `scope_dir_hashed` never embeds caller text in paths (sha256 hex only).
- `scope_subdir` embeds ONLY `normalize_scope` output, which cannot contain
  `/`, `..` or glob chars by construction (regex-enforced).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


class ScopeError(ValueError):
    """Raised when a scope string is invalid, reserved, or unsafe."""


_SCOPE_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_MAX_SCOPE_LEN = 32

# M2: 5-level namespace levels, in mandatory order (each optional, no repeats).
_SCOPE_LEVELS = ("c", "p", "a", "s", "u")
_SCOPE_LEVEL_RE = re.compile(r"^([cpasu]):([a-z0-9][a-z0-9_-]{0,31})$")
_MAX_CANONICAL_LEN = 5 * (_MAX_SCOPE_LEN + 3)  # "c:" + 32 + "/" per level

# Names that must never be usable as a *private* scope. "shared" is the
# legitimate public scope, NOT a bypass — it is readable by every tenant
# by design and must never hold private data.
RESERVED_SCOPES = frozenset({"global", "merged", "consolidated", "narrative", "dream"})

PUBLIC_SCOPE = "shared"

# Default when a caller omits scope. Explicit and documented; M4 replaces
# caller-supplied identity with harness-asserted identity (then this default
# is only a fallback for local/manual use, never for cross-tenant reads).
DEFAULT_SCOPE = "shared"

_SCOPES_DIRNAME = "_scopes"


def normalize_scope(scope: str) -> str:
    """Validate and canonicalize a scope string.

    Accepts ONE segment ("director-1") or the M2 5-level namespace
    ("c:acme/p:memory/a:director-1"). Returns the canonical form:
    single segments are stripped+lowercased; multi-level scopes are
    canonically ordered c<p<a<s<u with each segment validated.
    Raises ScopeError on anything invalid. Never returns a fallback.
    """
    if not isinstance(scope, str):
        raise ScopeError(f"scope must be str, got {type(scope).__name__}")
    s = scope.strip().lower()
    if not s:
        raise ScopeError("empty scope")
    if ":" in s:
        return _normalize_namespaced(s)
    if len(s) > _MAX_SCOPE_LEN:
        raise ScopeError(f"scope too long ({len(s)} > {_MAX_SCOPE_LEN})")
    if s in RESERVED_SCOPES:
        raise ScopeError(f"reserved scope: {s!r}")
    if not _SCOPE_SEGMENT_RE.match(s):
        raise ScopeError(f"invalid scope (must match {_SCOPE_SEGMENT_RE.pattern}): {s!r}")
    return s


def _normalize_namespaced(s: str) -> str:
    """Canonicalize `c:x/p:y/...` form: fixed order, no repeats, valid segments."""
    if len(s) > _MAX_CANONICAL_LEN:
        raise ScopeError(f"scope too long ({len(s)} > {_MAX_CANONICAL_LEN})")
    seen: dict[str, str] = {}
    for part in s.split("/"):
        m = _SCOPE_LEVEL_RE.match(part.strip())
        if not m:
            raise ScopeError(f"invalid namespace level (want c:/p:/a:/s:/u:): {part!r}")
        level, segment = m.group(1), m.group(2)
        if level in seen:
            raise ScopeError(f"duplicate namespace level: {level}:")
        if segment in RESERVED_SCOPES:
            raise ScopeError(f"reserved scope segment: {segment!r}")
        seen[level] = segment
    if not seen:
        raise ScopeError("empty namespaced scope")
    return "/".join(f"{lvl}:{seen[lvl]}" for lvl in _SCOPE_LEVELS if lvl in seen)


def scope_jail_path(base: Path, scope: str, rel: str | Path) -> Path:
    """Resolve `rel` inside the scope's jailed directory — fail-closed (ISO-07).

    Raises ScopeError BEFORE any filesystem access when `rel` traverses out
    (../..), is absolute, or escapes via an existing symlink. Returns the
    fully-resolved path callers MUST use for the actual write/read.
    """
    s = normalize_scope(scope)
    if isinstance(rel, str):
        rel = Path(rel)
    jail = scope_subdir(base, s)
    candidate = (jail / rel).resolve()
    return assert_contained(candidate, jail)


def scope_dir_hashed(base: Path, scope: str) -> Path:
    """Namespace directory for OPAQUE stores (reminders, sessions).

    Directory name is `sha256(scope)[:16]` — caller text never touches the
    filesystem, so traversal is impossible by construction.
    """
    s = normalize_scope(scope)
    digest = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    return base / digest


def scope_subdir(base: Path, scope: str, prefix: str = _SCOPES_DIRNAME) -> Path:
    """Namespace directory for HUMAN-BROWSABLE stores (decisions, vault).

    Uses the normalized scope as directory name. Safe: `normalize_scope`
    output cannot contain `/`, `..`, or glob characters for single segments
    (regex-enforced). M2: multi-level scopes are REJECTED here — browsable
    filesystem stores stay single-segment; hashed stores take any scope.
    """
    s = normalize_scope(scope)
    if ":" in s:
        raise ScopeError(
            "multi-level scopes cannot map to browsable directories; "
            "use scope_dir_hashed (M2 contract)"
        )
    if s == PUBLIC_SCOPE:
        return base
    return base / prefix / s


def visible_dirs_hashed(base: Path, scope: str) -> list[Path]:
    """Directories a scope may read (opaque stores): own + shared. Never siblings."""
    s = normalize_scope(scope)
    dirs = [scope_dir_hashed(base, s)]
    if s != PUBLIC_SCOPE:
        dirs.append(scope_dir_hashed(base, PUBLIC_SCOPE))
    return dirs


def assert_contained(path: Path, jail: Path) -> Path:
    """Fail-closed containment check. Returns resolved path or raises ScopeError."""
    resolved = path.resolve()
    jail_resolved = jail.resolve()
    try:
        resolved.relative_to(jail_resolved)
    except ValueError:
        raise ScopeError(f"path escapes jail: {path}")
    return resolved


def iter_namespaced_files(root: Path, scope: str, pattern: str = "*.md") -> list[Path]:
    """Files visible to `scope`: shared tree (excluding `_scopes/`) + own scope dir.

    Shared area is everything under root EXCEPT the `_scopes` subtree, so
    private namespaces never leak into public reads and vice versa.
    """
    s = normalize_scope(scope)
    out: list[Path] = []
    if root.is_dir():
        for f in sorted(root.rglob(pattern)):
            try:
                rel = f.relative_to(root)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] == _SCOPES_DIRNAME:
                continue
            if f.is_file():
                out.append(f)
    if s != PUBLIC_SCOPE:
        own = scope_subdir(root, s)
        if own.is_dir():
            out.extend(sorted(p for p in own.rglob(pattern) if p.is_file()))
    return out
