"""Immutable session lifecycle and optimistic sequence invariants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import RFC_4122, UUID


class SessionState(StrEnum):
    """States and legal lifecycle stages of a memory session."""

    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"
    REVOKED = "revoked"


class SessionError(ValueError):
    """Base class for typed session domain failures."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


class IllegalSessionTransitionError(SessionError):
    """Raised when a session state transition is not permitted."""


class StaleSessionWriterError(SessionError):
    """Raised when an optimistic sequence writer has an obsolete watermark."""


def _require_uuid7(field: str, value: UUID) -> None:
    if not isinstance(value, UUID) or value.version != 7 or value.variant != RFC_4122:
        raise SessionError("invalid_uuid7", f"{field} must be an RFC 4122 UUIDv7")


def _require_utc(field: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise SessionError("invalid_utc_time", f"{field} must be timezone-aware UTC")


def _require_hash(field: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SessionError("invalid_hash", f"{field} must be a lowercase SHA-256 hexadecimal digest")


@dataclass(frozen=True, slots=True)
class Session:
    """Immutable session aggregate whose transitions return replacements."""

    session_id: UUID
    territory_id: UUID
    tenant_id: UUID
    user_id: UUID | None
    agent_definition_id: UUID | None
    agent_instance_id: UUID | None
    task_id: UUID
    state: SessionState
    session_seq_high_watermark: int
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime
    identity_context_hash: str

    def __post_init__(self) -> None:
        for field in (
            "session_id",
            "territory_id",
            "tenant_id",
            "user_id",
            "agent_definition_id",
            "agent_instance_id",
            "task_id",
        ):
            value = getattr(self, field)
            if value is not None:
                _require_uuid7(field, value)

        if not isinstance(self.state, SessionState):
            raise SessionError("invalid_state", "state is not supported")
        if (
            not isinstance(self.session_seq_high_watermark, int)
            or isinstance(self.session_seq_high_watermark, bool)
            or self.session_seq_high_watermark < 0
        ):
            raise SessionError("invalid_sequence", "session_seq_high_watermark must be a non-negative integer")

        for field in ("started_at", "created_at", "updated_at"):
            _require_utc(field, getattr(self, field))
        if self.ended_at is not None:
            _require_utc("ended_at", self.ended_at)
        _require_hash("identity_context_hash", self.identity_context_hash)

    def transition(self, target: SessionState, at: datetime) -> Session:
        """Return a new session after one legal lifecycle transition."""

        _require_utc("at", at)
        legal_targets = {
            SessionState.ACTIVE: {SessionState.ENDING, SessionState.REVOKED},
            SessionState.ENDING: {SessionState.ENDED, SessionState.REVOKED},
            SessionState.ENDED: set(),
            SessionState.REVOKED: set(),
        }
        if not isinstance(target, SessionState) or target not in legal_targets[self.state]:
            raise IllegalSessionTransitionError(
                "illegal_transition", f"cannot transition {self.state.value} to {getattr(target, 'value', target)}"
            )
        if at < self.updated_at:
            raise SessionError("non_monotonic_time", "transition time must not precede updated_at")

        ended_at = at if target in (SessionState.ENDED, SessionState.REVOKED) else self.ended_at
        return self.__class__(
            session_id=self.session_id,
            territory_id=self.territory_id,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            agent_definition_id=self.agent_definition_id,
            agent_instance_id=self.agent_instance_id,
            task_id=self.task_id,
            state=target,
            session_seq_high_watermark=self.session_seq_high_watermark,
            started_at=self.started_at,
            ended_at=ended_at,
            created_at=self.created_at,
            updated_at=at,
            identity_context_hash=self.identity_context_hash,
        )

    def advance_sequence(self, expected_high_watermark: int, at: datetime) -> Session:
        """Return an active session with its optimistic watermark advanced once."""

        _require_utc("at", at)
        if self.state is not SessionState.ACTIVE:
            raise IllegalSessionTransitionError("session_not_active", "only active sessions advance sequence")
        if expected_high_watermark != self.session_seq_high_watermark:
            raise StaleSessionWriterError(
                "stale_session_writer",
                "expected high-watermark does not match the current session high-watermark",
            )
        if at < self.updated_at:
            raise SessionError("non_monotonic_time", "sequence time must not precede updated_at")
        return self.__class__(
            session_id=self.session_id,
            territory_id=self.territory_id,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            agent_definition_id=self.agent_definition_id,
            agent_instance_id=self.agent_instance_id,
            task_id=self.task_id,
            state=self.state,
            session_seq_high_watermark=self.session_seq_high_watermark + 1,
            started_at=self.started_at,
            ended_at=self.ended_at,
            created_at=self.created_at,
            updated_at=at,
            identity_context_hash=self.identity_context_hash,
        )
