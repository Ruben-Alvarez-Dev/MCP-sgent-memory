"""Session lifecycle tests using deterministic sanitized TEST-ONLY values."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from jart_memory.domain.session import (
    IllegalSessionTransitionError,
    Session,
    SessionState,
    StaleSessionWriterError,
)


TEST_ONLY_NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def _uuid7(number: int) -> UUID:
    """Return a deterministic UUIDv7 reserved exclusively for tests."""
    return UUID(f"018f0d6e-7a69-7{number:03x}-8000-{number:012x}")


def active_session(**overrides: object) -> Session:
    values: dict[str, object] = {
        "session_id": _uuid7(1),
        "territory_id": _uuid7(2),
        "tenant_id": _uuid7(3),
        "user_id": _uuid7(4),
        "agent_definition_id": _uuid7(5),
        "agent_instance_id": _uuid7(6),
        "task_id": _uuid7(7),
        "state": SessionState.ACTIVE,
        "session_seq_high_watermark": 0,
        "started_at": TEST_ONLY_NOW,
        "ended_at": None,
        "created_at": TEST_ONLY_NOW,
        "updated_at": TEST_ONLY_NOW,
        "identity_context_hash": "a" * 64,
    }
    values.update(overrides)
    return Session(**values)


def test_session_is_immutable_and_starts_active_at_zero() -> None:
    session = active_session()

    assert session.state is SessionState.ACTIVE
    assert session.session_seq_high_watermark == 0
    with pytest.raises(FrozenInstanceError):
        session.state = SessionState.ENDING  # type: ignore[misc]


def test_session_transitions_active_to_ending_to_ended_immutably() -> None:
    session = active_session()

    ending = session.transition(SessionState.ENDING, TEST_ONLY_NOW + timedelta(seconds=1))
    ended = ending.transition(SessionState.ENDED, TEST_ONLY_NOW + timedelta(seconds=2))

    assert session.state is SessionState.ACTIVE
    assert ending.state is SessionState.ENDING
    assert ended.state is SessionState.ENDED
    assert ended.ended_at == TEST_ONLY_NOW + timedelta(seconds=2)


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        (SessionState.ACTIVE, SessionState.ENDED),
        (SessionState.ENDING, SessionState.ACTIVE),
        (SessionState.ENDED, SessionState.ACTIVE),
        (SessionState.ENDED, SessionState.REVOKED),
        (SessionState.REVOKED, SessionState.ACTIVE),
    ],
)
def test_session_rejects_illegal_transitions(initial: SessionState, target: SessionState) -> None:
    session = active_session(state=initial)

    with pytest.raises(IllegalSessionTransitionError) as error:
        session.transition(target, TEST_ONLY_NOW + timedelta(seconds=1))

    assert error.value.code == "illegal_transition"


def test_active_and_ending_sessions_can_be_revoked() -> None:
    active = active_session()
    ending = active.transition(SessionState.ENDING, TEST_ONLY_NOW + timedelta(seconds=1))

    revoked_active = active.transition(SessionState.REVOKED, TEST_ONLY_NOW + timedelta(seconds=1))
    revoked_ending = ending.transition(SessionState.REVOKED, TEST_ONLY_NOW + timedelta(seconds=2))

    assert revoked_active.state is SessionState.REVOKED
    assert revoked_ending.state is SessionState.REVOKED


@pytest.mark.parametrize("state", [SessionState.ENDING, SessionState.ENDED, SessionState.REVOKED])
def test_only_active_sessions_advance_sequence(state: SessionState) -> None:
    session = active_session(state=state)

    with pytest.raises(IllegalSessionTransitionError) as error:
        session.advance_sequence(expected_high_watermark=0, at=TEST_ONLY_NOW + timedelta(seconds=1))

    assert error.value.code == "session_not_active"


def test_sequence_advancement_returns_new_session_and_monotonic_high_watermark() -> None:
    session = active_session()

    advanced = session.advance_sequence(expected_high_watermark=0, at=TEST_ONLY_NOW + timedelta(seconds=1))
    advanced_again = advanced.advance_sequence(expected_high_watermark=1, at=TEST_ONLY_NOW + timedelta(seconds=2))

    assert session.session_seq_high_watermark == 0
    assert advanced.session_seq_high_watermark == 1
    assert advanced_again.session_seq_high_watermark == 2
    assert advanced_again.updated_at == TEST_ONLY_NOW + timedelta(seconds=2)


def test_stale_writer_is_rejected_without_advancing_high_watermark() -> None:
    session = active_session().advance_sequence(0, TEST_ONLY_NOW + timedelta(seconds=1))

    with pytest.raises(StaleSessionWriterError) as error:
        session.advance_sequence(expected_high_watermark=0, at=TEST_ONLY_NOW + timedelta(seconds=2))

    assert error.value.code == "stale_session_writer"
    assert session.session_seq_high_watermark == 1
