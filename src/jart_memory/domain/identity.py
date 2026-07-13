"""Identity values and invariants for the Jart Memory domain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import RFC_4122, UUID


_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_CAPABILITY = re.compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")


class DomainValidationError(ValueError):
    """Raised when a domain value violates a construction invariant."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


class IdentityInactiveError(PermissionError):
    """Raised when identity is evaluated outside its active validity window."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PrincipalKind(StrEnum):
    """Authenticated principal categories understood by the memory core."""

    USER = "user"
    AGENT = "agent"
    SERVICE = "service"


class MemoryScope(StrEnum):
    """Canonical memory visibility scopes."""

    SESSION_PRIVATE = "session_private"
    AGENT_PRIVATE = "agent_private"
    TEAM_PRIVATE = "team_private"
    DOMAIN_CONTROLLED = "domain_controlled"
    TENANT_CONTROLLED = "tenant_controlled"
    GLOBAL_GOLDEN = "global_golden"
    EXTERNAL_RAG = "external_rag"


def _require_uuid7(field: str, value: UUID | None) -> None:
    if not isinstance(value, UUID) or value.version != 7 or value.variant != RFC_4122:
        raise DomainValidationError("invalid_uuid7", f"{field} must be an RFC 4122 UUIDv7")


def _require_optional_uuid7(field: str, value: UUID | None) -> None:
    if value is not None:
        _require_uuid7(field, value)


def _require_utc(field: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise DomainValidationError("invalid_utc_time", f"{field} must be timezone-aware UTC")


def _require_semantic_version(field: str, value: str) -> None:
    if not isinstance(value, str) or _SEMANTIC_VERSION.fullmatch(value) is None:
        raise DomainValidationError("invalid_semantic_version", f"{field} must be a semantic version")


@dataclass(frozen=True, slots=True)
class IdentityContext:
    """Verified immutable authority presented to Jart Memory use cases."""

    schema_version: str
    context_id: UUID
    territory_id: UUID
    tenant_id: UUID
    principal_kind: PrincipalKind
    principal_id: UUID
    user_id: UUID | None
    agent_definition_id: UUID | None
    agent_instance_id: UUID | None
    domain_id: UUID | None
    team_id: UUID | None
    session_id: UUID
    task_id: UUID
    plaza_id: UUID
    credential_version: int
    policy_version: str
    purpose: str
    scope_ceiling: MemoryScope
    capabilities: frozenset[str]
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_semantic_version("schema_version", self.schema_version)
        _require_semantic_version("policy_version", self.policy_version)

        for field in (
            "context_id",
            "territory_id",
            "tenant_id",
            "principal_id",
            "session_id",
            "task_id",
            "plaza_id",
        ):
            _require_uuid7(field, getattr(self, field))

        for field in ("user_id", "agent_definition_id", "agent_instance_id", "domain_id", "team_id"):
            _require_optional_uuid7(field, getattr(self, field))

        if not isinstance(self.principal_kind, PrincipalKind):
            raise DomainValidationError("invalid_principal_kind", "principal_kind is not supported")
        if not isinstance(self.scope_ceiling, MemoryScope):
            raise DomainValidationError("invalid_scope", "scope_ceiling is not supported")

        if self.principal_kind is PrincipalKind.AGENT:
            for field in ("user_id", "agent_definition_id", "agent_instance_id"):
                if getattr(self, field) is None:
                    raise DomainValidationError("missing_agent_identity", f"{field} is required for agent principals")
        elif self.principal_kind is PrincipalKind.USER and self.user_id is None:
            raise DomainValidationError("missing_user_identity", "user_id is required for user principals")

        if (
            not isinstance(self.credential_version, int)
            or isinstance(self.credential_version, bool)
            or self.credential_version < 1
        ):
            raise DomainValidationError("invalid_credential_version", "credential_version must be a positive integer")
        if not isinstance(self.purpose, str) or not self.purpose.strip():
            raise DomainValidationError("missing_purpose", "purpose must not be empty")

        capabilities = frozenset(self.capabilities)
        if not capabilities:
            raise DomainValidationError("missing_capabilities", "at least one capability is required")
        invalid_capabilities = sorted(
            capability for capability in capabilities if _CAPABILITY.fullmatch(capability) is None
        )
        if invalid_capabilities:
            raise DomainValidationError("invalid_capability", "capabilities must use resource:action names")
        object.__setattr__(self, "capabilities", capabilities)

        _require_utc("issued_at", self.issued_at)
        _require_utc("expires_at", self.expires_at)
        if self.expires_at <= self.issued_at:
            raise DomainValidationError("invalid_validity_interval", "expires_at must be later than issued_at")

    def assert_active(self, at: datetime) -> IdentityContext:
        """Return this context when active, otherwise raise a typed denial."""

        _require_utc("at", at)
        if at < self.issued_at:
            raise IdentityInactiveError("not_yet_active")
        if at >= self.expires_at:
            raise IdentityInactiveError("expired")
        return self
