"""Conversation Store — Thread persistence and search.

Architecture:
    SQLite + FTS5  → raw storage, exact retrieval, full-text search
    Qdrant         → semantic search only (vectors)
    Both linked by thread_id.

Multi-agent isolation:
    agent_scope="shared"     → visible to all agents (default)
    agent_scope="director-1" → visible only to director-1
    agent_scope="engineer-3" → visible only to engineer-3
    Search: scope own + shared
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.embedding import safe_embed, bm25_tokenize
from shared.sanitize import validate_save_conversation
from shared.conversation_db import save_thread, get_thread, search_fts, list_threads as db_list_threads, thread_count
from shared.result_models import SaveConversationResult, SearchResult, ThreadListResult, ConversationStatusResult

logger = logging.getLogger(__name__)

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, "conversations", config.embedding_dim)
mcp = FastMCP("conversation-store")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def save_conversation(
    thread_id: str,
    messages_json: str,
    summary: str = "",
    agent_scope: str = "shared",
) -> SaveConversationResult:
    """Save a conversation thread.

    Stores full messages in SQLite (exact retrieval + FTS5 search).
    Stores vector in Qdrant (semantic search only).

    Args:
        thread_id: Unique thread identifier.
        messages_json: JSON array of messages [{"role": str, "content": str}, ...].
        summary: Optional summary for embedding/search.
        agent_scope: Scope for multi-agent isolation. Default "shared" (visible to all).
                     Use agent-specific scope like "director-1" for private threads.
    """
    clean = validate_save_conversation(thread_id, messages_json)
    messages = clean["messages"]

    # 1. SQLite — full messages + metadata + scope (primary storage)
    save_thread(clean["thread_id"], messages, summary, agent_scope=agent_scope)

    # 2. Qdrant — vector for semantic search (best-effort, non-blocking)
    try:
        text_for_embedding = summary or " ".join(
            m.get("content", "") for m in messages[:5]
        )[:2000]
        vector = await safe_embed(text_for_embedding)
        sparse = bm25_tokenize(text_for_embedding)
        await qdrant.ensure_collection(sparse=True)
        # Deterministic UUID from thread_id — same thread always gets same point ID
        # This prevents duplicates when saving the same thread multiple times
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"conv:{clean['thread_id']}"))
        await qdrant.upsert(
            point_id,
            vector,
            {
                "thread_id": clean["thread_id"],
                "summary": summary,
                "agent_scope": agent_scope,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            sparse=sparse,
        )
    except Exception as e:
        logger.warning(
            "Qdrant upsert failed for thread %s (SQLite saved OK): %s",
            clean["thread_id"], e
        )

    return SaveConversationResult(
        status="saved",
        thread_id=clean["thread_id"],
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_conversation(thread_id: str) -> dict:
    """Retrieve a conversation thread by ID.

    Returns full messages from SQLite (not Qdrant).
    """
    result = get_thread(thread_id)
    if result:
        return result
    return {"status": "not_found", "thread_id": thread_id}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def search_conversations(
    query: str,
    limit: int = 5,
    min_score: float = 0.3,
    agent_scope: str | None = None,
) -> SearchResult:
    """Search conversations by semantic similarity + full-text search.

    Merges Qdrant (semantic) and SQLite FTS5 (text) results.
    Deduplicates by thread_id, keeps best score.

    Args:
        query: Search query.
        limit: Max results.
        min_score: Minimum semantic similarity score.
        agent_scope: If set, filter to this scope + "shared". None = all scopes.
    """
    # 1. Semantic search via Qdrant (with scope filter)
    vector = await safe_embed(query)
    qdrant_filter = None
    if agent_scope:
        qdrant_filter = {
            "should": [
                {"key": "agent_scope", "match": {"value": agent_scope}},
                {"key": "agent_scope", "match": {"value": "shared"}},
            ]
        }
    qdrant_results = []
    try:
        qdrant_results = await qdrant.search(
            vector, limit=limit, score_threshold=min_score, filter=qdrant_filter
        )
    except Exception as e:
        logger.warning("Qdrant semantic search failed (using FTS5 only): %s", e)

    # 2. Full-text search via SQLite FTS5 (with scope filter)
    fts_results = search_fts(query, limit=limit, agent_scope=agent_scope)

    # 3. Merge — Qdrant results first, then FTS5 for threads not already found
    seen = set()
    merged = []

    for r in qdrant_results:
        payload = r.get("payload", {})
        tid = payload.get("thread_id", "")
        if tid and tid not in seen:
            seen.add(tid)
            merged.append({
                "thread_id": tid,
                "summary": payload.get("summary", ""),
                "score": round(r.get("score", 0), 4),
                "match_type": "semantic",
            })

    for r in fts_results:
        tid = r.get("thread_id", "")
        if tid and tid not in seen:
            seen.add(tid)
            merged.append({
                "thread_id": tid,
                "summary": r.get("summary", ""),
                "snippet": r.get("snippet", ""),
                "score": 0.0,
                "match_type": "fts",
            })

    return SearchResult(count=len(merged), results=merged[:limit])


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_threads(
    limit: int = 20,
    agent_scope: str | None = None,
) -> ThreadListResult:
    """List recent conversation threads ordered by last update.

    Args:
        limit: Max threads to return.
        agent_scope: If set, filter to this scope + "shared". None = all scopes.
    """
    threads = db_list_threads(limit=limit, agent_scope=agent_scope)
    return ThreadListResult(count=len(threads), threads=threads)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> ConversationStatusResult:
    """Show conversation store status."""
    ok = await qdrant.health()
    count = thread_count()
    return ConversationStatusResult(
        daemon="conversation-store",
        status="RUNNING",
        threads=count,
    )


def register_tools(target_mcp, target_qdrant, target_config, prefix=""):
    global qdrant, config
    qdrant = QdrantClient(target_config.qdrant_url, "conversations", target_config.embedding_dim)
    config = target_config
    for fn in [save_conversation, get_conversation, search_conversations, list_threads, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")


def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()
