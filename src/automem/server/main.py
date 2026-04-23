"""AutoMem — Real-time Memory Ingestion Daemon."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from shared.env_loader import load_env
load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.models import HeartbeatStatus, MemoryItem, MemoryLayer, MemoryScope, MemoryType, RawEvent, RawEventType
from shared.embedding import async_embed, safe_embed, bm25_tokenize
from shared.sanitize import validate_memorize, validate_ingest_event
from shared.result_models import MemorizeResult, IngestResult, HeartbeatResult, AutoMemStatusResult

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, config.qdrant_collection, config.embedding_dim)
JSONL_PATH = config.raw_events_jsonl
PROMOTION_INTERVAL = config.automem_promote_every
STAGING_BUFFER = Path(config.staging_buffer_path) if config.staging_buffer_path else Path("")

mcp = FastMCP("automem")


async def _store_memory(item: MemoryItem) -> bool:
    """Store memory. Returns True if stored, False if failed. Falls back to JSONL."""
    import logging
    _log = logging.getLogger(__name__)
    try:
        await qdrant.ensure_collection()
        vector = item.embedding if item.embedding else await safe_embed(item.content)
        sparse = bm25_tokenize(item.content)
        await qdrant.upsert(item.memory_id, vector, item.model_dump(mode="json"), sparse=sparse)
        return True
    except Exception as e:
        _log.error("Failed to store memory %s: %s", item.memory_id, e)
        # Fallback: write to JSONL so data is never lost
        _append_raw_jsonl(RawEvent(
            type=RawEventType.SYSTEM, source="automem_fallback",
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
    """Store a memory. AutoMem ingests it immediately."""
    from shared.timing import Timer, DEBUG
    t = Timer()
    clean = validate_memorize(content, mem_type, scope, tags)
    scope_map = {"session": MemoryScope.SESSION, "agent": MemoryScope.AGENT, "domain": MemoryScope.DOMAIN, "personal": MemoryScope.PERSONAL, "global-core": MemoryScope.GLOBAL_CORE}
    item = MemoryItem(layer=MemoryLayer.WORKING, scope_type=scope_map.get(clean["scope"], MemoryScope.AGENT), scope_id=scope_id, type=MemoryType(clean["mem_type"]), content=clean["content"], importance=importance, topic_ids=clean["tags"])
    t.start("store"); await _store_memory(item); t.stop()
    _append_raw_jsonl(RawEvent(type=RawEventType.AGENT_ACTION, source="automem", actor_id=scope_id, attributes={"memory_id": item.memory_id, "type": clean["mem_type"]}))
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
    # Prefetch embeddings in background (non-blocking)
    if prefetch_queries:
        try:
            from shared.embedding import async_embed_batch
            import asyncio
            asyncio.create_task(async_embed_batch(prefetch_queries))
        except Exception:
            pass  # Prefetch is best-effort
    
    status = HeartbeatStatus(agent_id=agent_id, session_id=session_id, turn_count=turn_count, status="active")
    hb_dir = Path(config.heartbeats_path)
    hb_dir.mkdir(parents=True, exist_ok=True)
    (hb_dir / f"{agent_id}.json").write_text(status.model_dump_json(indent=2))
    promote_due = turn_count > 0 and turn_count % PROMOTION_INTERVAL == 0
    return HeartbeatResult(status="active", agent_id=agent_id, turn_count=turn_count, promotion_due=promote_due)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> AutoMemStatusResult:
    """Show AutoMem daemon status — always ON regardless of agent state."""
    qdrant_ok = await qdrant.health()
    try:
        from shared.embedding import _get_llama_cmd
        llama_ok = _get_llama_cmd() is not None
    except (ImportError, OSError):
        llama_ok = False
    raw_events = sum(1 for _ in open(JSONL_PATH)) if Path(JSONL_PATH).exists() else 0
    memory_count = await qdrant.count() if qdrant_ok else 0
    staging = sum(1 for _ in STAGING_BUFFER.glob("*.json")) if STAGING_BUFFER.exists() else 0
    return AutoMemStatusResult(daemon="AutoMem", status="RUNNING", qdrant="OK" if qdrant_ok else "DOWN", llama_cpp="OK" if llama_ok else "NOT_INSTALLED", raw_events_jsonl=raw_events, stored_memories=memory_count, staged_change_sets=staging)


def register_tools(target_mcp: FastMCP, target_qdrant: QdrantClient, target_config: Config, prefix: str = "") -> None:
    global qdrant, config
    qdrant = target_qdrant
    config = target_config
    target_mcp.add_tool(memorize, name=f"{prefix}memorize")
    target_mcp.add_tool(ingest_event, name=f"{prefix}ingest_event")
    target_mcp.add_tool(heartbeat, name=f"{prefix}heartbeat")
    target_mcp.add_tool(status, name=f"{prefix}status")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
