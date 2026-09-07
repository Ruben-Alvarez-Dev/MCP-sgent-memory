# M7: Embedding imports removed. FTS5-only retrieval.
"""L0_capture — Real-time Memory Ingestion Daemon (M2-storage port).

Storage is shared.memory_db.MemoryDB (SQLite, collection 'L0_L4_memory');
events.jsonl remains the ingestion source of truth (storage is memory.db)
(STO-03) and is append-only — never rewritten from here.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from shared.env_loader import load_env

load_env()
from shared.config import Config
from shared.memory_db import MemoryDB
from shared.models import HeartbeatStatus, MemoryItem, MemoryLayer, MemoryScope, MemoryType, RawEvent, RawEventType
from shared.result_models import HeartbeatResult, IngestResult, L0CaptureStatusResult, MemorizeResult
from shared.sanitize import validate_ingest_event, validate_memorize
from shared.scope import assert_contained

config = Config.from_env()
db = MemoryDB(None, "L0_L4_memory", config.embedding_dim)
from shared.identity import bind_identity

IDENTITY = bind_identity()  # M4: strict mode raises here (fail-closed boot, ISO-14)
JSONL_PATH = config.L0_events_jsonl
PROMOTION_INTERVAL = config.L0_capture_promote_every
STAGING_BUFFER = Path(config.tmp_path) if config.tmp_path else Path("")

mcp = FastMCP("L0_capture")


async def _store_memory(item: MemoryItem) -> bool:
    """Store memory. Returns True if stored, False if failed. Falls back to JSONL."""
    import logging
    _log = logging.getLogger(__name__)
    try:
        await db.ensure_collection()
        vector = None  # M6: embeddings removed
        sparse = None  # M6: FTS5 replaces sparse vectors
        payload = dict(item.model_dump(mode="json"))
        # M5/M2: effective identity scope instead of a hardcoded public write.
        # Bound servers tag their OWN tenant scope (data stays private to the
        # engine-level filter); unbound (open) servers keep the legacy public
        # default so existing retrieval filters still see their memories.
        agent_scope = IDENTITY.assert_agent("default")  # ISO-15: bound→own scope
        if IDENTITY.mode != "bound":
            agent_scope = "shared"  # open mode: no verified tenant → public
        payload["agent_scope"] = agent_scope
        # user_id passthrough: preserved automatically if the item payload carried one
        await db.upsert(item.memory_id, payload, sparse=sparse)
        return True
    except Exception as e:
        _log.error("Failed to store memory %s: %s", item.memory_id, e)
        # Fallback: write to JSONL so data is never lost
        _append_raw_jsonl(RawEvent(
            type=RawEventType.SYSTEM, source="L0_capture_fallback",
            attributes={"error": str(e), "memory_id": item.memory_id, "content": item.content[:500]},
        ))
        return False


def _append_raw_jsonl(event: RawEvent) -> None:
    path = Path(JSONL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(event.model_dump_json() + "\n")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def memorize(content: str, mem_type: str = "fact", scope: str = "session", scope_id: str = "current", importance: float = 0.5, tags: str = "") -> dict:
    """Store a memory. L0_capture ingests it immediately."""
    from shared.timing import DEBUG, Timer
    t = Timer()
    clean = validate_memorize(content, mem_type, scope, tags)
    scope_map = {"session": MemoryScope.SESSION, "agent": MemoryScope.AGENT, "domain": MemoryScope.DOMAIN, "personal": MemoryScope.PERSONAL, "global-core": MemoryScope.GLOBAL_CORE}
    item = MemoryItem(layer=MemoryLayer.WORKING, scope_type=scope_map.get(clean["scope"], MemoryScope.AGENT), scope_id=scope_id, type=MemoryType(clean["mem_type"]), content=clean["content"], importance=importance, topic_ids=clean["tags"])
    t.start("store"); await _store_memory(item); t.stop()
    _append_raw_jsonl(RawEvent(type=RawEventType.AGENT_ACTION, source="L0_capture", actor_id=scope_id, attributes={"memory_id": item.memory_id, "type": clean["mem_type"]}))
    result = MemorizeResult(status="stored", memory_id=item.memory_id, layer="L1_WORKING", scope=item.full_scope).model_dump()
    if DEBUG:
        result.update(t.to_dict())
    return result


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def ingest_event(event_type: str, source: str, content: str, actor_id: str = "system", session_id: str = "") -> IngestResult:
    """Ingest a raw L0 event (terminal, git, file, system, diff)."""
    clean = validate_ingest_event(event_type, source, content)
    type_map = {"terminal": RawEventType.TERMINAL, "file": RawEventType.FILE_ACCESS, "git": RawEventType.GIT_EVENT, "agent": RawEventType.AGENT_ACTION, "ide": RawEventType.IDE_EVENT, "system": RawEventType.SYSTEM, "diff_proposed": RawEventType.AGENT_ACTION, "diff_accepted": RawEventType.AGENT_ACTION, "diff_rejected": RawEventType.AGENT_ACTION, "diff_applied": RawEventType.AGENT_ACTION, "diff_failed": RawEventType.AGENT_ACTION}
    is_diff = clean["event_type"].startswith("diff_")
    event = RawEvent(type=type_map.get(clean["event_type"], RawEventType.SYSTEM), source=clean["source"], actor_id=actor_id, session_id=session_id, attributes={"content": clean["content"], "event_subtype": clean["event_type"]})
    _append_raw_jsonl(event)
    importance, meta = 0.3, {}
    if is_diff and clean["content"].startswith("{"):
        try:
            d = json.loads(clean["content"])
            meta = {"diff_event": clean["event_type"], "file_path": d.get("file_path", ""), "language": d.get("language", "")}
            importance = 0.7 if clean["event_type"] == "diff_rejected" else 0.6
        except json.JSONDecodeError:
            pass
    if len(clean["content"]) > 20 or is_diff:
        item = MemoryItem(layer=MemoryLayer.WORKING, scope_type=MemoryScope.SESSION if session_id else MemoryScope.AGENT, scope_id=session_id or "system", type=MemoryType.FACT, content=clean["content"][:2000], source_event_ids=[event.event_id], importance=importance, metadata=meta)
        await _store_memory(item)
    return IngestResult(status="ingested", event_id=event.event_id, layer="L0_RAW + L1_WORKING")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def heartbeat(agent_id: str, session_id: str = "", turn_count: int = 0, prefetch_queries: list[str] = []) -> HeartbeatResult:
    """Update agent heartbeat. Call every turn to signal the agent is alive.
    
    Optional: pass prefetch_queries to pre-compute embeddings for upcoming searches.
    """
    # M5/H2: identity gate BEFORE any I/O (ISO-13) — rejects foreign/traversal
    # agent_ids while the server is bound; shape-validates them in open mode.
    agent_id = IDENTITY.assert_agent(agent_id)
    status = HeartbeatStatus(agent_id=agent_id, session_id=session_id, turn_count=turn_count, status="active")
    hb_dir = Path(config.L1_working_path)
    hb_dir.mkdir(parents=True, exist_ok=True)
    # M5/H2: fail-closed containment — a traversal/absolute agent_id can never
    # name a heartbeat file outside the L1 jail, even if shape checks regress.
    path = assert_contained(hb_dir / f"{agent_id}.json", hb_dir)
    path.write_text(status.model_dump_json(indent=2))
    promote_due = turn_count > 0 and turn_count % PROMOTION_INTERVAL == 0
    return HeartbeatResult(status="active", agent_id=agent_id, turn_count=turn_count, promotion_due=promote_due)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> L0CaptureStatusResult:
    """Show L0_capture daemon status — always ON regardless of agent state."""
    await db.ensure_collection()  # idempotent; makes count() safe on a virgin DB
    db_ok = await db.health()
    try:
                llama_ok = False
    except (ImportError, OSError):
        llama_ok = False
    raw_events = sum(1 for _ in open(JSONL_PATH)) if Path(JSONL_PATH).exists() else 0
    memory_count = await db.count() if db_ok else 0
    staging = sum(1 for _ in STAGING_BUFFER.glob("*.json")) if STAGING_BUFFER.exists() else 0
    # L0CaptureStatusResult.qdrant kept for model compatibility; storage is
    # MemoryDB now, so the field is explicitly 'n/a' (never 'OK'/'DOWN').
    return L0CaptureStatusResult(daemon="L0_capture", status="RUNNING", llama_cpp="OK" if llama_ok else "NOT_INSTALLED", L0_events_jsonl=raw_events, stored_memories=memory_count, staged_change_sets=staging)


def register_tools(target_mcp: FastMCP, target_qdrant, target_config: Config, prefix: str = "") -> None:
    """Register L0_capture tools. Positional signature is a public contract.

    target_qdrant is IGNORED (M2-storage: SQLite MemoryDB replaced the Qdrant
    daemon); it stays in the signature for positional compatibility with the
    unified server.
    """
    global config, db
    config = target_config
    if db.embedding_dim != config.embedding_dim:
        db = MemoryDB(None, "L0_L4_memory", config.embedding_dim)
    target_mcp.add_tool(memorize, name=f"{prefix}memorize")
    target_mcp.add_tool(ingest_event, name=f"{prefix}ingest_event")
    target_mcp.add_tool(heartbeat, name=f"{prefix}heartbeat")
    target_mcp.add_tool(status, name=f"{prefix}status")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


# M6 stub