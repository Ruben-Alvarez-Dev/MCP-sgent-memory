"""Minimal local terminal UI for inspecting the identity-session MVP."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from jart_memory.domain.session import Session, SessionState


def _uuid7() -> UUID:
    """Generate a local UUIDv7-compatible identifier for the TUI process."""
    value = uuid4().hex
    return UUID(f"{value[:8]}-{value[8:12]}-7{value[13:16]}-8{value[17:20]}-{value[20:]}")


def new_local_session() -> Session:
    now = datetime.now(timezone.utc)
    identifier = _uuid7()
    return Session(
        session_id=identifier,
        territory_id=_uuid7(),
        tenant_id=_uuid7(),
        user_id=_uuid7(),
        agent_definition_id=_uuid7(),
        agent_instance_id=_uuid7(),
        task_id=_uuid7(),
        state=SessionState.ACTIVE,
        session_seq_high_watermark=0,
        started_at=now,
        ended_at=None,
        created_at=now,
        updated_at=now,
        identity_context_hash="0" * 64,
    )


def render(session: Session, message: str = "") -> str:
    return "\n".join(
        (
            "╔════════════════════════════════════════════════════╗",
            "║ JART MEMORY — LOCAL MVP TUI                        ║",
            "╠════════════════════════════════════════════════════╣",
            f"║ Session: {session.session_id} ║",
            f"║ State:   {session.state.value:<39}║",
            f"║ Sequence:{session.session_seq_high_watermark:<39}║",
            "╠════════════════════════════════════════════════════╣",
            "║ [a] advance sequence   [e] end   [q] quit          ║",
            f"║ {message:<51}║",
            "╚════════════════════════════════════════════════════╝",
        )
    )


def main() -> None:
    session = new_local_session()
    print(render(session))
    while session.state not in (SessionState.ENDED, SessionState.REVOKED):
        command = input("> ").strip().lower()
        now = datetime.now(timezone.utc)
        if command == "a":
            session = session.advance_sequence(session.session_seq_high_watermark, now)
            print(render(session, "Sequence advanced"))
        elif command == "e":
            ending = session.transition(SessionState.ENDING, now)
            session = ending.transition(SessionState.ENDED, now)
            print(render(session, "Session ended"))
        elif command == "q":
            break
        else:
            print(render(session, "Unknown command"))


if __name__ == "__main__":
    main()
