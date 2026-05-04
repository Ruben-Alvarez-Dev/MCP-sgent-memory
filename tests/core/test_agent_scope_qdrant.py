"""Tests for Fase 2B (ScopedQdrantClient) and Fase 2C (HybridQdrantClient).

Tests the collection-per-agent and hybrid approaches.
Skipped if Qdrant not running.
"""
import sys
import os
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.scoped_qdrant import ScopedQdrantClient
from shared.hybrid_qdrant import HybridQdrantClient, _parse_agent_level, LEVEL_MAP


QDRANT_URL = "http://127.0.0.1:6333"


def _qdrant_available():
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


# ── Fase 2B: ScopedQdrantClient ─────────────────────────────────


@requires_qdrant
@pytest.mark.asyncio
async def test_scoped_creates_separate_collections():
    """Each agent scope should get its own collection."""
    client = ScopedQdrantClient(QDRANT_URL, "test_scoped", 1024)
    await client.ensure_collection("director-1")
    await client.ensure_collection("engineer-1")
    await client.ensure_collection("shared")

    # Each should have its own collection
    assert await client.count("director-1") == 0
    assert await client.count("engineer-1") == 0
    assert await client.count("shared") == 0


@requires_qdrant
@pytest.mark.asyncio
async def test_scoped_isolates_agents():
    """Director-1 should not see engineer-1's data."""
    import httpx
    import uuid

    client = ScopedQdrantClient(QDRANT_URL, "test_scoped_iso", 1024)
    await client.ensure_collection("director-1")
    await client.ensure_collection("engineer-1")
    await client.ensure_collection("shared")

    # Save data for director-1
    vec = [0.1] * 1024
    await client.upsert(str(uuid.uuid4()), vec, {"thread_id": "dir-thread", "summary": "Director stuff"}, agent_scope="director-1")

    # Save data for engineer-1
    await client.upsert(str(uuid.uuid4()), vec, {"thread_id": "eng-thread", "summary": "Engineer stuff"}, agent_scope="engineer-1")

    # Save shared data
    await client.upsert(str(uuid.uuid4()), vec, {"thread_id": "shared-thread", "summary": "Shared stuff"}, agent_scope="shared")

    # Director-1 search should find own + shared, not engineer's
    results = await client.search(vec, agent_scope="director-1", limit=10, score_threshold=0.0)
    thread_ids = {r.get("payload", {}).get("thread_id") for r in results}
    assert "dir-thread" in thread_ids
    assert "shared-thread" in thread_ids
    assert "eng-thread" not in thread_ids

    # Cleanup
    async with httpx.AsyncClient(timeout=10) as hc:
        for suffix in ["director-1", "engineer-1", "shared"]:
            await hc.delete(f"{QDRANT_URL}/collections/test_scoped_iso_{suffix}")


# ── Fase 2C: HybridQdrantClient ─────────────────────────────────


def test_parse_agent_level():
    assert _parse_agent_level("director-1") == ("director", "director-1")
    assert _parse_agent_level("engineer-3") == ("engineer", "engineer-3")
    assert _parse_agent_level("catedratico-2") == ("catedratico", "catedratico-2")
    assert _parse_agent_level("technician-5") == ("technician", "technician-5")
    assert _parse_agent_level("shared") == ("shared", "shared")


def test_level_map():
    assert LEVEL_MAP["director"] == "directors"
    assert LEVEL_MAP["catedratico"] == "directors"
    assert LEVEL_MAP["engineer"] == "engineers"
    assert LEVEL_MAP["technician"] == "technicians"


@requires_qdrant
@pytest.mark.asyncio
async def test_hybrid_creates_level_collections():
    """Each level should get its own collection."""
    client = HybridQdrantClient(QDRANT_URL, "test_hybrid", 1024)
    await client.ensure_collection("director-1")
    await client.ensure_collection("engineer-1")
    await client.ensure_collection("shared")

    # Directors and catedraticos share the same collection
    assert await client.count("director-1") == 0
    assert await client.count("catedratico-1") == 0  # Same collection as directors
    assert await client.count("engineer-1") == 0
    assert await client.count("shared") == 0


@requires_qdrant
@pytest.mark.asyncio
async def test_hybrid_isolates_by_level_and_agent():
    """Director-1 should not see engineer-1's data, but directors share a collection."""
    import httpx
    import uuid

    client = HybridQdrantClient(QDRANT_URL, "test_hybrid_iso", 1024)
    await client.ensure_collection("director-1")
    await client.ensure_collection("director-2")
    await client.ensure_collection("engineer-1")
    await client.ensure_collection("shared")

    vec = [0.1] * 1024

    # Save data for director-1
    await client.upsert(str(uuid.uuid4()), vec, {"thread_id": "dir1-thread", "summary": "Director 1"}, agent_scope="director-1")

    # Save data for director-2
    await client.upsert(str(uuid.uuid4()), vec, {"thread_id": "dir2-thread", "summary": "Director 2"}, agent_scope="director-2")

    # Save data for engineer-1
    await client.upsert(str(uuid.uuid4()), vec, {"thread_id": "eng1-thread", "summary": "Engineer 1"}, agent_scope="engineer-1")

    # Save shared
    await client.upsert(str(uuid.uuid4()), vec, {"thread_id": "shared-thread", "summary": "Shared"}, agent_scope="shared")

    # Director-1 should see own + shared, NOT director-2 or engineer-1
    results = await client.search(vec, agent_scope="director-1", limit=10, score_threshold=0.0)
    thread_ids = {r.get("payload", {}).get("thread_id") for r in results}
    assert "dir1-thread" in thread_ids
    assert "shared-thread" in thread_ids
    assert "dir2-thread" not in thread_ids  # Different agent in same level
    assert "eng1-thread" not in thread_ids  # Different level

    # Cleanup
    async with httpx.AsyncClient(timeout=10) as hc:
        for suffix in ["directors", "engineers", "shared"]:
            await hc.delete(f"{QDRANT_URL}/collections/test_hybrid_iso_{suffix}")
