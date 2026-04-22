"""Diff Sandbox — isolated change management with syntax validation.

Inspired by Plandex's build-validate-fix loop.
Does NOT touch project files until explicitly approved.

Tracks every proposed/accepted/rejected/applied change for autoaprendizaje.

Zero new dependencies: uses git diff (subprocess) + Pygments (installed).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from pygments import lex
from pygments.lexers import get_lexer_by_name, get_lexer_for_filename, ClassNotFound
from pygments.token import Token


# ── Models ────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    """Result of validating a proposed change."""
    valid: bool
    syntax_ok: bool = True
    compliance_ok: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DiffChange(BaseModel):
    """A proposed change to a file."""
    change_id: str = Field(default_factory=lambda: hashlib.sha256(
        f"{time.time()}-{os.urandom(4).hex()}".encode()
    ).hexdigest()[:16])
    file_path: str
    original_sha: str = ""
    proposed_sha: str = ""
    diff_text: str = ""
    original_content: str = ""
    proposed_content: str = ""
    language: str = ""
    status: str = "proposed"  # proposed | accepted | rejected | applied | failed
    validation: Optional[ValidationResult] = None
    reject_reason: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolved_at: Optional[str] = None


# ── Syntax Validation ─────────────────────────────────────────────

def validate_syntax(content: str, language: str = "",
                    file_path: str = "") -> tuple[bool, list[str]]:
    """Validate syntax using Pygments lexer.

    Strategy: Pygments tokenizes the content. If it produces error tokens,
    the syntax is likely broken. This is NOT a full parser — it catches
    ~70-80% of syntax errors without needing tree-sitter.

    Args:
        content: Source code to validate.
        language: Programming language name.
        file_path: File path (used to detect language if language is empty).

    Returns:
        (is_valid, error_messages)
    """
    if not content.strip():
        return (True, [])

    lexer = None
    try:
        if language:
            lexer = get_lexer_by_name(language)
        elif file_path:
            lexer = get_lexer_for_filename(file_path, content)
    except ClassNotFound:
        pass

    if lexer is None:
        # Can't validate without a lexer — assume OK
        return (True, [])

    try:
        tokens = list(lex(content, lexer))
    except Exception:
        # Lexer crash = probably bad syntax
        return (False, ["Lexer failed to tokenize — possible syntax error"])

    errors: list[str] = []
    for token_type, token_value in tokens:
        # Check for error tokens
        type_str = str(token_type)
        if "Error" in type_str:
            errors.append(f"Syntax error near: {token_value[:80]}")
        elif token_type in Token.Error:
            errors.append(f"Syntax error near: {token_value[:80]}")

    return (len(errors) == 0, errors)


# ── Diff Generation ───────────────────────────────────────────────

def generate_diff(original: str, proposed: str,
                  file_path: str = "file") -> str:
    """Generate unified diff between original and proposed content.

    Uses git diff --no-index (subprocess, ~10ms).
    Fallback to simple line diff if git not available.
    """
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".orig", delete=False) as f1:
            f1.write(original)
            f1_path = f1.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".new", delete=False) as f2:
            f2.write(proposed)
            f2_path = f2.name

        try:
            result = subprocess.run(
                ["git", "diff", "--no-color", "--no-index", f1_path, f2_path],
                capture_output=True, text=True, timeout=5,
            )
            # git diff exits with 1 when there are differences (expected)
            diff_text = result.stdout
            # Replace temp file names with actual file path
            diff_text = diff_text.replace(f1_path, f"a/{file_path}")
            diff_text = diff_text.replace(f2_path, f"b/{file_path}")
            return diff_text
        finally:
            os.unlink(f1_path)
            os.unlink(f2_path)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Fallback: simple line-by-line diff
        return _simple_diff(original, proposed, file_path)


def _simple_diff(original: str, proposed: str, file_path: str) -> str:
    """Simple line-by-line diff fallback when git is not available."""
    orig_lines = original.splitlines(keepends=True)
    new_lines = proposed.splitlines(keepends=True)

    import difflib
    diff = difflib.unified_diff(
        orig_lines, new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)


# ── SHA Helper ────────────────────────────────────────────────────

def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]


def _detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript",
        ".go": "go", ".rs": "rust", ".java": "java",
        ".rb": "ruby", ".php": "php", ".swift": "swift",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
        ".sh": "bash", ".bash": "bash",
        ".sql": "sql", ".html": "html", ".css": "css",
    }
    return ext_map.get(Path(file_path).suffix.lower(), "")


# ── DiffSandbox ───────────────────────────────────────────────────

class DiffSandbox:
    """Isolated change sandbox for a project.

    Changes are proposed, validated, and tracked without touching
    the filesystem until explicitly approved and applied.

    Usage:
        sandbox = DiffSandbox("/path/to/project")
        change = sandbox.propose("src/main.py", new_content)
        if change.validation.syntax_ok:
            sandbox.accept(change.change_id)
            sandbox.apply(change.change_id)
    """

    def __init__(self, project_root: str, staging_dir: str = ""):
        self.project_root = Path(project_root).resolve()
        if staging_dir:
            self._staging_dir = Path(staging_dir)
        else:
            self._staging_dir = self.project_root / "data" / "staging_buffer"
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, file_path: str) -> Path:
        """Resolve file path relative to project root."""
        p = Path(file_path)
        if p.is_absolute():
            return p
        return self.project_root / file_path

    def _staging_path(self, change_id: str) -> Path:
        return self._staging_dir / f"{change_id}.json"

    def _save(self, change: DiffChange) -> None:
        """Persist change to staging dir."""
        path = self._staging_path(change.change_id)
        path.write_text(change.model_dump_json(indent=2))

    def _load(self, change_id: str) -> DiffChange | None:
        """Load change from staging dir."""
        path = self._staging_path(change_id)
        if not path.exists():
            return None
        return DiffChange.model_validate_json(path.read_text())

    # ── Public API ────────────────────────────────────────────────

    def propose(
        self,
        file_path: str,
        new_content: str,
        language: str = "",
        metadata: dict | None = None,
    ) -> DiffChange:
        """Propose a change to a file.

        Does NOT touch the filesystem. Returns a DiffChange with:
          - diff_text: unified diff
          - validation: syntax check result
          - status: "proposed"

        Args:
            file_path: File to change (relative to project root).
            new_content: The proposed new content.
            language: Source language (auto-detected if empty).
            metadata: Arbitrary metadata for tracking.
        """
        resolved = self._resolve(file_path)
        rel_path = str(resolved.relative_to(self.project_root))

        # Read original
        original = ""
        original_sha = ""
        if resolved.exists():
            try:
                original = resolved.read_text(encoding="utf-8", errors="replace")
                original_sha = _sha(original)
            except OSError:
                pass

        lang = language or _detect_language(rel_path)
        proposed_sha = _sha(new_content)

        # Skip if no actual change
        if original_sha == proposed_sha:
            return DiffChange(
                file_path=rel_path,
                original_sha=original_sha,
                proposed_sha=proposed_sha,
                language=lang,
                status="rejected",
                reject_reason="No changes detected (identical content)",
                metadata=metadata or {},
            )

        # Generate diff
        diff_text = generate_diff(original, new_content, rel_path)

        # Validate syntax
        syntax_ok, syntax_errors = validate_syntax(new_content, lang, rel_path)

        validation = ValidationResult(
            valid=syntax_ok,
            syntax_ok=syntax_ok,
            compliance_ok=True,  # Compliance checked separately
            errors=syntax_errors,
        )

        change = DiffChange(
            file_path=rel_path,
            original_sha=original_sha,
            proposed_sha=proposed_sha,
            diff_text=diff_text,
            original_content=original,
            proposed_content=new_content,
            language=lang,
            status="proposed",
            validation=validation,
            metadata=metadata or {},
        )

        self._save(change)
        return change

    def accept(self, change_id: str) -> DiffChange | None:
        """Mark a proposed change as accepted (ready to apply).

        Returns updated DiffChange or None if not found.
        """
        change = self._load(change_id)
        if change is None:
            return None
        if change.status != "proposed":
            return change  # Already resolved

        change.status = "accepted"
        change.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save(change)
        return change

    def reject(self, change_id: str, reason: str = "") -> DiffChange | None:
        """Mark a proposed change as rejected.

        The diff is preserved for autoaprendizaje (anti-patterns).
        """
        change = self._load(change_id)
        if change is None:
            return None
        if change.status in ("applied", "failed"):
            return change  # Can't reject applied changes

        change.status = "rejected"
        change.reject_reason = reason
        change.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save(change)
        return change

    def apply(self, change_id: str) -> DiffChange | None:
        """Apply an accepted change to the filesystem.

        Only works if status="accepted". Writes the proposed content
        to the target file and marks as "applied".

        Returns updated DiffChange or None if not found/not accepted.
        """
        change = self._load(change_id)
        if change is None:
            return None
        if change.status != "accepted":
            return change

        target = self._resolve(change.file_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.proposed_content, encoding="utf-8")
            change.status = "applied"
        except OSError as e:
            change.status = "failed"
            if change.validation:
                change.validation.errors.append(f"Write failed: {e}")
            else:
                change.validation = ValidationResult(
                    valid=False, errors=[f"Write failed: {e}"]
                )

        change.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save(change)
        return change

    def apply_all_accepted(self) -> list[DiffChange]:
        """Apply all changes with status="accepted"."""
        applied = []
        for change in self.get_pending():
            if change.status == "accepted":
                result = self.apply(change.change_id)
                if result:
                    applied.append(result)
        return applied

    def get_pending(self) -> list[DiffChange]:
        """Return all changes with status='proposed' or 'accepted'."""
        pending = []
        for f in self._staging_dir.glob("*.json"):
            try:
                change = DiffChange.model_validate_json(f.read_text())
                if change.status in ("proposed", "accepted"):
                    pending.append(change)
            except Exception:
                pass
        return sorted(pending, key=lambda c: c.created_at)

    def get_history(self, file_path: str = "", limit: int = 50) -> list[DiffChange]:
        """Get change history, optionally filtered by file_path.

        Returns changes sorted by creation time (newest first).
        """
        history = []
        for f in self._staging_dir.glob("*.json"):
            try:
                change = DiffChange.model_validate_json(f.read_text())
                if file_path and change.file_path != file_path:
                    continue
                history.append(change)
            except Exception:
                pass
        history.sort(key=lambda c: c.created_at, reverse=True)
        return history[:limit]

    def cleanup(self, older_than_hours: int = 168) -> int:
        """Remove resolved changes older than N hours.

        Keeps proposed/accepted changes (they may still be needed).
        Default: 168 hours = 7 days.

        Returns count of removed changes.
        """
        now = datetime.now(timezone.utc)
        removed = 0

        for f in self._staging_dir.glob("*.json"):
            try:
                change = DiffChange.model_validate_json(f.read_text())
                if change.status in ("proposed", "accepted"):
                    continue  # Don't remove pending

                if change.resolved_at:
                    resolved = datetime.fromisoformat(change.resolved_at)
                    age_hours = (now - resolved).total_seconds() / 3600
                    if age_hours > older_than_hours:
                        f.unlink()
                        removed += 1
            except Exception:
                pass

        return removed

    def validate(self, change_id: str) -> DiffChange | None:
        """Re-validate a proposed change.

        Runs syntax validation again on the proposed content.
        """
        change = self._load(change_id)
        if change is None:
            return None

        syntax_ok, syntax_errors = validate_syntax(
            change.proposed_content, change.language, change.file_path
        )
        change.validation = ValidationResult(
            valid=syntax_ok,
            syntax_ok=syntax_ok,
            compliance_ok=True,
            errors=syntax_errors,
        )
        self._save(change)
        return change
