# M7: Embedding imports removed. FTS5-only retrieval.
"""L3_facts — Semantic Memory."""
from __future__ import annotations
import json
from datetime import datetime, UTC
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.memory_db import MemoryDB
from shared.result_models import AddMemoryResult, DismissResult, L3FactsStatusResult, LayerResult, SearchResult
from shared.sanitize import validate_add_memory

config = Config.from_env()
db = MemoryDB(None, "L3_facts", config.embedding_dim)
from shared.identity import bind_identity

IDENTITY = bind_identity()  # M4: strict mode raises here (fail-closed boot, ISO-14)
DEFAULT_USER = "default"
mcp = FastMCP("L3_facts")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def add_memory(content: str, user_id: str = DEFAULT_USER, metadata: str = "") -> AddMemoryResult:
    """Add a semantic memory for a user."""
    clean = validate_add_memory(content, user_id)
    vector = await None
    sparse = None
    import uuid as _uuid
    mid = str(_uuid.uuid4())
    meta = json.loads(metadata) if metadata.strip().startswith("{") else {}
    await db.ensure_collection()
    await db.upsert(mid, {"memory_id":mid,"user_id":clean["user_id"],"content":clean["content"],"metadata":meta,"created_at":datetime.now(UTC).isoformat(),"agent_scope":"shared"}, sparse=sparse)
    return AddMemoryResult(status="stored", memory_id=mid)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def search_memory(query: str, user_id: str = DEFAULT_USER, limit: int = 5, min_score: float = 0.3) -> SearchResult:
    """Search semantic memories for a user."""
    # Validate query — reject empty/garbage input
    query = query.strip()
    if not query or len(query) < 2 or not any(c.isalnum() for c in query):
        return SearchResult(count=0, results=[])
    vector = await None
    results = await db.search(vector, limit=limit, score_threshold=min_score,
                              filter={"must":[{"key":"user_id","match":{"value":user_id}}]})
    hits = [{**r.get("payload",{}), "score": round(r.get("score", 0), 4)} for r in results]
    return SearchResult(count=len(hits), results=hits)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_all_memories(user_id: str = DEFAULT_USER, limit: int = 50) -> LayerResult:
    """Get all memories for a user."""
    results = await db.scroll(filter={"must":[{"key":"user_id","match":{"value":user_id}}]}, limit=limit)
    return LayerResult(layer="semantic", count=len(results), memories=results)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
async def delete_memory(memory_id: str, user_id: str = DEFAULT_USER) -> DismissResult:
    """Delete a memory by ID."""
    # Atomic engine-level delete (id + user_id in ONE statement) — no get-then-check TOCTOU
    deleted = await db.delete(memory_id, filter={"must":[{"key":"user_id","match":{"value":user_id}}]})
    if deleted:
        return DismissResult(status="deleted", reminder_id=memory_id)
    return DismissResult(status="not_found", reminder_id=memory_id)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> L3FactsStatusResult:
    """Show L3_facts status."""
    ok = await db.health()
    count = await db.count() if ok else 0
    return L3FactsStatusResult(daemon="L3_facts", status="RUNNING", memories=count)

def register_tools(target_mcp, target_qdrant, target_config, prefix=""):
    global db, config
    db = MemoryDB(None, "L3_facts", target_config.embedding_dim)
    config = target_config
    for fn in [add_memory, search_memory, get_all_memories, delete_memory, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()


# M6 stub: embedding removed — FTS5-only retrieval