"""Integration tests for conversation_store — real Qdrant + real embeddings.

Requires:
  - Qdrant running on :6333
  - Embedding server running on :8081

Run: PYTHONPATH=src pytest tests/test_conversation_store_integration.py -v
"""
import sys
import os
import json
import pytest
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.env_loader import load_env; load_env()
from shared.conversation_db import save_thread, get_thread, search_fts, set_db_path
from shared.embedding import safe_embed
from shared.qdrant_client import QdrantClient


QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION = "test_conversations"


def _qdrant_available():
    """Check if Qdrant is reachable."""
    import urllib.request
    try:
        req = urllib.request.Request(f"{QDRANT_URL}/healthz", method="GET")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_available(),
    reason="Qdrant not running on :6333"
)


@pytest.fixture(autouse=True)
def setup(tmp_path):
    """Fresh SQLite DB per test. Qdrant cleanup done in test body."""
    db_path = str(tmp_path / "integration_test.db")
    set_db_path(db_path)
    yield


async def _clean_qdrant():
    """Delete test collection from Qdrant."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.delete(f"{QDRANT_URL}/collections/{COLLECTION}")
    except Exception:
        pass


@pytest.fixture
def qdrant():
    return QdrantClient(QDRANT_URL, COLLECTION, 1024)


# ── Embedding integration ──────────────────────────────────────


@pytest.mark.asyncio
async def test_embedding_produces_real_vectors():
    """Embeddings should be non-zero and correct dimension."""
    vec = await safe_embed("SQLite FTS5 full text search")
    assert len(vec) == 1024
    assert any(v != 0 for v in vec), "Vector should not be all zeros"


@pytest.mark.asyncio
async def test_embedding_similar_texts_have_high_similarity():
    """Similar texts should have higher cosine similarity than unrelated texts."""
    import math

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0

    vec1 = await safe_embed("How to implement SQLite FTS5?")
    vec2 = await safe_embed("SQLite full text search implementation")
    vec3 = await safe_embed("The weather is sunny today")

    sim_related = cosine(vec1, vec2)
    sim_unrelated = cosine(vec1, vec3)

    assert sim_related > sim_unrelated, (
        f"Related ({sim_related:.4f}) should be > unrelated ({sim_unrelated:.4f})"
    )


# ── Qdrant integration ─────────────────────────────────────────


@requires_qdrant
@pytest.mark.asyncio
async def test_qdrant_upsert_and_search(qdrant):
    """Should store vector and find it by semantic search."""
    import uuid
    await _clean_qdrant()
    await qdrant.ensure_collection(sparse=True)

    text = "How to use SQLite FTS5 for conversation search"
    vec = await safe_embed(text)
    point_id = str(uuid.uuid4())
    await qdrant.upsert(point_id, vec, {
        "thread_id": "thread-1",
        "summary": "FTS5 discussion",
    })

    # Search with similar query
    query_vec = await safe_embed("full text search SQLite")
    results = await qdrant.search(query_vec, limit=5, score_threshold=0.1)

    assert len(results) >= 1
    found_ids = [r.get("payload", {}).get("thread_id") for r in results]
    assert "thread-1" in found_ids


@requires_qdrant
@pytest.mark.asyncio
async def test_qdrant_multiple_vectors(qdrant):
    """Should distinguish between different topics."""
    import uuid
    await _clean_qdrant()
    await qdrant.ensure_collection(sparse=True)

    topics = [
        ("topic-1", "Python decorators and closures", "Python programming"),
        ("topic-2", "SQLite database optimization", "Database tuning"),
        ("topic-3", "React component lifecycle", "Frontend development"),
    ]

    for tid, text, summary in topics:
        vec = await safe_embed(text)
        await qdrant.upsert(str(uuid.uuid4()), vec, {"thread_id": tid, "summary": summary})

    # Search for Python — should find topic-1 first
    query_vec = await safe_embed("Python programming language")
    results = await qdrant.search(query_vec, limit=3, score_threshold=0.1)

    assert len(results) >= 1
    # The most relevant result should be about Python
    top_result = results[0].get("payload", {}).get("thread_id")
    assert top_result == "topic-1"


# ── Full pipeline: save → embed → store → search ───────────────


@requires_qdrant
@pytest.mark.asyncio
async def test_full_pipeline_save_embed_search(qdrant):
    """Complete flow: save thread → embed summary → store in Qdrant → search."""
    import uuid
    await _clean_qdrant()
    await qdrant.ensure_collection(sparse=True)

    # 1. Save thread in SQLite
    msgs = [
        {"role": "user", "content": "How do I implement SQLite FTS5?"},
        {"role": "assistant", "content": "FTS5 is a virtual table extension..."},
        {"role": "user", "content": "Can you show triggers example?"},
    ]
    save_thread("pipeline-1", msgs, summary="SQLite FTS5 implementation")

    # 2. Embed and store in Qdrant
    summary = "SQLite FTS5 implementation"
    vec = await safe_embed(summary)
    await qdrant.upsert(str(uuid.uuid4()), vec, {
        "thread_id": "pipeline-1",
        "summary": summary,
    })

    # 3. Search semantically
    query_vec = await safe_embed("full text search database")
    results = await qdrant.search(query_vec, limit=5, score_threshold=0.1)

    assert len(results) >= 1
    found = [r for r in results if r.get("payload", {}).get("thread_id") == "pipeline-1"]
    assert len(found) == 1

    # 4. Retrieve full thread from SQLite
    thread = get_thread("pipeline-1")
    assert thread is not None
    assert len(thread["messages"]) == 3
    assert thread["summary"] == "SQLite FTS5 implementation"

    # 5. FTS search also works
    fts_results = search_fts("FTS5 triggers")
    assert len(fts_results) >= 1
    assert fts_results[0]["thread_id"] == "pipeline-1"


@requires_qdrant
@pytest.mark.asyncio
async def test_full_pipeline_multiple_threads(qdrant):
    """Multiple threads with cross-referencing search."""
    import uuid
    await _clean_qdrant()
    await qdrant.ensure_collection(sparse=True)

    threads = [
        ("conv-1", "Discussing Python asyncio patterns", [
            {"role": "user", "content": "How does asyncio work?"},
            {"role": "assistant", "content": "asyncio uses an event loop..."},
        ]),
        ("conv-2", "Database indexing strategies", [
            {"role": "user", "content": "Should I add an index?"},
            {"role": "assistant", "content": "Indexes speed up reads but slow writes..."},
        ]),
        ("conv-3", "Python type hints best practices", [
            {"role": "user", "content": "When to use Optional?"},
            {"role": "assistant", "content": "Use Optional when a value can be None..."},
        ]),
    ]

    for tid, summary, msgs in threads:
        save_thread(tid, msgs, summary=summary)
        vec = await safe_embed(summary)
        await qdrant.upsert(str(uuid.uuid4()), vec, {"thread_id": tid, "summary": summary})

    # Search for Python — should find conv-1 and conv-3
    query_vec = await safe_embed("Python programming")
    results = await qdrant.search(query_vec, limit=5, score_threshold=0.1)

    found_ids = {r.get("payload", {}).get("thread_id") for r in results}
    assert "conv-1" in found_ids or "conv-3" in found_ids

    # Search for database — should find conv-2
    query_vec2 = await safe_embed("database optimization")
    results2 = await qdrant.search(query_vec2, limit=5, score_threshold=0.1)

    found_ids2 = {r.get("payload", {}).get("thread_id") for r in results2}
    assert "conv-2" in found_ids2
