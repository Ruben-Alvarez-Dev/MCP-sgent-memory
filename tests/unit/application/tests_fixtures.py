"""TEST-ONLY application ports and sanitized identity fixture."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jart_memory.domain.identity import IdentityContext, MemoryScope, PrincipalKind
from jart_memory.domain.session import Session

TEST_ONLY_NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def _uuid7(number: int) -> UUID:
    return UUID(f"018f0d6e-7a69-7{number:03x}-8000-{number:012x}")


def valid_agent_context(**overrides: object) -> IdentityContext:
    values = {
        "schema_version": "1.0.0", "context_id": _uuid7(1), "territory_id": _uuid7(2), "tenant_id": _uuid7(3),
        "principal_kind": PrincipalKind.AGENT, "principal_id": _uuid7(4), "user_id": _uuid7(5),
        "agent_definition_id": _uuid7(6), "agent_instance_id": _uuid7(7), "domain_id": _uuid7(8),
        "team_id": _uuid7(9), "session_id": _uuid7(10), "task_id": _uuid7(11), "plaza_id": _uuid7(12),
        "credential_version": 1, "policy_version": "1.0.0", "purpose": "application-test",
        "scope_ceiling": MemoryScope.AGENT_PRIVATE, "capabilities": frozenset({"memory:search"}),
        "issued_at": TEST_ONLY_NOW, "expires_at": TEST_ONLY_NOW + timedelta(minutes=5),
    }
    values.update(overrides)
    return IdentityContext(**values)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value


class FakeUuid7Generator:
    def __init__(self, number: int) -> None:
        self.number = number

    def new(self) -> UUID:
        return _uuid7(self.number)


class FakeRepository:
    def __init__(self) -> None:
        self.session: Session | None = None

    def create(self, session: Session) -> Session:
        self.session = session
        return session

    def get(self, session_id: UUID) -> Session:
        assert self.session is not None and self.session.session_id == session_id
        return self.session

    def save(self, session: Session, expected_high_watermark: int | None = None) -> Session:
        self.session = session
        return session
