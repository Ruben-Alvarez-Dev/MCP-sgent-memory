from __future__ import annotations
import httpx
import json
from typing import List, Optional

# Add src to pythonpath
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.llm.config import QueryIntent
import shared.retrieval as retrieval
from shared.retrieval.code_map import CodeMap

# --- MCP Server Logic ---

_reminders_path: Optional[Path] = None

def llama_embed(text: str) -> list[float]:
    """Placeholder for llama_embed. In a real scenario, this would call the embedding model."""
    print(f"INFO: llama_embed placeholder called for: {text[:50]}...")
    # The dimension should match the Qdrant collection dimension
    return [0.0] * 384 # A common dimension for small models

# This will be monkeypatched by the test
_llama_embed_func = llama_embed

async def _retrieve_code_maps(query: str, client: httpx.AsyncClient, qdrant_url: str, collection: str) -> List[CodeMap]:
    """Retrieves relevant code maps from Qdrant based on a query."""
    try:
        query_embedding = _llama_embed_func(query)
        
        response = await client.post(
            f"{qdrant_url}/collections/{collection}/points/search",
            json={
                "vector": query_embedding,
                "limit": 5,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "type", "match": {"value": "code_map"}}
                    ]
                }
            },
            timeout=10.0
        )
        response.raise_for_status()
        
        results = response.json().get("result", [])
        return [CodeMap(**point["payload"]) for point in results]
    except Exception as e:
        print(f"ERROR: Failed to retrieve code maps from Qdrant: {e}")
        return []

async def request_context(query: str, intent: str, token_budget: int = 4000, *args, **kwargs) -> str:
    """
    Assembles context for a query using Code Maps for token efficiency.
    This implements SPEC-1.3.
    """
    print(f"INFO: request_context received query: '{query}' with intent: '{intent}'")
    # For now, we assume Qdrant is on localhost and collection is 'automem'
    # These would typically come from config
    qdrant_url = "http://localhost:6333"
    collection = "automem"
    
    injection_text = ""
    sources_used = []

    # In a real implementation, we'd use the monkeypatched client from the test.
    # Here, we create a new one for demonstration.
    async with httpx.AsyncClient() as client:
        # According to SPEC-1.3, logic depends on intent
        if intent in ("code_lookup", "plan", "answer"):
            print("INFO: Intent is code_lookup/plan. Retrieving code maps.")
            code_maps = await _retrieve_code_maps(query, client, qdrant_url, collection)
            
            for code_map in code_maps:
                if len(injection_text) + len(code_map.map_text) > token_budget:
                    break
                injection_text += f"--- Code Map: {code_map.file_path} ---\n"
                injection_text += code_map.map_text + "\n\n"
                sources_used.append(f"code_map:{Path(code_map.file_path).name}")
        else: # Fallback for "debug" or other intents
            print("INFO: Intent is not code_lookup/plan. Placeholder for full file retrieval.")
            injection_text = "Placeholder for full file content for debugging."
            sources_used.append("placeholder:full_file")

    response_payload = {
        "metadata": {"sources_used": sources_used, "tokens_used": len(injection_text.split())},
        "injection_text": injection_text.strip()
    }
    
    return json.dumps(response_payload)


async def push_reminder(*args, **kwargs):
    """Placeholder for push_reminder."""
    print("WARNING: push_reminder is a placeholder.")
    return '{"status": "reminder_pushed"}'

