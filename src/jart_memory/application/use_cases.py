"""Minimal identity/session application use cases."""

from __future__ import annotations

import hashlib
from dataclasses import fields
from datetime import datetime

from jart_memory.application.ports import Clock, SessionRepository, Uuid7Generator
from jart_memory.domain.identity import IdentityContext
from jart_memory.domain.session import Session, SessionState
from jart_memory.policy.isolation import AccessDecision, IsolationPolicy, MemoryOwner


def _context_hash(context: IdentityContext) -> str:
    payload = "|".join(str(getattr(context, field.name)) for field in fields(context))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class StartSession:
    def __init__(self, clock: Clock, uuid7_generator: Uuid7Generator, repository: SessionRepository) -> None:
        self._clock, self._uuid7, self._repository = clock, uuid7_generator, repository

    def execute(self, context: IdentityContext) -> Session:
        now = self._clock.now()
        session = Session(
            session_id=self._uuid7.new(),
            territory_id=context.territory_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            agent_definition_id=context.agent_definition_id,
            agent_instance_id=context.agent_instance_id,
            task_id=context.task_id,
            state=SessionState.ACTIVE,
            session_seq_high_watermark=0,
            started_at=now,
            ended_at=None,
            created_at=now,
            updated_at=now,
            identity_context_hash=_context_hash(context),
        )
        return self._repository.create(session)


class AdvanceSession:
    def __init__(self, clock: Clock, repository: SessionRepository) -> None:
        self._clock, self._repository = clock, repository

    def execute(self, context: IdentityContext, *, expected_high_watermark: int) -> Session:
        session = self._repository.get(context.session_id)
        advanced = session.advance_sequence(expected_high_watermark, self._clock.now())
        return self._repository.save(advanced, expected_high_watermark)


class EndSession:
    def __init__(self, clock: Clock, repository: SessionRepository) -> None:
        self._clock, self._repository = clock, repository

    def execute(self, context: IdentityContext) -> Session:
        session = self._repository.get(context.session_id)
        now = self._clock.now()
        ending = session if session.state is SessionState.ENDING else session.transition(SessionState.ENDING, now)
        ended = ending.transition(SessionState.ENDED, now)
        return self._repository.save(ended, session.session_seq_high_watermark)


class AuthorizeMemoryAccess:
    def __init__(self, policy: IsolationPolicy | None = None) -> None:
        self._policy = policy or IsolationPolicy()

    def execute(
        self, context: IdentityContext, owner: MemoryOwner, required_capability: str, at: datetime
    ) -> AccessDecision:
        return self._policy.authorize(context, owner, required_capability=required_capability, at=at)
