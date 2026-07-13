"""Identity-domain tests using deterministic sanitized TEST-ONLY values."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from jart_memory.domain.identity import (
    DomainValidationError,
    IdentityContext,
    IdentityInactiveError,
    MemoryScope,
    PrincipalKind,
)


TEST_ONLY_NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def _uuid7(number: int) -> UUID:
    """Return a deterministic UUIDv7 reserved exclusively for tests."""
    return UUID(f"018f0d6e-7a69-7{number:03x}-8000-{number:012x}")


def valid_agent_context(**overrides) -> IdentityContext:
    values = {
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
        "purpose": "identity-domain-test",
        "scope_ceiling": MemoryScope.AGENT_PRIVATE,
        "capabilities": frozenset({"memory:capture", "memory:search"}),
        "issued_at": TEST_ONLY_NOW,
        "expires_at": TEST_ONLY_NOW + timedelta(minutes=5),
    }
    values.update(overrides)
    return IdentityContext(**values)


def test_valid_agent_context_is_immutable_and_active() -> None:
    context = valid_agent_context()

    assert context.assert_active(TEST_ONLY_NOW + timedelta(seconds=1)) is context
    with pytest.raises(FrozenInstanceError):
        context.purpose = "widened"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_id", UUID("550e8400-e29b-41d4-a716-446655440000")),
        ("task_id", UUID("550e8400-e29b-41d4-a716-446655440000")),
        ("plaza_id", UUID("550e8400-e29b-41d4-a716-446655440000")),
    ],
)
def test_context_rejects_non_uuid7_identifiers(field: str, value: UUID) -> None:
    with pytest.raises(DomainValidationError, match=field) as error:
        valid_agent_context(**{field: value})

    assert error.value.code == "invalid_uuid7"


@pytest.mark.parametrize("missing_field", ["user_id", "agent_definition_id", "agent_instance_id"])
def test_agent_principal_requires_complete_agent_identity(missing_field: str) -> None:
    with pytest.raises(DomainValidationError, match=missing_field) as error:
        valid_agent_context(**{missing_field: None})

    assert error.value.code == "missing_agent_identity"


@pytest.mark.parametrize("field", ["issued_at", "expires_at"])
def test_context_rejects_naive_or_non_utc_time(field: str) -> None:
    with pytest.raises(DomainValidationError, match=field) as error:
        valid_agent_context(**{field: datetime(2026, 7, 13)})

    assert error.value.code == "invalid_utc_time"


def test_context_rejects_invalid_validity_interval() -> None:
    with pytest.raises(DomainValidationError) as error:
        valid_agent_context(expires_at=TEST_ONLY_NOW)

    assert error.value.code == "invalid_validity_interval"


@pytest.mark.parametrize(
    ("at", "reason"),
    [
        (TEST_ONLY_NOW - timedelta(microseconds=1), "not_yet_active"),
        (TEST_ONLY_NOW + timedelta(minutes=5), "expired"),
    ],
)
def test_context_denies_outside_active_window(at: datetime, reason: str) -> None:
    with pytest.raises(IdentityInactiveError) as error:
        valid_agent_context().assert_active(at)

    assert error.value.code == reason


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"purpose": ""}, "missing_purpose"),
        ({"capabilities": frozenset()}, "missing_capabilities"),
        ({"credential_version": 0}, "invalid_credential_version"),
        ({"schema_version": "latest"}, "invalid_semantic_version"),
        ({"policy_version": "current"}, "invalid_semantic_version"),
    ],
)
def test_context_rejects_implicit_or_incomplete_authority(overrides: dict, code: str) -> None:
    with pytest.raises(DomainValidationError) as error:
        valid_agent_context(**overrides)

    assert error.value.code == code
