"""vk-cache — Unified Retrieval & Context Assembly (L5)."""
from __future__ import annotations
import json, math, os
from datetime import datetime, timezone
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.models import ContextPack, ContextReminder, ContextSource
from shared.embedding import async_embed
from shared.retrieval import retrieve as smart_retrieve
from shared.sanitize import validate_request_context, validate_push_reminder, sanitize_text
from shared.result_models import ContextPackResult, ReminderListResult, ReminderPushResult, DismissResult, ContextShiftResult, VkCacheStatusResult

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, config.qdrant_collection, config.embedding_dim)
_reminders_path = Path(config.reminders_path) if config.reminders_path else Path("")
_reminders_path.mkdir(parents=True, exist_ok=True)
mcp = FastMCP("vk-cache")

def _estimate_tokens(t): return len(t) // 4
def _save_reminder(r): (_reminders_path / f"{r.reminder_id}.json").write_text(r.model_dump_json(indent=2))
def _get_reminders(aid): return [ContextReminder(**json.loads(f.read_text())) for f in _reminders_path.glob("*.json")]

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def request_context(query: str, agent_id: str = "default", intent: str = "answer", token_budget: int = 8000, scopes: str = "", mode: str = "standard") -> ContextPackResult:
    """LLM requests context. Returns a ContextPack with smart routing."""
    clean = validate_request_context(query, intent)
    sm = {"answer":"dev","plan":"dev","review":"dev","debug":"ops","study":"docs"}
    pack = await smart_retrieve(query=clean["query"], session_type=sm.get(clean["intent"],"dev"), token_budget=token_budget)
    sources = [ContextSource(scope=s.get("source",""),layer=s.get("level",0),mem_type="",score=s.get("confidence",0),content_preview=s.get("content","")[:500]) for s in pack.sections]
    parts = [f"[{s.get('source','?')}] (conf={s.get('confidence',0):.2f}): {s.get('content','')[:200]}" for s in pack.sections]
    legacy = ContextPack(request_id="",query=clean["query"],sources=sources,summary="\n".join(parts) or "No context found",token_estimate=pack.total_tokens,reason=f"smart_retrieve:{pack.profile}")
    return ContextPackResult(context_pack=legacy.model_dump(mode="json"), injection_text=legacy.to_injection_text())

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def check_reminders(agent_id: str = "default") -> ReminderListResult:
    """Check pending context reminders."""
    rems = _get_reminders(agent_id)
    result = [{"reminder_id":r.reminder_id,"reason":r.reason,"pack":r.pack.to_injection_text()} for r in rems]
    return ReminderListResult(agent_id=agent_id, reminders=result, count=len(result))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def push_reminder(query: str, reason: str = "relevant_to_current_task", agent_id: str = "default") -> ReminderPushResult:
    """System pushes a context reminder to the LLM."""
    clean = validate_push_reminder(query, agent_id)
    vector = await async_embed(clean["query"])
    results = await qdrant.search(vector, limit=5, score_threshold=config.vk_min_score)
    sources = [ContextSource(scope=f"{r.get('payload',{}).get('scope_type','')}/{r.get('payload',{}).get('scope_id','')}",layer=r.get("payload",{}).get("layer",0),mem_type=r.get("payload",{}).get("type",""),score=r.get("score",0),content_preview=r.get("payload",{}).get("content","")[:500]) for r in results]
    summary = "\n".join(f"[{s.layer}][{s.score:.2f}] {s.content_preview}" for s in sources) or "No context found"
    pack = ContextPack(request_id="",query=clean["query"],sources=sources,summary=summary,token_estimate=_estimate_tokens(summary),reason=reason)
    reminder = ContextReminder(pack=pack, reason=reason)
    _save_reminder(reminder)
    return ReminderPushResult(status="reminder_pushed", reminder_id=reminder.reminder_id, sources=len(sources))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
async def dismiss_reminder(reminder_id: str) -> DismissResult:
    """Dismiss a reminder."""
    path = _reminders_path / f"{reminder_id}.json"
    if path.exists(): path.unlink(); return DismissResult(status="dismissed", reminder_id=reminder_id)
    return DismissResult(status="not_found", reminder_id=reminder_id)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def detect_context_shift(current_query: str, previous_query: str = "", agent_id: str = "default") -> ContextShiftResult:
    """Detect if conversation context has shifted domains."""
    if not previous_query: return ContextShiftResult(shift_detected=False)
    try:
        v1, v2 = await async_embed(current_query), await async_embed(previous_query)
        dot = sum(a*b for a,b in zip(v1,v2))
        sim = dot / (math.sqrt(sum(a*a for a in v1)) * math.sqrt(sum(a*a for a in v2))) if v1 and v2 else 0
    except Exception: sim = 0.0
    shifted = sim < 0.7
    new_ctx = ""
    if shifted:
        vec = await async_embed(current_query)
        res = await qdrant.search(vec, limit=5)
        new_ctx = f"{len(res)} sources found"
    return ContextShiftResult(shift_detected=shifted, similarity=round(sim,4), new_context=new_ctx)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> VkCacheStatusResult:
    """Show vk-cache router status."""
    q_ok = await qdrant.health()
    return VkCacheStatusResult(daemon="vk-cache", status="RUNNING", qdrant="OK" if q_ok else "DOWN", active_reminders=len(list(_reminders_path.glob("*.json"))))

def register_tools(target_mcp, target_qdrant, target_config, prefix=""):
    global qdrant, config; qdrant = target_qdrant; config = target_config
    for fn in [request_context, check_reminders, push_reminder, dismiss_reminder, detect_context_shift, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()
