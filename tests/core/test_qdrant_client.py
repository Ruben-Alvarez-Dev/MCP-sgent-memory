"""Tests for QdrantClient — vector validation, retry logic."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from shared.qdrant_client import QdrantClient
import httpx


class TestVectorValidation:
    """B-1: Reject empty and mismatched vectors."""

    @pytest.mark.asyncio
    async def test_empty_vector_rejected(self):
        c = QdrantClient("http://localhost:6333", "test", 1024)
        with pytest.raises(ValueError, match="Invalid vector"):
            await c.upsert("id-1", [], {"test": True})

    @pytest.mark.asyncio
    async def test_wrong_dim_rejected(self):
        c = QdrantClient("http://localhost:6333", "test", 1024)
        with pytest.raises(ValueError, match="1024"):
            await c.upsert("id-1", [0.1] * 512, {"test": True})

    @pytest.mark.asyncio
    async def test_valid_vector_schema_version(self):
        c = QdrantClient("http://localhost:6333", "test", 1024)
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        c._get_client = AsyncMock(return_value=mock_client)

        await c.upsert("id-1", [0.1] * 1024, {"test": True})
        call_args = mock_client.put.call_args
        import json
        points = call_args[1]["json"]["points"]
        assert points[0]["payload"]["schema_version"] == "1.0"

    @pytest.mark.asyncio
    async def test_batch_empty_vector_rejected(self):
        c = QdrantClient("http://localhost:6333", "test", 1024)
        with pytest.raises(ValueError, match="Invalid vector"):
            await c.upsert_batch([
                {"id": "id-1", "vector": [], "payload": {"test": True}},
            ])


class TestRetryLogic:
    """C-1: Retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self):
        c = QdrantClient("http://localhost:6333", "test", 1024)
        mock_client = AsyncMock()
        # Fail twice, succeed third time
        mock_client.put = AsyncMock(
            side_effect=[httpx.ConnectError("refused"), httpx.ConnectError("refused"), None]
        )
        c._get_client = AsyncMock(return_value=mock_client)

        # Should succeed after retries
        await c.upsert("id-1", [0.1] * 1024, {"test": True})
        assert mock_client.put.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        c = QdrantClient("http://localhost:6333", "test", 1024)
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(side_effect=httpx.ConnectError("refused"))
        c._get_client = AsyncMock(return_value=mock_client)

        with pytest.raises(httpx.ConnectError):
            await c.upsert("id-1", [0.1] * 1024, {"test": True})
        assert mock_client.put.call_count == 3  # max_retries


class TestConfigValidation:
    """G-3: Config.validate() covers all fields."""

    def test_valid_config(self):
        from shared.config import Config
        c = Config.from_env()
        errors = c.validate()
        assert isinstance(errors, list)

    def test_invalid_backend(self):
        from shared.config import Config
        c = Config.from_env()
        c.embedding_backend = "invalid_backend"
        errors = c.validate()
        assert any("EMBEDDING_BACKEND" in e for e in errors)
