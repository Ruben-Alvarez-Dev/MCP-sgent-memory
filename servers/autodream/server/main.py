"""AutoDream — Consolidation & Dream Daemon."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from shared.env_loader import load_env
load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.models import MemoryItem, MemoryLayer, MemoryScope, MemoryType
from shared.llm import get_llm
from shared.embedding import async_embed, safe_embed
from shared.result_models import HeartbeatResult, ConsolidateResult, DreamResult, LayerResult, AutoDreamStatusResult

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, config.qdrant_collection, config.embedding_dim)
DREAM_PATH = Path(config.dream_path) if config.dream_path else Path("")
_state_path = DREAM_PATH / "state.json"
_state_path.parent.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("autodream")


def _load_state() -> dict:
    if _state_path.exists():
        return json.loads(_state_path.read_text())
    return {"last_promote_l1_l2": 0, "last_promote_l2_l3": 0, "last_promote_l3_l4": 0, "last_dream": 0, "turn_count": 0, "total_consolidated": 0, "total_dreams": 0}

def _save_state(state: dict) -> None:
    _state_path.write_text(json.dumps(state, indent=2))

async def _summarize(texts: list[str], prompt: str = "") -> str:
    content = "\n---\n".join(texts[:20])
    if not prompt:
        prompt = "Synthesize the following memories into a concise summary.\n\n"
    try:
        llm = get_llm()
        if llm.is_available():
            resp = llm.ask(prompt + content, max_tokens=512, temperature=0.3)
            if resp.strip():
                return resp.strip()
    except Exception:
        pass
    return "\n".join(f"[{i+1}] {t[:200]}" for i, t in enumerate(texts[:10]))

async def _promote_l1_l2(state: dict) -> str | None:
    if state["turn_count"] - state.get("last_promote_l1_l2", 0) < config.dream_promote_l1:
        return None
    await qdrant.ensure_collection(sparse=False)
    working = await qdrant.scroll({"must": [{"key": "layer", "match": {"value": 1}}]}, limit=100)
    if not working:
        return None
    groups: dict[str, list] = {}
    for m in working:
        key = f"{m.get('scope_type', '')}/{m.get('scope_id', '')}"
        groups.setdefault(key, []).append(m)
    episodes = []
    for scope_key, items in groups.items():
        if len(items) < 2:
            continue
        combined = "\n".join(f"- {m['content']}" for m in items[:10])
        avg_imp = sum(m.get("importance", 0) for m in items) / len(items)
        ep = MemoryItem(layer=MemoryLayer.EPISODIC, scope_type=items[0].get("scope_type", MemoryScope.AGENT), scope_id=items[0].get("scope_id", "system"), type=MemoryType.EPISODE, content=f"Episode ({len(items)} events):\n{combined}", importance=avg_imp, confidence=0.7)
        vector = await safe_embed(ep.content)
        await qdrant.upsert(ep.memory_id, vector, ep.model_dump(mode="json"))
        episodes.append(ep.memory_id)
    state["last_promote_l1_l2"] = state.get("turn_count", 0)
    return f"Created {len(episodes)} episodes" if episodes else None

async def _promote_l2_l3(state: dict, now: float) -> str | None:
    if now - state.get("last_promote_l2_l3", 0) < config.dream_promote_l2:
        return None
    await qdrant.ensure_collection(sparse=False)
    episodes = await qdrant.scroll({"must": [{"key": "layer", "match": {"value": 2}}]}, limit=50)
    if not episodes:
        return None
    summary = await _summarize([e.get("content", "") for e in episodes], "Extract key decisions, entities, and reusable patterns.\n\n")
    sem = MemoryItem(layer=MemoryLayer.SEMANTIC, scope_type=MemoryScope.AGENT, scope_id="consolidated", type=MemoryType.DECISION, content=f"Consolidated from {len(episodes)} episodes:\n\n{summary}", importance=0.8, confidence=0.75)
    vector = await safe_embed(summary)
    await qdrant.upsert(sem.memory_id, vector, sem.model_dump(mode="json"))
    state["last_promote_l2_l3"] = now
    state["total_consolidated"] = state.get("total_consolidated", 0) + 1
    return f"Consolidated {len(episodes)} episodes"

async def _promote_l3_l4(state: dict, now: float) -> str | None:
    if now - state.get("last_promote_l3_l4", 0) < config.dream_promote_l3:
        return None
    await qdrant.ensure_collection(sparse=False)
    semantic = await qdrant.scroll({"must": [{"key": "layer", "match": {"value": 3}}]}, limit=30)
    if not semantic:
        return None
    narrative = await _summarize([s.get("content", "") for s in semantic], "Write a coherent narrative from these memory fragments.\n\n")
    item = MemoryItem(layer=MemoryLayer.CONSOLIDATED, scope_type=MemoryScope.AGENT, scope_id="narrative", type=MemoryType.NARRATIVE, content=narrative, importance=0.9, confidence=0.6)
    vector = await safe_embed(narrative)
    await qdrant.upsert(item.memory_id, vector, item.model_dump(mode="json"))
    state["last_promote_l3_l4"] = now
    state["total_consolidated"] = state.get("total_consolidated", 0) + 1
    return "Created consolidated narrative"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def heartbeat(agent_id: str = "default", turn_count: int = 1) -> HeartbeatResult:
    """Signal that the agent is alive. Triggers auto-consolidation if thresholds met."""
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + turn_count
    now = datetime.now(timezone.utc).timestamp()
    results = []
    for fn in [_promote_l1_l2, lambda s: _promote_l2_l3(s, now), lambda s: _promote_l3_l4(s, now)]:
        r = await fn(state)
        if r:
            results.append(r)
    if results:
        _save_state(state)
    return HeartbeatResult(status="ok", agent_id=agent_id, turn_count=state["turn_count"], message=", ".join(results) if results else "No consolidation due")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def consolidate(force: bool = False) -> ConsolidateResult:
    """Run consolidation across all layers."""
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + 1
    now = datetime.now(timezone.utc).timestamp()
    results = []
    if force:
        state["last_promote_l1_l2"] = 0
        state["last_promote_l2_l3"] = 0
        state["last_promote_l3_l4"] = 0
    for fn in [_promote_l1_l2, lambda s: _promote_l2_l3(s, now), lambda s: _promote_l3_l4(s, now)]:
        r = await fn(state)
        if r:
            results.append(r)
    _save_state(state)
    return ConsolidateResult(status="consolidation complete", forced=force, results=results)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def dream() -> DreamResult:
    """Trigger a deep dream cycle — pattern detection across all layers."""
    state = _load_state()
    now = datetime.now(timezone.utc).timestamp()
    if now - state.get("last_dream", 0) < config.dream_promote_l4:
        return DreamResult(status="Skipped — not due", total_dreams=state.get("total_dreams", 0))
    all_mem = []
    for layer in [MemoryLayer.WORKING, MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC, MemoryLayer.CONSOLIDATED]:
        all_mem.extend(await qdrant.scroll({"must": [{"key": "layer", "match": {"value": layer.value}}]}, limit=30))
    if not all_mem:
        return DreamResult(status="No memories to dream about", total_dreams=state.get("total_dreams", 0))
    dream_text = await _summarize([m.get("content", "") for m in all_mem[:15]], "You are dreaming. Find deep patterns and insights.\n\n")
    item = MemoryItem(layer=MemoryLayer.CONSOLIDATED, scope_type=MemoryScope.AGENT, scope_id="dream", type=MemoryType.DREAM, content=f"Dream:\n\n{dream_text}", importance=0.5, confidence=0.4)
    vector = await safe_embed(dream_text)
    await qdrant.upsert(item.memory_id, vector, item.model_dump(mode="json"))
    state["last_dream"] = now
    state["total_dreams"] = state.get("total_dreams", 0) + 1
    _save_state(state)
    return DreamResult(status="Dream cycle complete", total_dreams=state["total_dreams"])


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_consolidated(scope: str = "") -> LayerResult:
    """Get consolidated memories (L4)."""
    mems = await qdrant.scroll({"must": [{"key": "layer", "match": {"value": 4}}]}, limit=20)
    return LayerResult(layer="L4_CONSOLIDATED", count=len(mems), memories=mems)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_semantic(scope: str = "") -> LayerResult:
    """Get semantic memories (L3)."""
    mems = await qdrant.scroll({"must": [{"key": "layer", "match": {"value": 3}}]}, limit=20)
    return LayerResult(layer="L3_SEMANTIC", count=len(mems), memories=mems)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> AutoDreamStatusResult:
    """Show AutoDream daemon status."""
    state = _load_state()
    return AutoDreamStatusResult(daemon="AutoDream", status="RUNNING", state=state)


def register_tools(target_mcp: FastMCP, target_qdrant: QdrantClient, target_config: Config, prefix: str = "") -> None:
    global qdrant, config
    qdrant = target_qdrant
    config = target_config
    for fn in [heartbeat, consolidate, dream, get_consolidated, get_semantic, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
