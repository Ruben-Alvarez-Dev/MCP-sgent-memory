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

# ── Bootstrap: find project root dynamically ──────────────────────
_script_dir = Path(__file__).resolve().parent
_project_root = None
for _candidate in [_script_dir] + [_script_dir.parents[i] for i in range(6)]:
    if (_candidate / "shared" / "__init__.py").exists():
        _project_root = _candidate
        break
if _project_root is None:
    _env_dir = os.getenv("MEMORY_SERVER_DIR", "")
    if _env_dir and Path(_env_dir).exists():
        _project_root = Path(_env_dir)
if _project_root and str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.env_loader import load_env
load_env()
from shared.models import (
    MemoryItem,
    MemoryLayer,
    MemoryScope,
    MemoryType,
)

# LLM via shared module (Ollama, LM Studio, or llama.cpp)
from shared.llm import get_llm

# Embedding via shared module
from shared.embedding import get_embedding

mcp = FastMCP("autodream")

async def _embed_text(text: str) -> list[float]:
    """Generate dense embedding with fallback."""
    try:
        return await asyncio.to_thread(get_embedding, text[:2000])
    except Exception:
        return []  # Fallback: empty vector, Qdrant will still store payload


async def llm_summarize(texts: list[str], prompt: str = "") -> str:
    """Summarize texts using the configured LLM backend. Falls back to concat if unavailable."""
    content = "\n---\n".join(texts[:20])
    if not prompt:
        prompt = (
            "Synthesize the following memories into a concise, coherent summary. "
            "Preserve key decisions, patterns, and facts. Remove redundancy. "
            "Output only the summary, nothing else.\n\n"
        )

    try:
        llm = get_llm()
        if llm.is_available():
            response = llm.ask(prompt + content, max_tokens=512, temperature=0.3)
            if response.strip():
                return response.strip()
    except Exception:
        pass  # fallback to concat

    # Fallback: concatenation with numbering
    lines = [f"[{i+1}] {t[:200]}" for i, t in enumerate(texts[:10])]
    return "\n".join(lines)

# ── Configuration ──────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "automem")
DREAM_PATH = Path(os.getenv("DREAM_PATH", str(_project_root / "data" / "memory" / "dream") if _project_root else ""))

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


# ── Consolidation Jobs ─────────────────────────────────────────────


async def promote_l1_to_l2(turn_count: int, state: dict):
    """Working → Episodic: group related steps into episodes."""
    if turn_count - state["last_promote_l1_l2"] < PROMOTE_L1_TO_L2:
        return None
    return await _do_promote_l1_to_l2(state)


async def _force_promote_l1_to_l2(state: dict):
    """Force L1→L2 promotion regardless of thresholds."""
    return await _do_promote_l1_to_l2(state, mark_promoted=True)


async def _do_promote_l1_to_l2(state: dict, mark_promoted: bool = False) -> str | None:

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

        # Generate embedding for the episode
        vector = await _embed_text(episode.content)
        if not vector:
            vector = [0.0] * 1024  # Fallback: zero vector

        async with httpx.AsyncClient() as client:
            await client.put(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
                json={
                    "points": [{
                        "id": episode.memory_id,
                        "vector": vector,
                        "payload": episode.model_dump(mode="json"),
                    }]
                },
            )

        episodes.append(episode.memory_id)

        for m in items:
            await update_memory(m["memory_id"], {"promoted_to": episode.memory_id})

    state["last_promote_l1_l2"] = state.get("turn_count", 0)
    return f"Created {len(episodes)} episodes from working memory" if episodes else None


async def _force_promote_l2_to_l3(state: dict, now: float):
    """Force L2→L3 regardless of time threshold."""
    return await _do_promote_l2_to_l3(state, now)


async def promote_l2_to_l3(state: dict, now: float):
    """Episodic → Semantic: extract decisions, entities, patterns."""
    if now - state["last_promote_l2_l3"] < PROMOTE_L2_TO_L3:
        return None
    return await _do_promote_l2_to_l3(state, now)


async def _do_promote_l2_to_l3(state: dict, now: float) -> str | None:

    episodes = await query_memories(MemoryLayer.EPISODIC, limit=50)
    if not episodes:
        return None

    texts = [e.get("content", "") for e in episodes]
    summary = await llm_summarize(
        texts,
        prompt=(
            "Extract the key decisions, entities, and reusable patterns from these episodes. "
            "For EACH decision or fact, use this exact format:\n\n"
            "[Rule/Decision/Fact]\n"
            "**Why:** [the reason, motivation, or incident that led to this]\n"
            "**How to apply:** [when/where this should be used]\n\n"
            "Only extract items that are NOT derivable from code or git history.\n\n"
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

    vector = await _embed_text(summary)

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={
                "points": [{
                    "id": semantic.memory_id,
                    "vector": vector,
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
            "For each key insight, include:\n"
            "**Why:** [why this matters, what incident or reasoning led here]\n"
            "**How to apply:** [when future agents should use this knowledge]\n\n"
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

    vector = await _embed_text(narrative)

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={
                "points": [{
                    "id": consolidated.memory_id,
                    "vector": vector,
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

    vector = await _embed_text(dream)

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={
                "points": [{
                    "id": dream_item.memory_id,
                    "vector": vector,
                    "payload": dream_item.model_dump(mode="json"),
                }]
            },
        )

    state["last_dream"] = now
    state["total_dreams"] += 1
    return "Dream cycle complete"


async def _mine_diff_patterns() -> str | None:
    """SPEC-6.1: Mine diff events for autoaprendizaje patterns.

    Scans L1 for diff_proposed/diff_accepted/diff_rejected events,
    generates success patterns and anti-patterns, stores in L3.
    """
    # Query diff events from L1 (last 24h)
    diff_memories = []
    try:
        async with httpx.AsyncClient() as client:
            # Search for diff events
            for diff_type in ["diff_accepted", "diff_rejected"]:
                resp = await client.post(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/scroll",
                    json={
                        "filter": {
                            "must": [
                            {"key": "layer", "match": {"value": 1}},
                            {"key": "type", "match": {"value": "fact"}},
                        ]
                        },
                        "limit": 20,
                        "with_payload": True,
                    },
                )
                if resp.status_code == 200:
                    points = resp.json().get("result", {}).get("points", [])
                    for p in points:
                        payload = p.get("payload", {})
                        content = payload.get("content", "")
                        if diff_type in content or payload.get("metadata", {}).get("diff_event") == diff_type:
                            diff_memories.append({
                                "type": diff_type,
                                "content": content[:500],
                                "language": payload.get("metadata", {}).get("language", ""),
                                "file_path": payload.get("metadata", {}).get("file_path", ""),
                            })
    except Exception:
        return None

    if not diff_memories:
        return None

    # Separate into accepted and rejected
    accepted = [d for d in diff_memories if d["type"] == "diff_accepted"]
    rejected = [d for d in diff_memories if d["type"] == "diff_rejected"]

    patterns = []

    # Generate success patterns
    if accepted:
        languages = set(d["language"] for d in accepted if d["language"])
        for lang in languages:
            lang_accepted = [d for d in accepted if d["language"] == lang]
            pattern_item = MemoryItem(
                layer=MemoryLayer.SEMANTIC,
                scope_type=MemoryScope.AGENT,
                scope_id="diff_mining",
                type=MemoryType.PATTERN,
                content=f"SUCCESS PATTERN ({lang}): {len(lang_accepted)} changes accepted in {lang}. "
                        f"Files: {', '.join(set(d['file_path'] for d in lang_accepted))}",
                importance=0.5,
                confidence=0.7,
                metadata={"source": "diff_mining", "pattern_type": "success", "language": lang},
            )
            try:
                vector = await _embed_text(pattern_item.content)
                async with httpx.AsyncClient() as client:
                    await client.put(
                        f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
                        json={"points": [{
                            "id": pattern_item.memory_id,
                            "vector": vector,
                            "payload": pattern_item.model_dump(mode="json"),
                        }]},
                    )
                patterns.append(f"success:{lang}={len(lang_accepted)}")
            except Exception:
                pass

    # Generate anti-patterns
    if rejected:
        pattern_item = MemoryItem(
            layer=MemoryLayer.SEMANTIC,
            scope_type=MemoryScope.AGENT,
            scope_id="diff_mining",
            type=MemoryType.PATTERN,
            content=f"ANTI-PATTERN: {len(rejected)} changes rejected. "
                    f"Reasons: {', '.join(set(d.get('content', '')[:100] for d in rejected[:5]))}",
            importance=0.7,  # Failures are more important
            confidence=0.6,
            metadata={"source": "diff_mining", "pattern_type": "anti_pattern"},
        )
        try:
            vector = await _embed_text(pattern_item.content)
            async with httpx.AsyncClient() as client:
                await client.put(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
                    json={"points": [{
                        "id": pattern_item.memory_id,
                        "vector": vector,
                        "payload": pattern_item.model_dump(mode="json"),
                    }]},
                )
            patterns.append(f"anti-pattern:{len(rejected)} rejections")
        except Exception:
            pass

    if patterns:
        return f"Diff mining: {', '.join(patterns)}"
    return None


# ── Public MCP Tools ──────────────────────────────────────────────


@mcp.tool()
async def heartbeat(agent_id: str = "default", turn_count: int = 1) -> str:
    """Signal that the agent is alive and active.

    Increments turn counter for consolidation scheduling.
    Triggers auto-consolidation if thresholds are met.

    Args:
        agent_id: Identifier for the calling agent.
        turn_count: Number of turns to add (default 1).
    """
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + turn_count
    state["last_heartbeat"] = datetime.utcnow().isoformat()
    state["last_agent"] = agent_id
    _save_state(state)

    # Auto-consolidate if thresholds met
    results = []
    now = datetime.utcnow().timestamp()

    r1 = await promote_l1_to_l2(state["turn_count"], state)
    if r1:
        results.append(r1)

    r2 = await promote_l2_to_l3(state, now)
    if r2:
        results.append(r2)

    r3 = await promote_l3_to_l4(state, now)
    if r3:
        results.append(r3)

    if results:
        _save_state(state)

    return json.dumps({
        "status": "ok",
        "agent_id": agent_id,
        "total_turns": state["turn_count"],
        "consolidation_triggered": len(results) > 0,
        "consolidation_results": results if results else ["No consolidation due"],
    }, indent=2)


@mcp.tool()
async def consolidate(force: bool = False) -> str:
    """Run consolidation across all layers.

    Args:
        force: If true, bypasses all time/turn thresholds and runs all phases.
    """
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + 1
    now = datetime.utcnow().timestamp()

    results = []

    if force:
        # Force all phases regardless of thresholds
        r1 = await _force_promote_l1_to_l2(state)
        results.append(r1 or "L1→L2: nothing to promote")

        r2 = await _force_promote_l2_to_l3(state, now)
        results.append(r2 or "L2→L3: nothing to promote")

        # L3→L4: just call promote_l3_to_l4 with reset state
        state["last_promote_l3_l4"] = 0
        r3 = await promote_l3_to_l4(state, now)
        results.append(r3 or "L3→L4: nothing to promote")
    else:
        r1 = await promote_l1_to_l2(state["turn_count"], state)
        if r1:
            results.append(r1)

        r2 = await promote_l2_to_l3(state, now)
        if r2:
            results.append(r2)

        r3 = await promote_l3_to_l4(state, now)
        if r3:
            results.append(r3)

    _save_state(state)

    # SPEC-6.1: Mine diff patterns for autoaprendizaje
    diff_result = await _mine_diff_patterns()
    if diff_result:
        results.append(diff_result)

    return json.dumps({
        "daemon": "AutoDream",
        "status": "consolidation complete",
        "forced": force,
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
