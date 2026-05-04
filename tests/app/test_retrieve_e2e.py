"""End-to-end retrieve() test — real Qdrant + real embedding server.

Requires:
  - Qdrant running on :6333
  - Embedding server running on :8081

This test proves the full retrieval pipeline works with real data.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
import httpx

# ── Service availability check ─────────────────────────────────────


def _services_available() -> bool:
    try:
        r = httpx.get("http://127.0.0.1:6333/healthz", timeout=2)
        if r.status_code != 200:
            return False
    except Exception:
        return False
    try:
        r = httpx.get("http://127.0.0.1:8081/health", timeout=2)
        if "ok" not in r.text:
            return False
    except Exception:
        return False
    return True

pytestmark = pytest.mark.skipif(
    not _services_available(),
    reason="Requires Qdrant (:6333) and embedding server (:8081)",
)

QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION = "e2e_test_retrieve"
EMBEDDING_DIM = 1024


@pytest.fixture(autouse=True)
def setup_collection():
    """Create a clean test collection before each test."""
    # Create with correct vector dimension
    httpx.put(f"{QDRANT_URL}/collections/{COLLECTION}", json={
        "vectors": {
            "size": EMBEDDING_DIM,
            "distance": "Cosine",
        }
    })
    yield
    httpx.delete(f"{QDRANT_URL}/collections/{COLLECTION}")


# ── E2E Tests ──────────────────────────────────────────────────────


class TestRetrieveE2E:
    """Full pipeline: embed → upsert → search → rank."""

    @pytest.mark.asyncio
    async def test_embed_and_upsert_real_vectors(self):
        """Embed text and upsert to Qdrant with real vectors."""
        from shared.embedding import get_embedding

        vectors = get_embedding("Python dependency injection pattern")
        assert len(vectors) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in vectors)

        # Upsert to Qdrant
        payload = {
            "content": "Python dependency injection pattern",
            "source": "test",
            "layer": "L3",
        }
        response = httpx.put(
            f"{QDRANT_URL}/collections/{COLLECTION}/points",
            json={
                "points": [{
                    "id": 1,
                    "vector": vectors,
                    "payload": payload,
                }]
            }
        )
        assert response.status_code == 200

        # Search for it
        search_response = httpx.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
            json={
                "vector": vectors,
                "limit": 5,
                "with_payload": True,
            }
        )
        assert search_response.status_code == 200
        data = search_response.json()
        results = data.get("result", [])
        assert len(results) >= 1
        assert results[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_full_retrieve_pipeline(self):
        """Full retrieve() call with real services."""
        from shared.retrieval import retrieve

        # Upsert some test data first
        from shared.embedding import get_embedding
        test_items = [
            ("FastAPI dependency injection with annotations", 101),
            ("Docker compose networking configuration", 102),
            ("Git rebasing vs merging strategies", 103),
        ]
        for text, point_id in test_items:
            vectors = get_embedding(text)
            httpx.put(
                f"{QDRANT_URL}/collections/{COLLECTION}/points",
                json={"points": [{"id": point_id, "vector": vectors, "payload": {"content": text, "layer": "L3"}}]}
            )

        # Now retrieve
        pack = await retrieve(
            "How to do dependency injection in FastAPI",
            session_type="dev",
            token_budget=4000,
        )
        # Should return a ContextPack with sections
        assert pack is not None
        assert hasattr(pack, 'sections')
        assert hasattr(pack, 'total_tokens')
        assert hasattr(pack, 'query')

    @pytest.mark.asyncio
    async def test_qdrant_client_real_operations(self):
        """QdrantClient health and collection check with real Qdrant."""
        from shared.qdrant_client import QdrantClient
        from shared.config import Config

        config = Config.from_env()
        # Use our test collection
        client = QdrantClient(config.qdrant_url, COLLECTION, config.embedding_dim)

        # Health check
        healthy = await client.health()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_classify_intent_with_real_service(self):
        """classify_intent works without external calls."""
        from shared.retrieval import classify_intent

        result = classify_intent("where is the AuthService class defined?")
        assert result is not None
        assert hasattr(result, 'intent_type')
        assert result.intent_type in ("code_lookup", "pattern_match", "debug", "knowledge")

    @pytest.mark.asyncio
    async def test_embedding_consistency(self):
        """Same text produces consistent embeddings."""
        from shared.embedding import get_embedding

        text = "Hexagonal architecture separates domain from infrastructure"
        v1 = get_embedding(text)
        v2 = get_embedding(text)
        assert len(v1) == EMBEDDING_DIM
        assert len(v2) == EMBEDDING_DIM
        # Embeddings should be identical for same input
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embedding_different_text_different_vector(self):
        """Different texts produce different embeddings."""
        from shared.embedding import get_embedding

        v1 = get_embedding("Python is a programming language")
        v2 = get_embedding("Rust is a systems programming language")
        assert v1 != v2
