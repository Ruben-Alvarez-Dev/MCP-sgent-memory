"""Deny-by-default memory isolation tests with sanitized TEST-ONLY values."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from jart_memory.domain.identity import IdentityContext, MemoryScope, PrincipalKind
from jart_memory.policy.isolation import (
    AccessDecision,
    IsolationPolicy,
    MemoryAccessDenied,
    MemoryOwner,
)


TEST_ONLY_NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def _uuid7(number: int) -> UUID:
    """Return a deterministic UUIDv7 reserved exclusively for tests."""
    return UUID(f"018f0d6e-7a69-7{number:03x}-8000-{number:012x}")


def valid_agent_context(**overrides: object) -> IdentityContext:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "context_id": _uuid7(1),
        "territory_id": _uuid7(2),
        "tenant_id": _uuid7(3),
        "principal_kind": PrincipalKind.AGENT,
        "principal_id": _uuid7(4),
        "user_id": _uuid7(5),
        "agent_definition_id": _uuid7(6),
        "agent_instance_id": _uuid7(7),
        "domain_id": _uuid7(8),
        "team_id": _uuid7(9),
        "session_id": _uuid7(10),
        "task_id": _uuid7(11),
        "plaza_id": _uuid7(12),
        "credential_version": 1,
        "policy_version": "1.0.0",
        "purpose": "isolation-policy-test",
        "scope_ceiling": MemoryScope.AGENT_PRIVATE,
        "capabilities": frozenset({"memory:capture", "memory:search"}),
        "issued_at": TEST_ONLY_NOW,
        "expires_at": TEST_ONLY_NOW + timedelta(minutes=5),
    }
    values.update(overrides)
    return IdentityContext(**values)


def owner(context: IdentityContext | None = None, **overrides: object) -> MemoryOwner:
    context = context or valid_agent_context()
    values: dict[str, object] = {
        "scope": MemoryScope.SESSION_PRIVATE,
        "territory_id": context.territory_id,
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "agent_instance_id": context.agent_instance_id,
        "session_id": context.session_id,
        "task_id": context.task_id,
    }
    values.update(overrides)
    return MemoryOwner(**values)


def test_matching_session_private_owner_returns_explicit_permit() -> None:
    context = valid_agent_context(scope_ceiling=MemoryScope.AGENT_PRIVATE)

    decision = IsolationPolicy().authorize(
        context,
        owner(context),
        required_capability="memory:search",
        at=TEST_ONLY_NOW + timedelta(seconds=1),
    )

    assert decision == AccessDecision.PERMITTED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("territory_id", _uuid7(20)),
        ("tenant_id", _uuid7(21)),
        ("user_id", _uuid7(22)),
        ("agent_instance_id", _uuid7(23)),
        ("session_id", _uuid7(24)),
        ("task_id", _uuid7(25)),
    ],
)
def test_session_private_owner_denies_any_identity_mismatch(field: str, value: UUID) -> None:
    context = valid_agent_context(scope_ceiling=MemoryScope.AGENT_PRIVATE)

    with pytest.raises(MemoryAccessDenied) as error:
        IsolationPolicy().authorize(
            context,
            owner(context, **{field: value}),
            required_capability="memory:search",
            at=TEST_ONLY_NOW + timedelta(seconds=1),
        )

    assert error.value.code == "memory_access_denied"
    assert str(error.value) == "memory_access_denied"
    assert field not in str(error.value)


def test_agent_private_owner_does_not_require_session_or_task_match() -> None:
    context = valid_agent_context(scope_ceiling=MemoryScope.AGENT_PRIVATE)

    decision = IsolationPolicy().authorize(
        context,
        owner(
            context,
            scope=MemoryScope.AGENT_PRIVATE,
            session_id=_uuid7(30),
            task_id=_uuid7(31),
        ),
        required_capability="memory:search",
        at=TEST_ONLY_NOW + timedelta(seconds=1),
    )

    assert decision is AccessDecision.PERMITTED


@pytest.mark.parametrize(
    ("context_overrides", "owner_overrides", "capability", "reason"),
    [
        ({}, {}, "memory:write", "missing_capability"),
        (
            {"scope_ceiling": MemoryScope.SESSION_PRIVATE},
            {"scope": MemoryScope.AGENT_PRIVATE},
            "memory:search",
            "scope_ceiling_exceeded",
        ),
        ({}, {"scope": MemoryScope.TEAM_PRIVATE}, "memory:search", "unsupported_scope"),
        ({}, {"scope": MemoryScope.DOMAIN_CONTROLLED}, "memory:search", "unsupported_scope"),
        ({}, {"scope": MemoryScope.TENANT_CONTROLLED}, "memory:search", "unsupported_scope"),
        ({}, {"scope": MemoryScope.GLOBAL_GOLDEN}, "memory:search", "unsupported_scope"),
        ({}, {"scope": MemoryScope.EXTERNAL_RAG}, "memory:search", "unsupported_scope"),
    ],
)
def test_policy_denies_missing_capability_scope_escalation_and_broader_scopes(
    context_overrides: dict[str, object],
    owner_overrides: dict[str, object],
    capability: str,
    reason: str,
) -> None:
    context_values = {"scope_ceiling": MemoryScope.AGENT_PRIVATE, **context_overrides}
    context = valid_agent_context(**context_values)

    with pytest.raises(MemoryAccessDenied) as error:
        IsolationPolicy().authorize(
            context,
            owner(context, **owner_overrides),
            required_capability=capability,
            at=TEST_ONLY_NOW + timedelta(seconds=1),
        )

    assert error.value.code == reason
    assert str(error.value) == reason


@pytest.mark.parametrize("offset", [timedelta(microseconds=-1), timedelta(minutes=5)])
def test_policy_denies_inactive_identity_context(offset: timedelta) -> None:
    context = valid_agent_context()

    with pytest.raises(MemoryAccessDenied) as error:
        IsolationPolicy().authorize(
            context,
            owner(context),
            required_capability="memory:search",
            at=TEST_ONLY_NOW + offset,
        )

    assert error.value.code == "identity_inactive"
