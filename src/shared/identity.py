"""Harness-asserted agent identity (M4, ISO-01/ISO-13/ISO-14/ISO-15).

Identity is a property of the SERVER PROCESS, bound at boot from harness
credentials — never of each tool call. A bound server acts only within its
own scope or `shared`; caller-supplied foreign scopes are rejected BEFORE any
I/O. This converts M1-M3's advisory isolation into enforced isolation.

Modes:
- "strict": boot REQUIRES valid MEMORY_AGENT_ID + MEMORY_AGENT_TOKEN against
  the registry; anything else raises IdentityError and no tools are registered
  (fail-closed boot).
- "open" (default while single-agent): no credentials → identity.mode="open",
  WARN logged; scope parameters remain shape-validated (M3 behavior). If full
  credentials are present they are verified and bind silently.

Default-coercion policy (ISO-15, bound mode): caller `agent_id="default"`
(the legacy MCP default) coerces to the bound scope; `shared` stays public;
any other foreign scope raises ScopeError. Tokens: secrets.token_urlsafe(32),
shown exactly once at registration, stored ONLY as SHA-256, verified with
hmac.compare_digest (constant-time), never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .scope import PUBLIC_SCOPE, ScopeError, normalize_scope

logger = logging.getLogger(__name__)

IDENTITY_MODE_ENV = "MEMORY_IDENTITY_MODE"
AGENT_ID_ENV = "MEMORY_AGENT_ID"
AGENT_TOKEN_ENV = "MEMORY_AGENT_TOKEN"
_VALID_MODES = {"open", "strict"}


class IdentityError(RuntimeError):
    """Raised at boot when strict-mode credentials are missing or invalid."""


def _default_registry_path() -> str:
    base = os.getenv("MEMORY_SERVER_DIR", os.path.expanduser("~/.memory"))
    data_dir = os.getenv("DATA_DIR", os.path.join(base, "data"))
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "agents.json")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AgentRegistry:
    """agent_id -> {token_sha256, created_at}. Plaintext tokens never stored."""

    def __init__(self, path: str | None = None):
        self.path = path or _default_registry_path()
        self._entries: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                # ValueError not TypeError: corrupt registry is caller-shaped
                # input state, same family as ScopeError (ValueError).
                raise ValueError("registry root must be an object")  # noqa: TRY004
            return data
        except (json.JSONDecodeError, ValueError, OSError) as e:
            # Corrupt registry: empty + WARN — boot in open mode must survive;
            # strict mode will fail closed right after (verify finds nothing).
            logger.warning("identity: corrupt agents.json (%s) — starting empty", e)
            return {}

    def _save(self) -> None:
        d = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".agents-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._entries, fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600 before rename
            os.replace(tmp, self.path)
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def register(self, agent_id: str, token: str | None = None) -> str:
        """Create/rotate an agent credential. Returns the plaintext token ONCE."""
        aid = normalize_scope(agent_id)
        if aid == PUBLIC_SCOPE:
            raise ScopeError("the shared scope is public and cannot hold credentials")
        token = token or secrets.token_urlsafe(32)
        self._entries[aid] = {
            "token_sha256": _token_hash(token),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._save()
        return token

    def verify(self, agent_id: str, token: str) -> bool:
        aid = normalize_scope(agent_id)
        entry = self._entries.get(aid)
        if not entry or not isinstance(token, str):
            return False
        expected = entry.get("token_sha256", "")
        return hmac.compare_digest(expected, _token_hash(token))

    def list_agents(self) -> dict[str, dict[str, Any]]:
        return {aid: {"created_at": e.get("created_at")} for aid, e in sorted(self._entries.items())}


@dataclass(frozen=True)
class Identity:
    agent_id: str  # canonical own scope
    mode: str      # "bound" | "open"

    def assert_agent(self, requested: str) -> str:
        """Resolve the effective scope for one tool call (ISO-13/ISO-15).

        bound: "default" coerces to the bound scope (legacy MCP default),
        "shared" stays public, anything foreign raises ScopeError BEFORE I/O.
        open: shape-validation only (legacy behavior, mode is observable).
        """
        normalized = normalize_scope(requested)
        if self.mode != "bound":
            return normalized
        if normalized == "default":
            logger.debug("identity: default coerced to bound scope %s", self.agent_id)
            return self.agent_id
        if normalized == PUBLIC_SCOPE or normalized == self.agent_id:
            return normalized
        raise ScopeError(
            f"identity-bound as {self.agent_id!r}: cannot act as {normalized!r} (ISO-13)"
        )

    def as_dict(self) -> dict[str, str]:
        return {"agent_id": self.agent_id, "mode": self.mode}


def bind_identity(env: dict[str, str] | None = None, registry: AgentRegistry | None = None) -> Identity:
    """Bind server identity at boot. strict failures raise IdentityError (fail-closed)."""
    env = dict(os.environ if env is None else env)
    mode = (env.get(IDENTITY_MODE_ENV) or "open").strip().lower()
    if mode not in _VALID_MODES:
        raise IdentityError(f"invalid {IDENTITY_MODE_ENV}={mode!r} (want open|strict)")

    agent_id = env.get(AGENT_ID_ENV) or ""
    token = env.get(AGENT_TOKEN_ENV) or ""
    reg = registry or AgentRegistry()

    if agent_id or token:
        if not agent_id or not token:
            raise IdentityError("partial identity credentials: both MEMORY_AGENT_ID and MEMORY_AGENT_TOKEN are required")
        if not reg.verify(agent_id, token):
            raise IdentityError(f"identity verification failed for agent {agent_id!r}")
        aid = normalize_scope(agent_id)
        logger.info("identity: BOUND to scope %r (credentials verified)", aid)
        return Identity(agent_id=aid, mode="bound")

    if mode == "strict":
        raise IdentityError(
            f"strict mode requires {AGENT_ID_ENV} + {AGENT_TOKEN_ENV} (fail-closed boot, ISO-14)"
        )

    logger.warning(
        "identity: OPEN mode — scopes are shape-validated but NOT bound to a "
        "verified agent (ISO-01 legacy). Register credentials and set %s=strict.",
        IDENTITY_MODE_ENV,
    )
    return Identity(agent_id=PUBLIC_SCOPE, mode="open")
