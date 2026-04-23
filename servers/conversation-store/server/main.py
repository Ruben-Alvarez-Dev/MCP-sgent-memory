"""Conversation Store — Thread persistence and search."""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.embedding import async_embed, safe_embed, bm25_tokenize
from shared.sanitize import validate_save_conversation
from shared.result_models import MemorizeResult as SaveConversationResult, SearchResult, ThreadListResult, ConversationStatusResult

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, "conversations", config.embedding_dim)
mcp = FastMCP("conversation-store")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def save_conversation(thread_id: str, messages_json: str, summary: str = "") -> SaveConversationResult:
    """Save a conversation thread."""
    clean = validate_save_conversation(thread_id, messages_json)
    text = summary or str(clean["messages"][:500])
    vector = await safe_embed(text)
    sparse = bm25_tokenize(text)
    await qdrant.ensure_collection(sparse=True)
    await qdrant.upsert(str(uuid.uuid4()), vector, {"thread_id":clean["thread_id"],"messages":clean["messages"],"summary":summary,"created_at":datetime.now(timezone.utc).isoformat()}, sparse=sparse)
    return SaveConversationResult(status="saved", memory_id=clean["thread_id"], layer="conversations", scope="thread")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_conversation(thread_id: str) -> dict:
    """Retrieve a conversation thread by ID."""
    point = await qdrant.get(thread_id)
    return point.get("payload", {}) if point else {"status":"not_found","thread_id":thread_id}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def search_conversations(query: str, limit: int = 5) -> SearchResult:
    """Search conversations by semantic similarity."""
    vector = await safe_embed(query)
    results = await qdrant.search(vector, limit=limit)
    return SearchResult(count=len(results), results=[r.get("payload",{}) for r in results])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_threads(limit: int = 20) -> ThreadListResult:
    """List recent conversation threads."""
    results = await qdrant.scroll(limit=limit)
    return ThreadListResult(count=len(results), threads=results)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> ConversationStatusResult:
    """Show conversation store status."""
    ok = await qdrant.health()
    count = await qdrant.count() if ok else 0
    return ConversationStatusResult(daemon="conversation-store", status="RUNNING", threads=count)

def register_tools(target_mcp, target_qdrant, target_config, prefix=""):
    global qdrant, config
    qdrant = QdrantClient(target_config.qdrant_url, "conversations", target_config.embedding_dim)
    config = target_config
    for fn in [save_conversation, get_conversation, search_conversations, list_threads, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()
