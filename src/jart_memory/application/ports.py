"""Small application ports for time, identifiers, and session persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from jart_memory.domain.session import Session


class Clock(Protocol):
    def now(self) -> datetime: ...


class Uuid7Generator(Protocol):
    def new(self) -> UUID: ...


class SessionRepository(Protocol):
    def create(self, session: Session) -> Session: ...

    def get(self, session_id: UUID) -> Session: ...

    def save(self, session: Session, expected_high_watermark: int | None = None) -> Session: ...
