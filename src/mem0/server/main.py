"""Mem0 Bridge — Semantic Memory (L1 Working) Bridge.

Wraps mem0ai library as MCP server for:
  - add_memory: Store facts, preferences, user knowledge
  - search_memory: Semantic search over stored facts
  - get_all_memories: List all stored memories

If mem0ai is not installed, falls back to direct Qdrant operations.
Embeddings via shared backend.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

_project_root = Path(os.getenv("MEMORY_SERVER_DIR", Path(__file__).resolve().parents[3]))


from shared.env_loader import load_env
load_env()

# Embedding via shared backend
from shared.embedding import get_embedding as llama_embed, async_embed
from shared.sanitize import validate_add_memory, sanitize_text, normalize_query

mcp = FastMCP("mem0")

# ── Configuration ──────────────────────────────────────────────────

DEFAULT_USER = os.getenv("MEM0_USER", "ruben")
MEM0_ENABLED = os.getenv("MEM0_ENABLED", "true").lower() == "true"
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = os.getenv("MEM0_COLLECTION", "mem0_memories")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

# ── Mem0 client (optional) ────────────────────────────────────────

_memory_client = None

def get_mem0_client():
    global _memory_client
    if _memory_client is None and MEM0_ENABLED:
        try:
            from mem0 import Memory
            _memory_client = Memory()
        except ImportError:
            print("mem0ai not installed — falling back to Qdrant direct mode", file=sys.stderr)
    return _memory_client

# ── Helpers ────────────────────────────────────────────────────────

async def ensure_collection():
    async with httpx.AsyncClient() as client:
        cols_resp = await client.get(f"{QDRANT_URL}/collections")
        existing = [c["name"] for c in cols_resp.json().get("result", {}).get("collections", [])]
        if COLLECTION not in existing:
            await client.put(
                f"{QDRANT_URL}/collections/{COLLECTION}",
                json={"vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"},
                    "sparse_vectors": {"text": {"index": {"type": "bm25"}}}},
            )

async def embed_text(text: str) -> list[float]:
    """Generate embedding via configured backend."""
    return await async_embed(text)

# ── Public MCP Tools ──────────────────────────────────────────────

@mcp.tool()
async def add_memory(
    content: str,
    user_id: str = DEFAULT_USER,
    metadata: str = "",
) -> str:
    """Add a semantic memory (fact, preference, user knowledge)."""
    # Sanitize inputs
    clean = validate_add_memory(content, user_id)
    content = clean["content"]
    user_id = clean["user_id"]
    meta = json.loads(metadata) if metadata else {}

    client = get_mem0_client()
    if client:
        result = client.add(content, user_id=user_id, metadata=meta)
        return json.dumps({"status": "stored", "result": str(result), "backend": "mem0"}, indent=2)

    # Fallback: direct Qdrant
    try:
        vector = await embed_text(content)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Embedding failed: {e}", "backend": "qdrant_direct"}, indent=2)

    await ensure_collection()

    point = {
        "id": str(uuid.uuid4()),
        "vector": vector,
        "payload": {
            "content": content,
            "user_id": user_id,
            "metadata": meta,
            "created_at": datetime.utcnow().isoformat(),
            "type": "fact",
            "layer": 1,
        },
    }

    try:
        async with httpx.AsyncClient() as hc:
            resp = await hc.put(
                f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
                json={"points": [point]},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return json.dumps({"status": "error", "message": f"Qdrant error: {resp.status_code} {resp.text}", "backend": "qdrant_direct"}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Connection error: {e}", "backend": "qdrant_direct"}, indent=2)

    return json.dumps({"status": "stored", "point_id": point["id"], "backend": "qdrant_direct"}, indent=2)

@mcp.tool()
async def search_memory(
    query: str,
    user_id: str = DEFAULT_USER,
    limit: int = 10,
) -> str:
    """Search stored semantic memories."""
    # Sanitize inputs
    query = normalize_query(query)
    user_id = sanitize_user_id(user_id) if user_id else DEFAULT_USER

    client = get_mem0_client()
    if client:
        result = client.search(query=query, user_id=user_id, limit=limit)
        return json.dumps({"backend": "mem0", "results": result}, indent=2, default=str)

    vector = await embed_text(query)
    await ensure_collection()

    search_body = {"vector": vector, "limit": limit, "with_payload": True}
    if user_id:
        search_body["filter"] = {"must": [{"key": "user_id", "match": {"value": user_id}}]}

    async with httpx.AsyncClient() as hc:
        resp = await hc.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
            json=search_body,
        )
        resp_data = resp.json().get("result", [])
        points = resp_data if isinstance(resp_data, list) else resp_data.get("result", [])

    results = [
        {
            "score": round(p.get("score", 0), 4),
            "content": p.get("payload", {}).get("content", ""),
            "user_id": p.get("payload", {}).get("user_id"),
            "created_at": p.get("payload", {}).get("created_at"),
        }
        for p in points
    ]

    return json.dumps({"backend": "qdrant_direct", "results": results}, indent=2)

@mcp.tool()
async def get_all_memories(user_id: str = DEFAULT_USER, limit: int = 50) -> str:
    """List all stored memories."""
    client = get_mem0_client()
    if client:
        result = client.get_all(user_id=user_id, limit=limit)
        return json.dumps({"backend": "mem0", "results": result}, indent=2, default=str)

    await ensure_collection()

    scroll_body = {
        "limit": limit,
        "with_payload": True,
    }
    if user_id:
        scroll_body["filter"] = {"must": [{"key": "user_id", "match": {"value": user_id}}]}

    async with httpx.AsyncClient() as hc:
        resp = await hc.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll",
            json=scroll_body,
        )
        resp_data = resp.json().get("result", {})
        points_data = resp_data.get("points", []) if isinstance(resp_data, dict) else resp_data

    results = [
        {
            "id": p["id"],
            "content": p.get("payload", {}).get("content", ""),
            "user_id": p.get("payload", {}).get("user_id"),
            "created_at": p.get("payload", {}).get("created_at"),
        }
        for p in points_data
    ]

    return json.dumps({"backend": "qdrant_direct", "count": len(results), "results": results}, indent=2)

@mcp.tool()
async def delete_memory(memory_id: str, user_id: str = DEFAULT_USER) -> str:
    """Delete a specific memory."""
    client = get_mem0_client()
    if client:
        client.delete(memory_id, user_id=user_id)
        return json.dumps({"status": "deleted", "memory_id": memory_id, "backend": "mem0"}, indent=2)

    return json.dumps({"status": "not_supported", "message": "Direct Qdrant delete not implemented"}, indent=2)

@mcp.tool()
async def status() -> str:
    """Show mem0 status."""
    client = get_mem0_client()
    llama_ok = False
    try:
        from shared.embedding import _get_llama_cmd
        llama_ok = _get_llama_cmd() is not None
    except Exception:
        pass

    return json.dumps({
        "daemon": "mem0",
        "status": "RUNNING",
        "backend": "mem0" if client else "qdrant_direct",
        "llama_cpp": "OK" if llama_ok else "NOT_INSTALLED",
        "mem0_enabled": MEM0_ENABLED,
        "default_user": DEFAULT_USER,
    }, indent=2)

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
