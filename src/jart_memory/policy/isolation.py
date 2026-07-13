"""Deny-by-default policy for the initial private memory scopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from jart_memory.domain.identity import IdentityContext, IdentityInactiveError, MemoryScope


class AccessDecision(StrEnum):
    """Explicit outcomes returned by the isolation policy."""

    PERMITTED = "permitted"


class MemoryAccessDenied(PermissionError):
    """Typed non-disclosing denial for every failed authorization check."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MemoryOwner:
    """Verified ownership coordinates for a memory scope."""

    scope: MemoryScope
    territory_id: UUID
    tenant_id: UUID
    user_id: UUID | None
    agent_instance_id: UUID | None
    session_id: UUID | None
    task_id: UUID | None


class IsolationPolicy:
    """Authorize only the explicitly supported private ownership scopes."""

    _SUPPORTED_SCOPES = frozenset({MemoryScope.SESSION_PRIVATE, MemoryScope.AGENT_PRIVATE})
    _SCOPE_LEVEL = {MemoryScope.SESSION_PRIVATE: 0, MemoryScope.AGENT_PRIVATE: 1}

    def authorize(
        self,
        context: IdentityContext,
        owner: MemoryOwner,
        *,
        required_capability: str,
        at: datetime,
    ) -> AccessDecision:
        """Return permit only when every private-scope predicate is satisfied."""

        try:
            context.assert_active(at)
        except IdentityInactiveError as error:
            raise MemoryAccessDenied("identity_inactive") from error

        if owner.scope not in self._SUPPORTED_SCOPES:
            raise MemoryAccessDenied("unsupported_scope")
        if not isinstance(required_capability, str) or required_capability not in context.capabilities:
            raise MemoryAccessDenied("missing_capability")
        if (
            context.scope_ceiling in self._SCOPE_LEVEL
            and self._SCOPE_LEVEL[owner.scope] > self._SCOPE_LEVEL[context.scope_ceiling]
        ):
            raise MemoryAccessDenied("scope_ceiling_exceeded")

        if owner.territory_id != context.territory_id or owner.tenant_id != context.tenant_id:
            raise MemoryAccessDenied("memory_access_denied")
        if owner.user_id != context.user_id or owner.agent_instance_id != context.agent_instance_id:
            raise MemoryAccessDenied("memory_access_denied")
        if owner.scope is MemoryScope.SESSION_PRIVATE and (
            owner.session_id != context.session_id or owner.task_id != context.task_id
        ):
            raise MemoryAccessDenied("memory_access_denied")
        return AccessDecision.PERMITTED
