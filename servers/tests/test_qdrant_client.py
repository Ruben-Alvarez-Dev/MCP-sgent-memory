"""Tests for shared.qdrant_client — centralized Qdrant operations."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.qdrant_client import QdrantClient


class TestQdrantClientInit:
    def test_default_url(self):
        c = QdrantClient()
        assert "6333" in c.url

    def test_custom_url(self):
        c = QdrantClient("http://localhost:9999", "test", 512)
        assert c.url == "http://localhost:9999"
        assert c.collection == "test"
        assert c.embedding_dim == 512

    def test_with_collection(self):
        c1 = QdrantClient("http://localhost:6333", "col_a", 1024)
        c2 = c1.with_collection("col_b")
        assert c2.collection == "col_b"
        assert c2.url == c1.url
        assert c1.collection == "col_a"  # original unchanged


class TestQdrantClientHealth:
    @pytest.mark.asyncio
    async def test_health_ok(self):
        c = QdrantClient("http://localhost:6333")
        with patch("shared.qdrant_client.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            MockClient.return_value = mock_client
            assert await c.health() is True

    @pytest.mark.asyncio
    async def test_health_fail(self):
        c = QdrantClient("http://localhost:9999")
        assert await c.health() is False
