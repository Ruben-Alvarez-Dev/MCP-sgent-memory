"""Sequential Thinking + Planner MCP Server.

Implements structured reasoning for complex tasks:
  - sequential_thinking: Break problems into thinking steps
  - planner: Create execution plans with dependencies
  - reflect: Review and improve previous reasoning

Works with the memory system — saves reasoning traces to AutoMem.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

_project_root = Path(os.getenv("MEMORY_SERVER_DIR", Path(__file__).resolve().parents[3]))


from shared.env_loader import load_env
load_env()

mcp = FastMCP("sequential-thinking")

# ── Configuration ──────────────────────────────────────────────────

DEFAULT_USER = os.getenv("DEFAULT_USER", "ruben")
THOUGHTS_PATH = os.getenv(
    "THOUGHTS_PATH",
    str(_project_root / "data" / "memory" / "thoughts") if _project_root else "",
)
STAGING_BUFFER_PATH = Path(
    os.getenv("STAGING_BUFFER", str(_project_root / "data" / "staging_buffer") if _project_root else "")
)

def _detect_lang(file_path: str) -> str:
    """Detect language from file extension."""
    ext_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript",
        ".go": "go", ".rs": "rust", ".java": "java",
        ".rb": "ruby", ".php": "php", ".swift": "swift",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    }
    return ext_map.get(Path(file_path).suffix.lower(), "")

def _save_thought(session: str, step: int, thought: dict):
    """Persist thinking step to filesystem."""
    path = Path(THOUGHTS_PATH) / session
    path.mkdir(parents=True, exist_ok=True)
    (path / f"step_{step:03d}.json").write_text(json.dumps(thought, indent=2))

def _load_session(session: str) -> list[dict]:
    """Load all thinking steps from a session."""
    path = Path(THOUGHTS_PATH) / session
    if not path.exists():
        return []
    steps = []
    for f in sorted(path.glob("step_*.json")):
        steps.append(json.loads(f.read_text()))
    return steps

def _staging_path(change_set_id: str) -> Path:
    STAGING_BUFFER_PATH.mkdir(parents=True, exist_ok=True)
    return STAGING_BUFFER_PATH / f"{change_set_id}.json"

def _load_model_pack_temps(pack_name: str) -> dict:
    """Load temperature recommendations from model pack YAML (SPEC-2.3)."""
    try:
        import yaml
        packs_dir = Path(THOUGHTS_PATH).parent / "engram" / "model-packs"
        pack_path = packs_dir / f"{pack_name}.yaml"
        if not pack_path.exists():
            return {"note": f"Pack '{pack_name}' not found, using defaults"}
        data = yaml.safe_load(pack_path.read_text())
        roles = data.get("roles", {})
        return {
            name: {"temperature": cfg.get("temperature", 0.5), "purpose": cfg.get("purpose", "")}
            for name, cfg in roles.items()
        }
    except Exception:
        return {"note": "Model packs not available"}

# ── Public MCP Tools ──────────────────────────────────────────────

@mcp.tool()
async def sequential_thinking(
    problem: str,
    session_id: str = "default",
    max_steps: int = 10,
    model_pack: str = "default",
) -> str:
    """Break down a complex problem into sequential thinking steps.

    Each step builds on the previous one. Use this before acting
    on complex tasks to ensure thorough reasoning.

    Args:
        problem: The problem or question to think about.
        session_id: Unique session for this thinking trace.
        max_steps: Maximum thinking steps.
        model_pack: Model pack name for temperature recommendations.
    """
    # Load model pack recommendations (SPEC-2.3)
    pack_temps = _load_model_pack_temps(model_pack)
    # Load previous context
    previous = _load_session(session_id)
    context_summary = ""
    if previous:
        last = previous[-1]
        context_summary = f"\nPrevious thinking ({len(previous)} steps):\n"
        context_summary += f"  Last conclusion: {last.get('conclusion', 'N/A')[:200]}\n"

    # Generate thinking framework
    steps = [
        {
            "step": 1,
            "phase": "understand",
            "action": "Define the problem clearly. What exactly are we trying to solve?",
            "question": f"What is the core of: {problem[:200]}?",
            "output": "",
        },
        {
            "step": 2,
            "phase": "decompose",
            "action": "Break the problem into smaller, manageable parts.",
            "question": "What are the sub-problems or components?",
            "output": "",
        },
        {
            "step": 3,
            "phase": "research",
            "action": "What do we already know? Check memory for relevant facts.",
            "question": "What existing knowledge applies here?",
            "output": "",
        },
        {
            "step": 4,
            "phase": "hypothesize",
            "action": "Generate possible approaches or solutions.",
            "question": "What are the possible paths forward?",
            "output": "",
        },
        {
            "step": 5,
            "phase": "evaluate",
            "action": "Evaluate each approach: pros, cons, feasibility.",
            "question": "Which approach is most viable and why?",
            "output": "",
        },
        {
            "step": 6,
            "phase": "plan",
            "action": "Create a concrete action plan for the chosen approach.",
            "question": "What are the specific steps to execute?",
            "output": "",
        },
    ]

    # Limit steps
    steps = steps[:max_steps]

    # Save thinking framework
    for i, step in enumerate(steps):
        step["session_id"] = session_id
        step["problem"] = problem
        step["timestamp"] = datetime.utcnow().isoformat()
        _save_thought(session_id, i + 1, step)

    result = {
        "session_id": session_id,
        "problem": problem,
        "total_steps": len(steps),
        "context_from_previous": context_summary or "No previous thinking in this session",
        "thinking_framework": steps,
        "model_pack_recommendations": pack_temps,
        "instructions": "Fill in each step's 'output' field as you think through the problem. Call sequential_thinking again with session_id to continue.",
    }

    return json.dumps(result, indent=2)

@mcp.tool()
async def record_thought(
    session_id: str,
    step: int,
    conclusion: str,
    confidence: float = 0.5,
    tags: str = "",
) -> str:
    """Record a thinking step's conclusion.

    Args:
        session_id: The thinking session.
        step: Step number.
        conclusion: What you concluded at this step.
        confidence: 0.0-1.0 confidence in this conclusion.
        tags: Comma-separated tags.
    """
    step_data = {
        "step": step,
        "session_id": session_id,
        "conclusion": conclusion,
        "confidence": confidence,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "timestamp": datetime.utcnow().isoformat(),
    }

    _save_thought(session_id, step, step_data)

    # Thinking traces are stored as files and can be ingested by the memory
    # system via the vk-cache retrieval pipeline — no direct coupling needed.

    return json.dumps({
        "status": "recorded",
        "session_id": session_id,
        "step": step,
        "conclusion": conclusion[:100],
        "confidence": confidence,
    }, indent=2)

@mcp.tool()
async def create_plan(
    goal: str,
    session_id: str = "default",
    max_steps: int = 8,
    dependencies: str = "",
) -> str:
    """Create an execution plan from a goal.

    Args:
        goal: What you want to achieve.
        session_id: Session identifier.
        max_steps: Maximum plan steps.
        dependencies: Comma-separated prerequisites.
    """
    dep_list = [d.strip() for d in dependencies.split(",") if d.strip()]

    plan_steps = []
    for i in range(1, max_steps + 1):
        step = {
            "step": i,
            "action": f"Step {i}: [To be defined based on goal]",
            "depends_on": [],
            "estimated_complexity": "medium",
            "status": "pending",
            "result": None,
        }
        # Add dependencies for first steps
        if i <= len(dep_list):
            step["depends_on"].append(f"prereq:{dep_list[i-1]}")
        elif i > 1:
            step["depends_on"].append(f"step:{i-1}")
        plan_steps.append(step)

    plan = {
        "goal": goal,
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "dependencies": dep_list,
        "steps": plan_steps,
        "total_steps": len(plan_steps),
        "critical_path": [s["step"] for s in plan_steps],
    }

    # Save plan
    path = Path(THOUGHTS_PATH) / "plans"
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{session_id}_plan.json").write_text(json.dumps(plan, indent=2))

    return json.dumps(plan, indent=2)

@mcp.tool()
async def update_plan_step(
    session_id: str,
    step: int,
    status: str,
    result: str = "",
) -> str:
    """Update a plan step's status.

    Args:
        session_id: The plan session.
        step: Step number to update.
        status: pending | in_progress | done | blocked | skipped
        result: What was achieved.
    """
    plan_path = Path(THOUGHTS_PATH) / "plans" / f"{session_id}_plan.json"
    if not plan_path.exists():
        return json.dumps({"error": f"Plan not found: {session_id}"}, indent=2)

    plan = json.loads(plan_path.read_text())
    for s in plan.get("steps", []):
        if s["step"] == step:
            s["status"] = status
            s["result"] = result
            s["updated_at"] = datetime.utcnow().isoformat()
            break

    plan_path.write_text(json.dumps(plan, indent=2))

    # Calculate overall progress
    steps = plan.get("steps", [])
    done = sum(1 for s in steps if s.get("status") == "done")
    total = len(steps)
    progress = f"{done}/{total} steps complete"

    return json.dumps({
        "status": "updated",
        "step": step,
        "new_status": status,
        "result": result[:100],
        "progress": progress,
    }, indent=2)

@mcp.tool()
async def reflect(
    session_id: str,
    question: str = "",
) -> str:
    """Review thinking session and identify gaps or improvements.

    Args:
        session_id: The thinking session to review.
        question: Specific aspect to reflect on.
    """
    steps = _load_session(session_id)
    if not steps:
        return json.dumps({"error": f"No thinking steps found: {session_id}"}, indent=2)

    review = {
        "session_id": session_id,
        "total_steps": len(steps),
        "phases_covered": list(set(s.get("phase", "unknown") for s in steps)),
        "confidence_scores": [s.get("confidence", 0) for s in steps if "confidence" in s],
        "gaps": [],
        "recommendations": [],
    }

    # Check for common gaps
    phases = set(s.get("phase", "") for s in steps)
    if "understand" not in phases:
        review["gaps"].append("No problem definition step")
    if "research" not in phases:
        review["gaps"].append("No knowledge retrieval step")
    if "evaluate" not in phases:
        review["gaps"].append("No evaluation of alternatives")
    if "plan" not in phases:
        review["gaps"].append("No action plan created")

    # Confidence analysis
    confidences = review["confidence_scores"]
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
        if avg_conf < 0.5:
            review["recommendations"].append("Low average confidence — consider more research")
        if len(confidences) < 3:
            review["recommendations"].append("Too few conclusions — deepen the analysis")

    if question:
        review["reflection_question"] = question

    return json.dumps(review, indent=2)

@mcp.tool()
async def get_thinking_session(session_id: str) -> str:
    """Get all thinking steps from a session."""
    steps = _load_session(session_id)
    return json.dumps({
        "session_id": session_id,
        "total_steps": len(steps),
        "steps": steps,
    }, indent=2)

@mcp.tool()
async def list_thinking_sessions() -> str:
    """List all thinking sessions."""
    base = Path(THOUGHTS_PATH)
    if not base.exists():
        return json.dumps({"sessions": []}, indent=2)

    sessions = []
    for d in sorted(base.iterdir()):
        if d.is_dir():
            steps = list(d.glob("step_*.json"))
            sessions.append({
                "session_id": d.name,
                "steps": len(steps),
                "last_modified": max(s.stat().st_mtime for s in steps) if steps else 0,
            })

    return json.dumps({"sessions": sessions}, indent=2)

@mcp.tool()
async def propose_change_set(
    session_id: str,
    title: str,
    changes_json: str,
    validate: bool = True,
) -> str:
    """Stage a virtual change set with syntax validation (SPEC-3.3).

    Uses diff_sandbox for validation. Each change is checked for syntax
    errors using Pygments before staging.

    Args:
        session_id: Session identifier.
        title: Human-readable title for the change set.
        changes_json: JSON list of [{path, content, language?}].
        validate: Whether to run syntax validation (default: True).
    """
    changes = json.loads(changes_json)
    if not isinstance(changes, list) or not changes:
        return json.dumps({"error": "changes_json must be a non-empty JSON list"}, indent=2)

    # Validate each change (SPEC-3.3)
    validation_results = []
    if validate:
        try:
            from shared.diff_sandbox import validate_syntax
            for change in changes:
                content = change.get("content", "")
                lang = change.get("language", "") or _detect_lang(change.get("path", ""))
                ok, errors = validate_syntax(content, lang, change.get("path", ""))
                validation_results.append({
                    "path": change.get("path", ""),
                    "syntax_ok": ok,
                    "errors": errors,
                })
        except ImportError:
            pass  # diff_sandbox not available, skip validation

    change_set_id = f"{session_id}-{int(time.time())}"
    payload = {
        "change_set_id": change_set_id,
        "session_id": session_id,
        "title": title,
        "created_at": datetime.utcnow().isoformat(),
        "changes": changes,
        "validation": validation_results,
        "status": "staged",
    }
    _staging_path(change_set_id).write_text(json.dumps(payload, indent=2))

    # Summary
    all_valid = all(v.get("syntax_ok", True) for v in validation_results)
    status_note = "" if all_valid else " ⚠️  Some changes have syntax issues"

    return json.dumps(
        {
            "status": "staged",
            "change_set_id": change_set_id,
            "files": [change.get("path", "") for change in changes],
            "validation": validation_results,
            "all_valid": all_valid,
            "staging_path": str(_staging_path(change_set_id)),
            "note": f"{len(changes)} changes staged{status_note}",
        },
        indent=2,
    )

@mcp.tool()
async def apply_sandbox(
    change_set_id: str,
    approved: bool = False,
) -> str:
    """Apply a staged change set to disk after explicit approval."""
    path = _staging_path(change_set_id)
    if not path.exists():
        return json.dumps({"error": f"Change set not found: {change_set_id}"}, indent=2)
    if not approved:
        return json.dumps({"status": "awaiting_approval", "change_set_id": change_set_id}, indent=2)

    payload = json.loads(path.read_text())
    written: list[str] = []
    for change in payload.get("changes", []):
        target = Path(change["path"]).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.get("content", ""))
        written.append(str(target))

    payload["status"] = "applied"
    payload["applied_at"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(payload, indent=2))

    return json.dumps(
        {
            "status": "applied",
            "change_set_id": change_set_id,
            "written_files": written,
        },
        indent=2,
    )

@mcp.tool()
async def status() -> str:
    """Show sequential-thinking server status."""
    base = Path(THOUGHTS_PATH)
    session_count = sum(1 for d in base.iterdir() if d.is_dir()) if base.exists() else 0
    plan_count = sum(1 for f in (base / "plans").glob("*_plan.json")) if (base / "plans").exists() else 0
    staged_count = sum(1 for _ in STAGING_BUFFER_PATH.glob("*.json")) if STAGING_BUFFER_PATH.exists() else 0

    return json.dumps({
        "daemon": "sequential-thinking",
        "status": "RUNNING",
        "thinking_sessions": session_count,
        "plans": plan_count,
        "staged_change_sets": staged_count,
        "staging_buffer": str(STAGING_BUFFER_PATH),
        "thoughts_path": str(base),
    }, indent=2)

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
