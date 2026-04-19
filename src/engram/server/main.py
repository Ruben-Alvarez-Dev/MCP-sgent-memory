from __future__ import annotations
import json
from pathlib import Path
from typing import List

# Path needs to be relative to the server's execution root
ENGRAM_PATH = Path("data/memory/engram")
MODEL_PACKS_PATH = ENGRAM_PATH / "model-packs"

def _load_default_pack() -> dict:
    # Fallback if no pack is found
    return {
        "name": "default-fallback",
        "roles": { "coder": { "temperature": 0.1 } }
    }

async def get_model_pack(name: str = "default") -> str:
    """Reads a JSON model pack and returns it as a JSON string."""
    pack_file = MODEL_PACKS_PATH / f"{name}.json"
    if not pack_file.is_file():
        return json.dumps(_load_default_pack())
    
    with open(pack_file, 'r') as f:
        content = json.load(f)
        return json.dumps(content)

async def list_model_packs() -> str:
    """Lists available model packs."""
    if not MODEL_PACKS_PATH.is_dir():
        return json.dumps([])
    
    packs = [f.stem for f in MODEL_PACKS_PATH.glob("*.json")]
    return json.dumps(packs)

async def set_model_pack(name: str, json_content: str) -> str:
    """Creates or updates a model pack file."""
    if not MODEL_PACKS_PATH.is_dir():
        MODEL_PACKS_PATH.mkdir(parents=True, exist_ok=True)
    
    try:
        # Validate JSON before writing
        json.loads(json_content)
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "message": str(e)})

    pack_file = MODEL_PACKS_PATH / f"{name}.json"
    with open(pack_file, 'w') as f:
        f.write(json_content)
    
    return json.dumps({"status": "saved", "file": str(pack_file)})
