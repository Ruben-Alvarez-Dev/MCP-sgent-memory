"""AutoMem — Real-time Memory Ingestion Daemon.

Runs INDEPENDENTLY of the LLM agent. Always ON.
Captures events from filesystem, terminal, git, and system.
Promotes raw events → working memory → episodic memory.

Frequency:
  - Every user message: embed + index (L1 working)
  - Every N turns: promote to episodic (L2)
  - On session close: tag and finalize

No LLM required. Works with agent disconnected.
Embeddings via llama.cpp (self-contained, no Ollama).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.models import (
    HeartbeatStatus,
    MemoryItem,
    MemoryLayer,
    MemoryScope,
    MemoryType,
    RawEvent,
    RawEventType,
)

# Embedding via llama.cpp (self-contained)
from shared.embedding import get_embedding as llama_embed, _ensure_binaries as _ensure_llama

mcp = FastMCP("automem")

# ── Configuration ──────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "automem")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
JSONL_PATH = os.path.expanduser(os.getenv("AUTOMEM_JSONL", str(Path.home() / ".memory" / "raw_events.jsonl"))
PROMOTION_INTERVAL = int(os.getenv("AUTOMEM_PROMOTE_EVERY", "10"))  # turns

# ── Qdrant helpers ─────────────────────────────────────────────────

async def ensure_collection():
    """Create Qdrant collection if not exists."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{QDRANT_URL}/collections")
        existing = [c["name"] for c in resp.json().get("result", {}).get("collections", [])]
        if QDRANT_COLLECTION not in existing:
            await client.put(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
                json={"vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"}},
            )


async def embed_text(text: str) -> list[float]:
    """Generate embedding via llama.cpp (self-contained)."""
    _ensure_llama()
    return await asyncio.to_thread(llama_embed, text)


async def store_memory(item: MemoryItem):
    """Store a memory item in Qdrant with embedding."""
    await ensure_collection()

    # Generate embedding
    vector = await embed_text(item.content) if item.embedding is None else item.embedding

    point = {
        "id": item.memory_id,
        "vector": vector,
        "payload": item.model_dump(mode="json"),
    }

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={"points": [point]},
        )


async def append_raw_jsonl(event: RawEvent):
    """Append raw event to JSONL file (L0 audit trail)."""
    path = Path(JSONL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(event.model_dump_json() + "\n")


# ── Public MCP Tools ──────────────────────────────────────────────


@mcp.tool()
async def memorize(
    content: str,
    mem_type: str = "fact",
    scope: str = "session",
    scope_id: str = "current",
    importance: float = 0.5,
    tags: str = "",
) -> str:
    """Store a memory. AutoMem ingests it immediately.

    Args:
        content: The memory content.
        mem_type: fact | step | preference | decision | episode | summary
        scope: session | agent | domain | personal | global-core
        scope_id: e.g. 'frontend', 'ruben', 'session-abc'
        importance: 0.0-1.0
        tags: Comma-separated tags.
    """
    scope_map = {
        "session": MemoryScope.SESSION,
        "agent": MemoryScope.AGENT,
        "domain": MemoryScope.DOMAIN,
        "personal": MemoryScope.PERSONAL,
        "global-core": MemoryScope.GLOBAL_CORE,
    }

    item = MemoryItem(
        layer=MemoryLayer.WORKING,
        scope_type=scope_map.get(scope, MemoryScope.AGENT),
        scope_id=scope_id,
        type=MemoryType(mem_type),
        content=content,
        importance=importance,
        topic_ids=[t.strip() for t in tags.split(",") if t.strip()],
    )

    await store_memory(item)

    # Also append as raw event for audit
    raw = RawEvent(
        type=RawEventType.AGENT_ACTION,
        source="automem",
        actor_id=scope_id,
        attributes={"memory_id": item.memory_id, "type": mem_type},
    )
    await append_raw_jsonl(raw)

    return json.dumps({
        "status": "stored",
        "memory_id": item.memory_id,
        "layer": "L1_WORKING",
        "scope": item.full_scope,
    }, indent=2)


@mcp.tool()
async def ingest_event(
    event_type: str,
    source: str,
    content: str,
    actor_id: str = "system",
    session_id: str = "",
) -> str:
    """Ingest a raw L0 event (terminal, git, file, system).

    This is the fire-and-forget capture that works even when the LLM is disconnected.
    """
    type_map = {
        "terminal": RawEventType.TERMINAL,
        "file": RawEventType.FILE_ACCESS,
        "git": RawEventType.GIT_EVENT,
        "agent": RawEventType.AGENT_ACTION,
        "ide": RawEventType.IDE_EVENT,
        "system": RawEventType.SYSTEM,
    }

    event = RawEvent(
        type=type_map.get(event_type, RawEventType.SYSTEM),
        source=source,
        actor_id=actor_id,
        session_id=session_id,
        attributes={"content": content},
    )

    await append_raw_jsonl(event)

    # Auto-promote to working memory if important enough
    if len(content) > 20:  # Non-trivial event
        item = MemoryItem(
            layer=MemoryLayer.WORKING,
            scope_type=MemoryScope.SESSION if session_id else MemoryScope.AGENT,
            scope_id=session_id or "system",
            type=MemoryType.FACT,
            content=content[:2000],  # Truncate for working memory
            source_event_ids=[event.event_id],
            importance=0.3,
        )
        await store_memory(item)

    return json.dumps({
        "status": "ingested",
        "event_id": event.event_id,
        "layer": "L0_RAW + L1_WORKING",
    }, indent=2)


@mcp.tool()
async def heartbeat(
    agent_id: str,
    session_id: str = "",
    turn_count: int = 0,
) -> str:
    """Update agent heartbeat. Call every turn to signal the agent is alive.

    If heartbeat stops, the daemon continues ingest but pauses context injection.
    """
    status = HeartbeatStatus(
        agent_id=agent_id,
        session_id=session_id,
        turn_count=turn_count,
        status="active",
    )

    # Store heartbeat
    hb_path = Path.home() / ".memory" / "heartbeats" / f"{agent_id}.json"
    hb_path.parent.mkdir(parents=True, exist_ok=True)
    hb_path.write_text(status.model_dump_json(indent=2))

    # Check if promotion is due
    promote_due = turn_count > 0 and turn_count % PROMOTION_INTERVAL == 0

    return json.dumps({
        "status": "active",
        "agent_id": agent_id,
        "turn_count": turn_count,
        "promotion_due": promote_due,
        "message": "Daemon running — memory ingest active",
    }, indent=2)


@mcp.tool()
async def status() -> str:
    """Show AutoMem daemon status — always ON regardless of agent state."""
    # Check Qdrant
    qdrant_ok = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{QDRANT_URL}/collections")
            qdrant_ok = resp.status_code == 200
    except Exception:
        pass  # health check fallback
        pass

    # Check llama.cpp
    llama_ok = False
    try:
        from shared.embedding import _get_llama_cmd
        llama_ok = _get_llama_cmd() is not None
    except Exception:
        pass  # health check fallback
        pass

    # Check JSONL
    jsonl_path = Path(JSONL_PATH)
    raw_events = 0
    if jsonl_path.exists():
        raw_events = sum(1 for _ in open(jsonl_path))

    # Count stored memories
    memory_count = 0
    if qdrant_ok:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}")
                memory_count = resp.json().get("result", {}).get("points_count", 0)
        except Exception:
        pass  # health check fallback
            pass

    # Check heartbeat
    hb_path = Path.home() / ".memory" / "heartbeats"
    agents = []
    if hb_path.exists():
        for f in hb_path.glob("*.json"):
            data = json.loads(f.read_text())
            agents.append(data)

    return json.dumps({
        "daemon": "AutoMem",
        "status": "RUNNING",
        "qdrant": "OK" if qdrant_ok else "DOWN",
        "llama_cpp": "OK" if llama_ok else "NOT_INSTALLED",
        "raw_events_jsonl": raw_events,
        "stored_memories": memory_count,
        "active_agents": agents,
        "note": "Daemon runs independently — works even when LLM is disconnected",
    }, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
