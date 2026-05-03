"""Centralized Qdrant HTTP client for all MCP memory servers.

Single source of truth for all Qdrant operations. Server modules
import this instead of making raw httpx calls.

Usage:
    from shared.qdrant_client import QdrantClient

    qdrant = QdrantClient("http://127.0.0.1:6333", "L0_L4_memory", 1024)
    await qdrant.ensure_collection()
    await qdrant.upsert("id-123", vector, payload)
    results = await qdrant.search(vector, limit=10)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class QdrantClient:
    """Unified Qdrant operations for all memory server modules.

    Wraps all HTTP calls to Qdrant into a clean async API.
    Replaces scattered httpx calls across 7 server modules.
    """

    def __init__(
        self,
        url: str | None = None,
        collection: str = "L0_L4_memory",
        embedding_dim: int = 1024,
        timeout: float = 30.0,
    ):
        self.url = url or os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
        self.collection = collection
        self.embedding_dim = embedding_dim
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create a persistent httpx client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self):
        """Close the persistent client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _retry(self, fn, max_retries: int = 3, base_delay: float = 0.5):
        """Execute fn with exponential backoff on transient errors."""
        last_exc = None
        for attempt in range(max_retries):
            try:
                return await fn()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Attempt %d/%d failed for %s: %s, retrying in %.1fs",
                    attempt + 1, max_retries, self.collection, e, delay,
                )
                await asyncio.sleep(delay)
        raise last_exc

    def with_collection(self, collection: str) -> QdrantClient:
        """Create a new client targeting a different collection."""
        return QdrantClient(self.url, collection, self.embedding_dim, self._timeout)

    # ── Health ─────────────────────────────────────────────────

    async def health(self) -> bool:
        """Check if Qdrant is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.url}/healthz")
                return resp.status_code == 200
        except Exception:
            return False

    # ── Collection management ──────────────────────────────────

    async def ensure_collection(self, sparse: bool = True) -> None:
        """Create collection with dense + optional sparse vectors if not exists."""
        async def _do():
            client = await self._get_client()
            resp = await client.get(f"{self.url}/collections")
            resp.raise_for_status()
            existing = [
                c["name"]
                for c in resp.json().get("result", {}).get("collections", [])
            ]
            if self.collection not in existing:
                body: dict[str, Any] = {
                    "vectors": {
                        "size": self.embedding_dim,
                        "distance": "Cosine",
                    }
                }
                if sparse:
                    body["sparse_vectors"] = {
                        "text": {"index": {"type": "bm25"}}
                    }
                await client.put(
                    f"{self.url}/collections/{self.collection}",
                    json=body,
                )
                logger.info(
                    "Created collection %s (dim=%d, sparse=%s)",
                    self.collection,
                    self.embedding_dim,
                    sparse,
                )
        await self._retry(_do)

    async def collection_info(self) -> Optional[dict]:
        """Get collection metadata, or None if not found."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self.url}/collections/{self.collection}"
                )
                if resp.status_code == 200:
                    return resp.json().get("result")
                return None
        except Exception:
            return None

    async def count(self) -> int:
        """Count points in the collection."""
        info = await self.collection_info()
        if info:
            return info.get("points_count", 0)
        return 0

    # ── Point operations ───────────────────────────────────────

    async def upsert(
        self,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
        sparse: Optional[dict] = None,
        wait: bool = True,
    ) -> None:
        """Insert or update a single point."""
        if not vector or len(vector) != self.embedding_dim:
            raise ValueError(
                f"Invalid vector for point {point_id}: "
                f"got {len(vector) if vector else 0} dims, expected {self.embedding_dim}"
            )
        payload["schema_version"] = payload.get("schema_version", "1.0")
        point: dict[str, Any] = {
            "id": point_id,
            "vector": vector,
            "payload": payload,
        }
        if sparse:
            point["sparse_vectors"] = {"text": sparse}

        async def _do():
            client = await self._get_client()
            await client.put(
                f"{self.url}/collections/{self.collection}/points"
                f"{'?wait=true' if wait else ''}",
                json={"points": [point]},
            )
        await self._retry(_do)

    async def upsert_batch(
        self,
        points: list[dict[str, Any]],
        wait: bool = True,
    ) -> None:
        """Insert or update multiple points."""
        for p in points:
            v = p.get("vector", [])
            if not v or len(v) != self.embedding_dim:
                raise ValueError(
                    f"Invalid vector for point {p.get('id', '?')}: "
                    f"got {len(v) if v else 0} dims, expected {self.embedding_dim}"
                )
            p.setdefault("payload", {})["schema_version"] = p["payload"].get("schema_version", "1.0")

        async def _do():
            client = await self._get_client()
            await client.put(
                f"{self.url}/collections/{self.collection}/points"
                f"{'?wait=true' if wait else ''}",
                json={"points": points},
            )
        await self._retry(_do)

    async def get(self, point_id: str) -> Optional[dict]:
        """Get a point by ID, or None if not found."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self.url}/collections/{self.collection}/points/{point_id}"
                )
                if resp.status_code == 200:
                    return resp.json().get("result")
                return None
        except Exception:
            return None

    async def delete(self, point_id: str, wait: bool = True) -> bool:
        """Delete a point by ID. Returns True if deleted."""
        async def _do():
            client = await self._get_client()
            resp = await client.post(
                f"{self.url}/collections/{self.collection}/points/delete"
                f"{'?wait=true' if wait else ''}",
                json={"points": [point_id]},
            )
            return resp.status_code == 200
        try:
            return await self._retry(_do)
        except Exception as e:
            logger.warning("Qdrant delete failed: %s", e)
            return False

    # ── Search & query ─────────────────────────────────────────

    async def search(
        self,
        vector: list[float],
        limit: int = 10,
        score_threshold: float = 0.3,
        filter: Optional[dict] = None,
    ) -> list[dict]:
        """Search by dense vector with optional filtering."""
        body: dict[str, Any] = {
            "vector": vector,
            "limit": limit,
            "score_threshold": score_threshold,
            "with_payload": True,
        }
        if filter:
            body["filter"] = filter

        async def _do():
            client = await self._get_client()
            resp = await client.post(
                f"{self.url}/collections/{self.collection}/points/search",
                json=body,
            )
            if resp.status_code != 200:
                return []
            result = resp.json().get("result", [])
            return result if isinstance(result, list) else result.get("result", [])
        try:
            return await self._retry(_do)
        except Exception as e:
            logger.warning("Qdrant search failed after retries: %s", e)
            return []

    async def scroll(
        self,
        filter: Optional[dict] = None,
        limit: int = 50,
        with_payload: bool = True,
    ) -> list[dict]:
        """Scroll points with optional filtering."""
        body: dict[str, Any] = {
            "limit": limit,
            "with_payload": with_payload,
        }
        if filter:
            body["filter"] = filter

        async def _do():
            client = await self._get_client()
            resp = await client.post(
                f"{self.url}/collections/{self.collection}/points/scroll",
                json=body,
            )
            if resp.status_code != 200:
                return []
            result = resp.json().get("result", [])
            points = result.get("points", []) if isinstance(result, dict) else result
            return [p.get("payload", {}) for p in points if p.get("payload")]
        try:
            return await self._retry(_do)
        except Exception as e:
            logger.warning("Qdrant scroll failed after retries: %s", e)
            return []
