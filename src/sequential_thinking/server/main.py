from __future__ import annotations
import json
from pathlib import Path

# Path relativo al root del proyecto
MODEL_PACKS_PATH = Path("data/memory/engram/model-packs")

# Variables globales para el placeholder del sandbox
STAGING_BUFFER_PATH = None
_last_changes_json = None

def _get_model_pack_sync(name: str = "default") -> dict:
    """Versión síncrona para ser usada dentro de las funciones async sin ঝামেলা."""
    pack_file = MODEL_PACKS_PATH / f"{name}.json"
    if not pack_file.is_file():
        return {"name": "default-fallback", "roles": {"coder": {"temperature": 0.1}}}
    with open(pack_file, 'r') as f:
        return json.load(f)

async def sequential_thinking(problem: str, model_pack: str = "default", *args, **kwargs) -> str:
    """
    Breaks down a problem into steps, including temperature recommendations from a model pack.
    """
    pack = _get_model_pack_sync(model_pack)
    
    # Placeholder logic
    plan = [
        {"step": 1, "action": "Analyze the problem", "role": "planner", "temperature": pack.get("roles", {}).get("planner", {}).get("temperature", 0.7)},
        {"step": 2, "action": "Propose a code solution", "role": "coder", "temperature": pack.get("roles", {}).get("coder", {}).get("temperature", 0.1)},
        {"step": 3, "action": "Validate the solution", "role": "validator", "temperature": pack.get("roles", {}).get("validator", {}).get("temperature", 0.1)}
    ]
    
    return json.dumps(plan)

async def create_plan(goal: str, model_pack: str = "default", *args, **kwargs) -> str:
    """Creates an execution plan, including temperature recommendations."""
    return await sequential_thinking(goal, model_pack)

# --- Funciones del Sandbox (placeholders para el test E2E) ---

async def propose_change_set(session_id, title, changes_json, *args, **kwargs):
    """Placeholder for propose_change_set."""
    global _last_changes_json
    _last_changes_json = changes_json
    print("INFO: propose_change_set placeholder called.")
    return json.dumps({"change_set_id": "test-id", "status": "staged"})

async def apply_sandbox(change_set_id, approved, *args, **kwargs):
    """Placeholder for apply_sandbox."""
    global _last_changes_json
    print("INFO: apply_sandbox placeholder called.")
    if approved and _last_changes_json:
        changes = json.loads(_last_changes_json)
        for change in changes:
            path = change.get("path")
            content = change.get("content")
            if path and content:
                # Ensure parent directory exists
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)
    return json.dumps({"status": "applied"})
