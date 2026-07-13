"""Application use-case tests with deterministic TEST-ONLY ports."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jart_memory.application.use_cases import (
    AdvanceSession,
    AuthorizeMemoryAccess,
    EndSession,
    StartSession,
)
from jart_memory.domain.identity import MemoryScope
from jart_memory.policy.isolation import AccessDecision, MemoryOwner
from tests.unit.application.tests_fixtures import FakeClock, FakeRepository, FakeUuid7Generator, valid_agent_context


TEST_ONLY_NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def test_start_and_advance_session_use_cases_use_ports() -> None:
    context = valid_agent_context(session_id=_uuid7(20))
    repository = FakeRepository()
    session = StartSession(FakeClock(TEST_ONLY_NOW), FakeUuid7Generator(20), repository).execute(context)

    advanced = AdvanceSession(FakeClock(TEST_ONLY_NOW + timedelta(seconds=1)), repository).execute(
        context, expected_high_watermark=0
    )

    assert session.session_id == _uuid7(20)
    assert advanced.session_seq_high_watermark == 1


def test_end_session_transitions_active_session_to_ended() -> None:
    context = valid_agent_context(session_id=_uuid7(20))
    repository = FakeRepository()
    StartSession(FakeClock(TEST_ONLY_NOW), FakeUuid7Generator(20), repository).execute(context)

    ended = EndSession(FakeClock(TEST_ONLY_NOW + timedelta(seconds=1)), repository).execute(context)

    assert ended.state.value == "ended"


def test_authorize_memory_access_delegates_to_isolation_policy() -> None:
    context = valid_agent_context(scope_ceiling=MemoryScope.AGENT_PRIVATE)
    owner = MemoryOwner(
        scope=MemoryScope.SESSION_PRIVATE,
        territory_id=context.territory_id,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        agent_instance_id=context.agent_instance_id,
        session_id=context.session_id,
        task_id=context.task_id,
    )

    decision = AuthorizeMemoryAccess().execute(context, owner, "memory:search", TEST_ONLY_NOW)

    assert decision is AccessDecision.PERMITTED


def _uuid7(number: int) -> UUID:
    return UUID(f"018f0d6e-7a69-7{number:03x}-8000-{number:012x}")
