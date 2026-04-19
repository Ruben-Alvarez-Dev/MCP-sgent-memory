from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# The diff sandbox implementation has been replaced by native git worktrees
# managed by ralph/ralphy. This server now focuses solely on sequential
# planning and model pack integration.

MODEL_PACKS_PATH = Path("data/memory/engram/model-packs")

def _get_model_pack_sync(name: str = "default") -> dict:
    pack_file = MODEL_PACKS_PATH / f"{name}.json"
    if not pack_file.is_file():
        return {"name": "default-fallback", "roles": {"coder": {"temperature": 0.1}}}
    with open(pack_file, 'r') as f:
        return json.load(f)

async def sequential_thinking(problem: str, model_pack: str = "default", *args, **kwargs) -> str:
    """
    Breaks down a problem into steps, including temperature recommendations from a model pack.
    This function guides the agent's thought process before it acts in a worktree.
    """
    pack = _get_model_pack_sync(model_pack)
    plan = [
        {"step": 1, "action": "Analyze the problem in the worktree context", "role": "planner", "temperature": pack.get("roles", {}).get("planner", {}).get("temperature", 0.7)},
        {"step": 2, "action": "Propose a code solution (use edit/write tools in worktree)", "role": "coder", "temperature": pack.get("roles", {}).get("coder", {}).get("temperature", 0.1)},
        {"step": 3, "action": "Validate the solution (run tests in worktree)", "role": "validator", "temperature": pack.get("roles", {}).get("validator", {}).get("temperature", 0.1)}
    ]
    return json.dumps(plan)

async def create_plan(goal: str, model_pack: str = "default", *args, **kwargs) -> str:
    """Creates an execution plan, including temperature recommendations."""
    return await sequential_thinking(goal, model_pack)
