# M7: Embedding imports removed. FTS5-only retrieval.
"""vk-cache — Unified Retrieval & Context Assembly (L5)."""
from __future__ import annotations
import json, logging, re
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.memory_db import MemoryDB
from shared.models import ContextPack, ContextReminder, ContextSource
from shared.result_models import (
    ContextPackResult,
    ContextShiftResult,
    DismissResult,
    ReminderListResult,
    ReminderPushResult,
    VkCacheStatusResult,
)
from shared.retrieval import retrieve as smart_retrieve
from shared.sanitize import validate_push_reminder, validate_request_context
from shared.scope import (
    ScopeError,
    assert_contained,
    normalize_scope,
    scope_dir_hashed,
    visible_dirs_hashed,
)

config = Config.from_env()
store = MemoryDB(None, config.qdrant_collection, config.embedding_dim)
from shared.identity import bind_identity

IDENTITY = bind_identity()  # M4: strict mode raises here (fail-closed boot, ISO-14)
_L5_selective_path = Path(config.L5_selective_path) if config.L5_selective_path else Path("")
_L5_selective_path.mkdir(parents=True, exist_ok=True)
mcp = FastMCP("L5_routing")

logger = logging.getLogger(__name__)

def _estimate_tokens(t): return len(t) // 4


def _token_similarity(a: str, b: str) -> float:
    """Deterministic token-set similarity (Jaccard) for context-shift detection.

    M9: replaces the embedding-cosine of _embed_or_hash (which had degraded to
    `await None` — always raising, silently forcing sim=0). Tokens are
    lowercased alphanumeric words; two empty sets count as identical (1.0).
    """
    ta = set(re.findall(r"[a-z0-9]+", (a or "").lower()))
    tb = set(re.findall(r"[a-z0-9]+", (b or "").lower()))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_REMINDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_migrated_legacy = False

def _sanitize_reminder_id(reminder_id: str) -> str:
    if not isinstance(reminder_id, str) or not _REMINDER_ID_RE.match(reminder_id or ""):
        raise ScopeError(f"invalid reminder_id: {reminder_id!r}")
    return reminder_id

def _migrate_legacy_reminders() -> int:
    """One-time move of root-level *.json into the shared namespace dir.

    Legacy files were world-readable by design accident; their historical
    visibility was public, so shared/ is the honest destination.
    """
    global _migrated_legacy
    if _migrated_legacy:
        return 0
    _migrated_legacy = True
    moved = 0
    if not _L5_selective_path.is_dir():
        return 0
    dest = scope_dir_hashed(_L5_selective_path, "shared")
    for f in sorted(_L5_selective_path.glob("*.json")):
        if not f.is_file():
            continue
        try:
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / f.name
            if not target.exists():
                f.rename(target)
                moved += 1
        except OSError:
            continue
    return moved

def _save_reminder(r, scope: str = "shared"):
    _migrate_legacy_reminders()
    d = scope_dir_hashed(_L5_selective_path, scope)
    d.mkdir(parents=True, exist_ok=True)
    fp = assert_contained(d / f"{_sanitize_reminder_id(r.reminder_id)}.json", _L5_selective_path)
    fp.write_text(r.model_dump_json(indent=2))

def _get_reminders(agent_id):
    """ISO-03 enforced: read ONLY own scope dir + shared dir. Never siblings."""
    _migrate_legacy_reminders()
    scope = normalize_scope(agent_id)
    out = []
    for d in visible_dirs_hashed(_L5_selective_path, scope):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                assert_contained(f, _L5_selective_path)
                out.append(ContextReminder(**json.loads(f.read_text())))
            except (OSError, ValueError):
                continue
    return out

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def request_context(query: str, agent_id: str = "shared", intent: str = "answer", token_budget: int = 8000, scopes: str = "", mode: str = "standard") -> ContextPackResult:
    """LLM requests context. Returns a ContextPack with smart routing."""
    agent_id = IDENTITY.assert_agent(agent_id)  # M4: identity gate before I/O
    clean = validate_request_context(query, intent)
    sm = {"answer":"dev","plan":"dev","review":"dev","debug":"ops","study":"docs"}
    pack = await smart_retrieve(query=clean["query"], session_type=sm.get(clean["intent"],"dev"), token_budget=token_budget, agent_scope=agent_id)
    sources = [ContextSource(scope=s.get("source",""),layer=s.get("level",0),mem_type="",score=s.get("confidence",0),content_preview=s.get("content","")[:500]) for s in pack.sections]
    parts = [f"[{s.get('source','?')}] (conf={s.get('confidence',0):.2f}): {s.get('content','')[:200]}" for s in pack.sections]
    legacy = ContextPack(request_id="",query=clean["query"],sources=sources,summary="\n".join(parts) or "No context found",token_estimate=pack.total_tokens,reason=f"smart_retrieve:{pack.profile}")
    return ContextPackResult(context_pack=legacy.model_dump(mode="json"), injection_text=legacy.to_injection_text())

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def check_reminders(agent_id: str = "default") -> ReminderListResult:
    """Check pending context reminders."""
    agent_id = IDENTITY.assert_agent(agent_id)
    rems = _get_reminders(agent_id)
    result = [{"reminder_id":r.reminder_id,"reason":r.reason,"pack":r.pack.to_injection_text()} for r in rems]
    return ReminderListResult(agent_id=agent_id, reminders=result, count=len(result))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def push_reminder(query: str, reason: str = "relevant_to_current_task", agent_id: str = "default") -> ReminderPushResult:
    """System pushes a context reminder to the LLM."""
    # Raw scope first: sanitize_user_id would remap traversal instead of
    # rejecting it — strict validation before any sanitization.
    agent_id = IDENTITY.assert_agent(agent_id)  # M4: identity gate before I/O
    scope = normalize_scope(agent_id)
    clean = validate_push_reminder(query, scope)
    # M9: FTS5-only engine search — the query text IS the retrieval signal
    # (was: _embed_or_hash → `await None` TypeError → silent empty results).
    # M2: engine-level scope filter (own + shared) — was per-scope collection name
    results = await store.search(
        clean["query"], limit=5,
        filter={"must": [{"key": "agent_scope", "match": {"any": [scope, "shared"] if scope != "shared" else ["shared"]}}]},
    )
    sources = [ContextSource(scope=f"{r.get('payload',{}).get('scope_type','')}/{r.get('payload',{}).get('scope_id','')}",layer=r.get("payload",{}).get("layer",0),mem_type=r.get("payload",{}).get("type",""),score=r.get("score",0),content_preview=r.get("payload",{}).get("content","")[:500]) for r in results]
    summary = "\n".join(f"[{s.layer}][{s.score:.2f}] {s.content_preview}" for s in sources) or "No context found"
    pack = ContextPack(request_id="",query=clean["query"],sources=sources,summary=summary,token_estimate=_estimate_tokens(summary),reason=reason)
    reminder = ContextReminder(pack=pack, reason=reason)
    _save_reminder(reminder, scope)
    return ReminderPushResult(status="reminder_pushed", reminder_id=reminder.reminder_id, sources=len(sources))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
async def dismiss_reminder(reminder_id: str, agent_id: str = "shared") -> DismissResult:
    """Dismiss a reminder (scoped: only own + shared namespaces are searched)."""
    agent_id = IDENTITY.assert_agent(agent_id)  # M4: identity gate before I/O
    rid = _sanitize_reminder_id(reminder_id)
    scope = normalize_scope(agent_id)
    for d in visible_dirs_hashed(_L5_selective_path, scope):
        path = d / f"{rid}.json"
        try:
            assert_contained(path, _L5_selective_path)
        except ScopeError:
            continue
        if path.exists():
            path.unlink()
            return DismissResult(status="dismissed", reminder_id=reminder_id)
    return DismissResult(status="not_found", reminder_id=reminder_id)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def detect_context_shift(current_query: str, previous_query: str = "", agent_id: str = "default") -> ContextShiftResult:
    """Detect if conversation context has shifted domains."""
    agent_id = IDENTITY.assert_agent(agent_id)  # M4: identity gate before I/O
    if not previous_query: return ContextShiftResult(shift_detected=False)
    # M9: deterministic token similarity (was: embedding cosine that silently
    # degraded to sim=0.0 on every call since M7).
    sim = _token_similarity(current_query, previous_query)
    shifted = sim < 0.7
    new_ctx = ""
    if shifted:
        scope = normalize_scope(agent_id)
        res = await store.search(
            current_query, limit=5,
            filter={"must": [{"key": "agent_scope", "match": {"any": [scope, "shared"] if scope != "shared" else ["shared"]}}]},
        )
        new_ctx = f"{len(res)} sources found"
    return ContextShiftResult(shift_detected=shifted, similarity=round(sim,4), new_context=new_ctx)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> VkCacheStatusResult:
    """Show vk-cache router status."""
    q_ok = await store.health()
    return VkCacheStatusResult(daemon="vk-cache", status="RUNNING", storage="memory.db" if q_ok else "ERROR", active_reminders=len(list(_L5_selective_path.glob("*.json"))))

def register_tools(target_mcp, target_qdrant, target_config, prefix=""):
    global store, config
    store = target_qdrant if isinstance(target_qdrant, MemoryDB) else MemoryDB(None, target_config.qdrant_collection, target_config.embedding_dim)
    config = target_config
    for fn in [request_context, check_reminders, push_reminder, dismiss_reminder, detect_context_shift, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()


# M6 stub