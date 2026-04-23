"""Sequential Thinking — Reasoning Chains & Planning."""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.result_models import ThinkingResult, PlanResult, PlanUpdateResult, ReflectResult, SessionResult, SessionListResult, ChangeSetResult, SequentialThinkingStatusResult
from shared.sanitize import sanitize_text, sanitize_thread_id, validate_json_field, validate_propose_change

config = Config.from_env()
THOUGHTS_PATH = Path(config.thoughts_path) if config.thoughts_path else Path("")
STAGING = Path(config.staging_buffer_path) if config.staging_buffer_path else Path("")
mcp = FastMCP("sequential-thinking")

def _save(sid, step, t):
    d = THOUGHTS_PATH / sid; d.mkdir(parents=True, exist_ok=True)
    (d / f"step_{step:04d}.json").write_text(json.dumps(t, indent=2))

def _load(sid):
    d = THOUGHTS_PATH / sid
    if not d.exists(): return []
    return [json.loads(f.read_text()) for f in sorted(d.glob("step_*.json"))]

def _staging(cid):
    STAGING.mkdir(parents=True, exist_ok=True)
    return STAGING / f"{cid}.json"

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def sequential_thinking(problem: str, context: str = "", max_steps: int = 10, thinking_style: str = "analytical", session_id: str = "") -> ThinkingResult:
    """Step-by-step reasoning chain for complex problems."""
    problem = sanitize_text(problem, max_length=500, field="problem")
    context = sanitize_text(context, max_length=2000, field="context") if context else ""
    sid = sanitize_thread_id(session_id) if session_id else f"think_{uuid.uuid4().hex[:8]}"
    for i in range(min(max_steps, 5)):
        _save(sid, i+1, {"step":i+1,"problem":problem,"thought":f"Step {i+1}: {problem[:100]}","style":thinking_style,"timestamp":datetime.now(timezone.utc).isoformat()})
    return ThinkingResult(session_id=sid, steps=min(max_steps,5), summary=f"Completed {min(max_steps,5)} thinking steps")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def record_thought(session_id: str, thought: str, step: int = 0, confidence: float = 0.5) -> ThinkingResult:
    """Record a single thought step."""
    session_id = sanitize_thread_id(session_id)
    thought = sanitize_text(thought, field="thought")
    existing = _load(session_id)
    ns = step or len(existing) + 1
    _save(session_id, ns, {"step":ns,"thought":thought,"confidence":confidence,"timestamp":datetime.now(timezone.utc).isoformat()})
    return ThinkingResult(session_id=session_id, steps=ns, summary=thought[:200])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def create_plan(title: str, steps_json: str, context: str = "", session_id: str = "") -> PlanResult:
    """Create an execution plan with steps."""
    title = sanitize_text(title, max_length=500, field="title")
    context = sanitize_text(context, max_length=2000, field="context") if context else ""
    steps = validate_json_field(steps_json, field="steps_json")
    sid = sanitize_thread_id(session_id) if session_id else f"plan_{uuid.uuid4().hex[:8]}"
    plan = {"plan_id":sid,"title":title,"context":context,"steps":steps,"status":"created","created_at":datetime.now(timezone.utc).isoformat()}
    d = THOUGHTS_PATH / "plans"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}_plan.json").write_text(json.dumps(plan, indent=2))
    return PlanResult(status="created", plan_id=sid, steps=len(steps))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def update_plan_step(plan_id: str, step_index: int, status: str = "completed", notes: str = "") -> PlanUpdateResult:
    """Update a plan step status."""
    plan_id = sanitize_thread_id(plan_id)
    notes = sanitize_text(notes, max_length=2000, field="notes") if notes else ""
    pf = THOUGHTS_PATH / "plans" / f"{plan_id}_plan.json"
    if not pf.exists(): return PlanUpdateResult(status="plan_not_found")
    plan = json.loads(pf.read_text())
    if step_index < len(plan.get("steps",[])):
        plan["steps"][step_index]["status"] = status
        plan["steps"][step_index]["notes"] = notes
        pf.write_text(json.dumps(plan, indent=2))
        return PlanUpdateResult(status="updated", plan_id=plan_id, step=step_index)
    return PlanUpdateResult(status="step_not_found")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def reflect(session_id: str, focus: str = "quality") -> ReflectResult:
    """Reflect on reasoning quality."""
    session_id = sanitize_thread_id(session_id)
    thoughts = _load(session_id)
    return ReflectResult(status="reflected", session_id=session_id, steps=len(thoughts), summary=f"Session {session_id}: {len(thoughts)} steps")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_thinking_session(session_id: str) -> SessionResult:
    """Retrieve a thinking session."""
    session_id = sanitize_thread_id(session_id)
    thoughts = _load(session_id)
    return SessionResult(session_id=session_id, steps=len(thoughts), thoughts=thoughts)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_thinking_sessions() -> SessionListResult:
    """List recent thinking sessions."""
    if not THOUGHTS_PATH.exists(): return SessionListResult(count=0)
    sessions = [d.name for d in THOUGHTS_PATH.iterdir() if d.is_dir() and d.name != "plans"]
    return SessionListResult(count=len(sessions), sessions=sorted(sessions)[-20:])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def propose_change_set(session_id: str, title: str, changes_json: str = "[]") -> ChangeSetResult:
    """Propose a code change set."""
    clean = validate_propose_change(session_id, title, changes_json)
    cid = f"cs_{uuid.uuid4().hex[:8]}"
    changes = clean["changes"]
    cs = {"change_set_id":cid,"session_id":session_id,"title":title,"changes":changes,"status":"proposed","created_at":datetime.now(timezone.utc).isoformat()}
    _staging(cid).write_text(json.dumps(cs, indent=2))
    return ChangeSetResult(status="proposed", change_set_id=cid, changes=len(changes))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def apply_sandbox(change_set_id: str, dry_run: bool = True) -> dict:
    """Apply changes in sandbox mode."""
    change_set_id = sanitize_thread_id(change_set_id)
    p = _staging(change_set_id)
    if not p.exists(): return {"status":"not_found"}
    cs = json.loads(p.read_text())
    cs["status"] = "applied" if not dry_run else "dry_run"
    p.write_text(json.dumps(cs, indent=2))
    return {"status":cs["status"],"change_set_id":change_set_id}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> SequentialThinkingStatusResult:
    """Show sequential thinking status."""
    b = THOUGHTS_PATH
    sc = sum(1 for d in b.iterdir() if d.is_dir() and d.name != "plans") if b.exists() else 0
    pc = sum(1 for f in (b/"plans").glob("*_plan.json")) if (b/"plans").exists() else 0
    st = sum(1 for _ in STAGING.glob("*.json")) if STAGING.exists() else 0
    return SequentialThinkingStatusResult(daemon="sequential-thinking", status="RUNNING", sessions=sc, plans=pc, staged=st)

def register_tools(target_mcp, _qdrant, target_config, prefix=""):
    global config, THOUGHTS_PATH, STAGING
    config = target_config
    THOUGHTS_PATH = Path(config.thoughts_path) if config.thoughts_path else Path("")
    STAGING = Path(config.staging_buffer_path) if config.staging_buffer_path else Path("")
    for fn in [sequential_thinking,record_thought,create_plan,update_plan_step,reflect,get_thinking_session,list_thinking_sessions,propose_change_set,apply_sandbox,status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()
