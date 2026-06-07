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
import re
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Qdrant-reserved payload keys that must never be used (they conflict with
# the point structure: id, vector, sparse_vectors, payload)
_QDRANT_RESERVED_KEYS = frozenset({"id", "vector", "sparse_vectors", "payload"})
_PAYLOAD_KEY_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _validate_payload_keys(payload: dict[str, Any], point_id: str = "?") -> None:
    """Validate payload keys to prevent injection into Qdrant internals."""
    for key in payload:
        if key in _QDRANT_RESERVED_KEYS:
            raise ValueError(
                f"Payload key '{key}' is reserved by Qdrant (point {point_id})"
            )
        if not _PAYLOAD_KEY_RE.match(key):
            raise ValueError(
                f"Invalid payload key '{key}': must match ^[a-zA-Z_][a-zA-Z0-9_]*$ "
                f"(point {point_id})"
            )


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
        # One httpx client per event loop. Pooled keepalive connections are
        # bound to the loop they were created on, so sharing a single client
        # across threads/loops raises "Event loop is closed" (or cross-loop
        # errors) as soon as a connection outlives its loop.
        self._clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create a persistent httpx client for the running event loop."""
        loop = asyncio.get_running_loop()
        client = self._clients.get(loop)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
            self._clients[loop] = client
        return client

    async def close(self):
        """Close the persistent client(s)."""
        for client in self._clients.values():
            if not client.is_closed:
                try:
                    await client.aclose()
                except Exception:
                    pass  # Client may belong to another (possibly closed) loop
        self._clients.clear()

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
        """Insert or update a single point.

        Payload keys are validated to prevent injection of Qdrant-internal
        keys (e.g., 'vector', 'id') that could corrupt point data.
        """
        if not vector or len(vector) != self.embedding_dim:
            raise ValueError(
                f"Invalid vector for point {point_id}: "
                f"got {len(vector) if vector else 0} dims, expected {self.embedding_dim}"
            )
        _validate_payload_keys(payload, point_id)
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
        """Insert or update multiple points with payload key validation."""
        for p in points:
            pid = p.get("id", "?")
            v = p.get("vector", [])
            if not v or len(v) != self.embedding_dim:
                raise ValueError(
                    f"Invalid vector for point {pid}: "
                    f"got {len(v) if v else 0} dims, expected {self.embedding_dim}"
                )
            payload = p.setdefault("payload", {})
            _validate_payload_keys(payload, pid)
            payload["schema_version"] = payload.get("schema_version", "1.0")

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

    async def set_payload(self, point_ids: list, payload: dict[str, Any], wait: bool = True) -> bool:
        """Set payload keys on existing points without touching vectors.

        Used by consolidation to mark L1 items as consumed (dedup guard)."""
        _validate_payload_keys(payload)

        async def _do():
            client = await self._get_client()
            resp = await client.post(
                f"{self.url}/collections/{self.collection}/points/payload"
                f"{'?wait=true' if wait else ''}",
                json={"points": point_ids, "payload": payload},
            )
            return resp.status_code == 200
        try:
            return await self._retry(_do)
        except Exception as e:
            logger.warning("Qdrant set_payload failed: %s", e)
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
