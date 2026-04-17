"""AutoDream — Consolidation & Dream Daemon.

Runs INDEPENDENTLY of the LLM agent. Always ON.
Promotes memory between layers on schedules:

  Every N turns:    L1 → L2 (working → episodic)
  Every hour:       L2 → L3 (episodic → semantic, feed Engram)
  Nightly / idle:   L3 → L4 (semantic → consolidated narratives)
  Weekly:           Pattern detection, decay, archive

No LLM required for base consolidation.
Uses llama.cpp for summarization (falls back to concat if unavailable).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.models import (
    MemoryItem,
    MemoryLayer,
    MemoryScope,
    MemoryType,
)

# Embedding via llama.cpp
from shared.embedding import _ensure_binaries as _ensure_llama, _get_llama_cmd

mcp = FastMCP("autodream")

# ── Configuration ──────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "automem")
DREAM_PATH = os.path.expanduser(os.getenv("DREAM_PATH", str(Path.home() / ".memory" / "dream"))

# LLM for summarization (llama.cpp)
LLAMA_BIN = _get_llama_cmd()
MODEL_PATH = Path(os.environ.get(
    "LLAMA_MODEL_PATH",
    str(Path.home() / "MCP-servers" / "memory-server" / "models" / "embedding.gguf"),
))

# Schedules
PROMOTE_L1_TO_L2 = int(os.getenv("DREAM_PROMOTE_L1", "10"))       # turns
PROMOTE_L2_TO_L3 = int(os.getenv("DREAM_PROMOTE_L2", "3600"))      # seconds (1h)
PROMOTE_L3_TO_L4 = int(os.getenv("DREAM_PROMOTE_L3", "86400"))     # seconds (24h)
PROMOTE_L4_DREAM = int(os.getenv("DREAM_PROMOTE_L4", "604800"))    # seconds (7d)

# ── State tracking ────────────────────────────────────────────────

_state_path = Path(DREAM_PATH) / "state.json"
_state_path.parent.mkdir(parents=True, exist_ok=True)

def _load_state() -> dict:
    if _state_path.exists():
        return json.loads(_state_path.read_text())
    return {
        "last_promote_l1_l2": 0,
        "last_promote_l2_l3": 0,
        "last_promote_l3_l4": 0,
        "last_dream": 0,
        "turn_count": 0,
        "total_consolidated": 0,
        "total_dreams": 0,
    }

def _save_state(state: dict):
    _state_path.write_text(json.dumps(state, indent=2))


# ── Qdrant helpers ─────────────────────────────────────────────────

async def query_memories(layer: MemoryLayer, limit: int = 50, scope: str = "") -> list[dict]:
    """Query memories by layer."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        filter_payload: dict = {
            "must": [
                {"key": "layer", "match": {"value": layer.value}},
            ]
        }
        if scope:
            filter_payload["must"].append({"key": "scope_id", "match": {"value": scope}})

        resp = await client.post(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/scroll",
            json={
                "limit": limit,
                "filter": filter_payload,
                "with_payload": True,
            },
        )
        resp.raise_for_status()
        resp_data = resp.json().get("result", [])
        points = resp_data.get("points", []) if isinstance(resp_data, dict) else resp_data
        return [p["payload"] for p in points if p.get("payload")]


async def update_memory(memory_id: str, updates: dict):
    """Update a memory item in Qdrant."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/{memory_id}")
        if resp.status_code != 200:
            return

        existing = resp.json().get("result", {})
        payload = existing.get("payload", {})
        payload.update(updates)
        payload["updated_at"] = datetime.utcnow().isoformat()

        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={"points": [{"id": memory_id, "vector": existing.get("vector", []), "payload": payload}]},
        )


# ── LLM Summarization (llama.cpp or fallback) ──────────────────────


async def llm_summarize(texts: list[str], prompt: str = "") -> str:
    """Summarize texts using llama.cpp. Falls back to basic concat if unavailable."""
    content = "\n---\n".join(texts[:20])
    if not prompt:
        prompt = (
            "Synthesize the following memories into a concise, coherent summary. "
            "Preserve key decisions, patterns, and facts. Remove redundancy. "
            "Output only the summary, nothing else.\n\n"
        )

    if LLAMA_BIN and MODEL_PATH.exists():
        try:
            # Use llama-cli for text generation if available
            import shutil
            llama_cli = shutil.which("llama-cli") or str(LLAMA_BIN).replace("llama-embedding", "llama-cli")
            if llama_cli and Path(llama_cli).exists():
                result = subprocess.run(
                    [llama_cli, "-m", str(MODEL_PATH), "-p", prompt + content, "-n", "256", "--log-disable"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
        except Exception as e:
            print(f"LLM summarization failed ({e}), using fallback", file=sys.stderr)

    # Fallback: concatenation with numbering
    lines = [f"[{i+1}] {t[:200]}" for i, t in enumerate(texts[:10])]
    return "\n".join(lines)


# ── Consolidation Jobs ─────────────────────────────────────────────


async def promote_l1_to_l2(turn_count: int, state: dict):
    """Working → Episodic: group related steps into episodes."""
    if turn_count - state["last_promote_l1_l2"] < PROMOTE_L1_TO_L2:
        return None

    working = await query_memories(MemoryLayer.WORKING, limit=100)
    if not working:
        return None

    # Group by scope + topic
    groups: dict[str, list] = {}
    for m in working:
        key = f"{m.get('scope_type', '')}/{m.get('scope_id', '')}"
        groups.setdefault(key, []).append(m)

    episodes = []
    for scope_key, items in groups.items():
        if len(items) < 2:
            continue

        combined = "\n".join([f"- {m['content']}" for m in items[:10]])
        avg_importance = sum(m.get("importance", 0) for m in items) / len(items)

        episode = MemoryItem(
            layer=MemoryLayer.EPISODIC,
            scope_type=items[0].get("scope_type", MemoryScope.AGENT),
            scope_id=items[0].get("scope_id", "system"),
            type=MemoryType.EPISODE,
            content=f"Episode ({len(items)} events):\n{combined}",
            importance=avg_importance,
            confidence=0.7,
        )

        async with httpx.AsyncClient() as client:
            await client.put(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
                json={
                    "points": [{
                        "id": episode.memory_id,
                        "vector": items[0].get("embedding", []),
                        "payload": episode.model_dump(mode="json"),
                    }]
                },
            )

        episodes.append(episode.memory_id)

        for m in items:
            await update_memory(m["memory_id"], {"promoted_to": episode.memory_id})

    state["last_promote_l1_l2"] = turn_count
    return f"Created {len(episodes)} episodes from working memory"


async def promote_l2_to_l3(state: dict, now: float):
    """Episodic → Semantic: extract decisions, entities, patterns."""
    if now - state["last_promote_l2_l3"] < PROMOTE_L2_TO_L3:
        return None

    episodes = await query_memories(MemoryLayer.EPISODIC, limit=50)
    if not episodes:
        return None

    texts = [e.get("content", "") for e in episodes]
    summary = await llm_summarize(
        texts,
        prompt=(
            "Extract the key decisions, entities, and reusable patterns from these episodes. "
            "Format as a list of decisions and facts.\n\n"
        ),
    )

    semantic = MemoryItem(
        layer=MemoryLayer.SEMANTIC,
        scope_type=MemoryScope.AGENT,
        scope_id="consolidated",
        type=MemoryType.DECISION,
        content=f"Consolidated decisions from {len(episodes)} episodes:\n\n{summary}",
        importance=0.8,
        confidence=0.75,
    )

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={
                "points": [{
                    "id": semantic.memory_id,
                    "vector": [],
                    "payload": semantic.model_dump(mode="json"),
                }]
            },
        )

    state["last_promote_l2_l3"] = now
    state["total_consolidated"] += 1
    return f"Consolidated {len(episodes)} episodes into semantic memory"


async def promote_l3_to_l4(state: dict, now: float):
    """Semantic → Consolidated: narratives and summaries."""
    if now - state["last_promote_l3_l4"] < PROMOTE_L3_TO_L4:
        return None

    semantic = await query_memories(MemoryLayer.SEMANTIC, limit=30)
    if not semantic:
        return None

    texts = [s.get("content", "") for s in semantic]
    narrative = await llm_summarize(
        texts[:10],
        prompt=(
            "Write a coherent narrative from these memory fragments. "
            "What has been learned? What patterns emerged? What should be remembered?\n\n"
        ),
    )

    consolidated = MemoryItem(
        layer=MemoryLayer.CONSOLIDATED,
        scope_type=MemoryScope.AGENT,
        scope_id="narrative",
        type=MemoryType.NARRATIVE,
        content=narrative,
        importance=0.9,
        confidence=0.6,
    )

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={
                "points": [{
                    "id": consolidated.memory_id,
                    "vector": [],
                    "payload": consolidated.model_dump(mode="json"),
                }]
            },
        )

    state["last_promote_l3_l4"] = now
    state["total_consolidated"] += 1
    return "Created consolidated narrative"


async def dream_cycle(state: dict, now: float):
    """Weekly deep dream — pattern detection across all layers."""
    if now - state["last_dream"] < PROMOTE_L4_DREAM:
        return None

    all_memories = []
    for layer in [MemoryLayer.WORKING, MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC, MemoryLayer.CONSOLIDATED]:
        all_memories.extend(await query_memories(layer, limit=30))

    if not all_memories:
        return None

    dream = await llm_summarize(
        [m.get("content", "") for m in all_memories[:15]],
        prompt=(
            "You are dreaming about everything you've learned. "
            "Find deep patterns, connections, and insights. "
            "What has changed? What surprised you? What should be forgotten?\n\n"
        ),
    )

    dream_item = MemoryItem(
        layer=MemoryLayer.CONSOLIDATED,
        scope_type=MemoryScope.AGENT,
        scope_id="dream",
        type=MemoryType.DREAM,
        content=f"Dream ({datetime.utcnow().isoformat()}):\n\n{dream}",
        importance=0.5,
        confidence=0.4,
    )

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={
                "points": [{
                    "id": dream_item.memory_id,
                    "vector": [],
                    "payload": dream_item.model_dump(mode="json"),
                }]
            },
        )

    state["last_dream"] = now
    state["total_dreams"] += 1
    return "Dream cycle complete"


# ── Public MCP Tools ──────────────────────────────────────────────


@mcp.tool()
async def consolidate(force: bool = False) -> str:
    """Run consolidation across all layers."""
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + 1
    now = datetime.utcnow().timestamp()

    results = []

    r1 = await promote_l1_to_l2(state["turn_count"], state)
    if r1 or force:
        results.append(r1 or "Skipped — not due")

    r2 = await promote_l2_to_l3(state, now)
    if r2 or force:
        results.append(r2 or "Skipped — not due")

    r3 = await promote_l3_to_l4(state, now)
    if r3 or force:
        results.append(r3 or "Skipped — not due")

    _save_state(state)

    return json.dumps({
        "daemon": "AutoDream",
        "status": "consolidation complete",
        "results": results,
        "state": state,
    }, indent=2)


@mcp.tool()
async def dream() -> str:
    """Trigger a deep dream cycle — pattern detection across all memory layers."""
    state = _load_state()
    now = datetime.utcnow().timestamp()

    result = await dream_cycle(state, now)
    _save_state(state)

    return json.dumps({
        "daemon": "AutoDream",
        "status": result or "Skipped — not due for dream cycle",
        "total_dreams": state["total_dreams"],
    }, indent=2)


@mcp.tool()
async def status() -> str:
    """Show AutoDream daemon status and consolidation state."""
    state = _load_state()
    return json.dumps({
        "daemon": "AutoDream",
        "status": "RUNNING",
        "schedule": {
            "L1→L2": f"every {PROMOTE_L1_TO_L2} turns",
            "L2→L3": f"every {PROMOTE_L2_TO_L3}s ({PROMOTE_L2_TO_L3//3600}h)",
            "L3→L4": f"every {PROMOTE_L3_TO_L4}s ({PROMOTE_L3_TO_L4//86400}d)",
            "Dream": f"every {PROMOTE_L4_DREAM}s ({PROMOTE_L4_DREAM//604800}w)",
        },
        "state": state,
        "note": "Daemon runs independently — consolidates even when LLM is disconnected",
    }, indent=2)


@mcp.tool()
async def get_consolidated(scope: str = "") -> str:
    """Get consolidated memories (L4)."""
    memories = await query_memories(MemoryLayer.CONSOLIDATED, limit=20, scope=scope)
    return json.dumps({
        "layer": "L4_CONSOLIDATED",
        "count": len(memories),
        "memories": memories,
    }, indent=2, default=str)


@mcp.tool()
async def get_semantic(scope: str = "") -> str:
    """Get semantic memories (L3)."""
    memories = await query_memories(MemoryLayer.SEMANTIC, limit=20, scope=scope)
    return json.dumps({
        "layer": "L3_SEMANTIC",
        "count": len(memories),
        "memories": memories,
    }, indent=2, default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
