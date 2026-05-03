"""mem0 — Semantic Memory (Mem0-compatible interface)."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.embedding import async_embed, safe_embed, bm25_tokenize
from shared.sanitize import validate_add_memory
from shared.result_models import AddMemoryResult, SearchResult, LayerResult as Mem0ListResult, DismissResult as DeleteResult, Mem0StatusResult

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, "mem0_memories", config.embedding_dim)
DEFAULT_USER = "default"
mcp = FastMCP("L3_facts")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def add_memory(content: str, user_id: str = DEFAULT_USER, metadata: str = "") -> AddMemoryResult:
    """Add a semantic memory for a user."""
    clean = validate_add_memory(content, user_id)
    vector = await safe_embed(clean["content"])
    sparse = bm25_tokenize(clean["content"])
    import uuid as _uuid
    mid = str(_uuid.uuid4())
    meta = json.loads(metadata) if metadata.strip().startswith("{") else {}
    await qdrant.ensure_collection(sparse=True)
    await qdrant.upsert(mid, vector, {"memory_id":mid,"user_id":clean["user_id"],"content":clean["content"],"metadata":meta,"created_at":datetime.now(timezone.utc).isoformat()}, sparse=sparse)
    return AddMemoryResult(status="stored", memory_id=mid)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def search_memory(query: str, user_id: str = DEFAULT_USER, limit: int = 5, min_score: float = 0.3) -> SearchResult:
    """Search semantic memories for a user."""
    # Validate query — reject empty/garbage input
    query = query.strip()
    if not query or len(query) < 2 or not any(c.isalnum() for c in query):
        return SearchResult(count=0, results=[])
    vector = await safe_embed(query)
    results = await qdrant.search(vector, limit=limit, score_threshold=min_score)
    filtered = [{**r.get("payload",{}), "score": round(r.get("score", 0), 4)} for r in results if r.get("payload",{}).get("user_id") == user_id]
    return SearchResult(count=len(filtered), results=filtered)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_all_memories(user_id: str = DEFAULT_USER, limit: int = 50) -> Mem0ListResult:
    """Get all memories for a user."""
    results = await qdrant.scroll({"must":[{"key":"user_id","match":{"value":user_id}}]}, limit=limit)
    return Mem0ListResult(layer="semantic", count=len(results), memories=results)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
async def delete_memory(memory_id: str, user_id: str = DEFAULT_USER) -> DeleteResult:
    """Delete a memory by ID."""
    point = await qdrant.get(memory_id)
    if point and point.get("payload",{}).get("user_id") == user_id:
        deleted = await qdrant.delete(memory_id)
        if deleted:
            return DeleteResult(status="deleted", reminder_id=memory_id)
        return DeleteResult(status="delete_failed", reminder_id=memory_id)
    return DeleteResult(status="not_found")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> Mem0StatusResult:
    """Show mem0 status."""
    ok = await qdrant.health()
    count = await qdrant.count() if ok else 0
    return Mem0StatusResult(daemon="mem0", status="RUNNING", memories=count)

def register_tools(target_mcp, target_qdrant, target_config, prefix=""):
    global qdrant, config
    qdrant = QdrantClient(target_config.qdrant_url, "mem0_memories", target_config.embedding_dim)
    config = target_config
    for fn in [add_memory, search_memory, get_all_memories, delete_memory, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()
