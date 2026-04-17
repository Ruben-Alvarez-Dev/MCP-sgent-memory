"""Conversation Store — Thread Recording MCP Server.

Stores full conversation threads with semantic embeddings in Qdrant.
Works independently of the LLM — captures conversations as they happen.
Embeddings via llama.cpp (self-contained).
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

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Embedding via llama.cpp
from shared.embedding import get_embedding as llama_embed, _ensure_binaries as _ensure_llama

mcp = FastMCP("conversation-store")

# ── Configuration ──────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = os.getenv("CONV_COLLECTION", "conversations")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))


# ── Helpers ────────────────────────────────────────────────────────

async def ensure_collection():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{QDRANT_URL}/collections")
        existing = [c["name"] for c in resp.json().get("result", {}).get("collections", [])]
        if COLLECTION not in existing:
            await client.put(
                f"{QDRANT_URL}/collections/{COLLECTION}",
                json={"vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"},
                    "sparse_vectors": {"text": {"index": {"type": "bm25"}}}},
            )


async def embed_text(text: str) -> list[float]:
    """Generate embedding via llama.cpp."""
    _ensure_llama()
    return await asyncio.to_thread(llama_embed, text)


# ── Public MCP Tools ──────────────────────────────────────────────


@mcp.tool()
async def save_conversation(
    thread_id: str,
    messages_json: str,
    metadata: str = "",
) -> str:
    """Save a conversation thread with semantic embedding.

    Args:
        thread_id: Unique thread identifier.
        messages_json: JSON array of messages [{"role": "user", "content": "..."}, ...]
        metadata: Optional JSON metadata.
    """
    await ensure_collection()

    messages = json.loads(messages_json)
    meta = json.loads(metadata) if metadata else {}
    text_content = json.dumps(messages, ensure_ascii=False)
    vector = await embed_text(text_content)

    point = {
        "id": str(uuid.uuid4()),
        "vector": vector,
        "payload": {
            "thread_id": thread_id,
            "messages": messages,
            "metadata": meta,
            "created_at": datetime.utcnow().isoformat(),
            "message_count": len(messages),
        },
    }

    async with httpx.AsyncClient() as client:
        await client.put(
            f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
            json={"points": [point]},
        )

    return json.dumps({"status": "saved", "thread_id": thread_id, "point_id": point["id"]}, indent=2)


@mcp.tool()
async def get_conversation(thread_id: str) -> str:
    """Get a conversation by thread_id."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll",
            json={
                "filter": {"must": [{"key": "thread_id", "match": {"value": thread_id}}]},
                "limit": 1,
                "with_payload": True,
            },
        )
        resp.raise_for_status()
        resp_data = resp.json().get("result", [])
        points = resp_data.get("points", []) if isinstance(resp_data, dict) else resp_data
        if not points:
            return json.dumps({"error": f"Thread {thread_id} not found"}, indent=2)

        payload = points[0].get("payload", {})
        return json.dumps({
            "thread_id": thread_id,
            "messages": payload.get("messages", []),
            "metadata": payload.get("metadata", {}),
            "created_at": payload.get("created_at"),
            "message_count": payload.get("message_count", 0),
        }, indent=2)


@mcp.tool()
async def search_conversations(query: str, limit: int = 5) -> str:
    """Search conversations semantically."""
    vector = await embed_text(query)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
            json={
                "vector": vector,
                "limit": limit,
                "with_payload": True,
            },
        )
        resp.raise_for_status()
        resp_data = resp.json().get("result", [])
        points = resp_data if isinstance(resp_data, list) else resp_data.get("result", [])

        results = []
        for p in points:
            payload = p.get("payload", {})
            results.append({
                "score": round(p.get("score", 0), 4),
                "thread_id": payload.get("thread_id"),
                "message_count": payload.get("message_count", 0),
                "created_at": payload.get("created_at"),
                "preview": json.dumps(payload.get("messages", [])[:2], ensure_ascii=False)[:300],
            })

        return json.dumps({"query": query, "results": results}, indent=2)


@mcp.tool()
async def list_threads(limit: int = 20) -> str:
    """List recent conversation threads."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll",
            json={"limit": limit, "with_payload": True},
        )
        resp.raise_for_status()
        resp_data = resp.json().get("result", [])
        points = resp_data.get("points", []) if isinstance(resp_data, dict) else resp_data

        threads = []
        for p in points:
            payload = p.get("payload", {})
            threads.append({
                "thread_id": payload.get("thread_id"),
                "message_count": payload.get("message_count", 0),
                "created_at": payload.get("created_at"),
            })

        return json.dumps({"threads": threads, "total": len(threads)}, indent=2)


@mcp.tool()
async def status() -> str:
    """Show conversation store status."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{QDRANT_URL}/collections/{COLLECTION}")
            count = resp.json().get("result", {}).get("points_count", 0)
            return json.dumps({"status": "OK", "collection": COLLECTION, "threads": count}, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "error": str(e)}, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
