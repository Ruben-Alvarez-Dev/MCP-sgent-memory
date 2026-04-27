"""Scoped Qdrant client — collection per agent (Fase 2B).

Each agent gets its own Qdrant collection for full isolation.
Shared data goes in a common collection.

Collections:
    conversations_shared          → visible to all agents
    conversations_{agent_scope}   → visible only to that agent

Usage:
    client = ScopedQdrantClient("http://127.0.0.1:6333", "conversations", 1024)
    await client.upsert("point-1", vector, payload, agent_scope="director-1")
    results = await client.search(vector, agent_scope="director-1")
    # Searches in conversations_director-1 + conversations_shared
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from shared.qdrant_client import QdrantClient

logger = logging.getLogger(__name__)


class ScopedQdrantClient:
    """Qdrant client with collection-per-agent isolation.

    Wraps QdrantClient and routes operations to the correct collection
    based on agent_scope.
    """

    def __init__(self, url: str, base_collection: str, embedding_dim: int = 1024):
        self.url = url
        self.base_collection = base_collection
        self.embedding_dim = embedding_dim
        self._clients: dict[str, QdrantClient] = {}

    def _get_client(self, agent_scope: str) -> QdrantClient:
        """Get or create a QdrantClient for the given scope's collection."""
        collection = self._collection_name(agent_scope)
        if collection not in self._clients:
            self._clients[collection] = QdrantClient(
                self.url, collection, self.embedding_dim
            )
        return self._clients[collection]

    def _collection_name(self, agent_scope: str) -> str:
        """Map agent_scope to collection name."""
        if agent_scope == "shared":
            return f"{self.base_collection}_shared"
        return f"{self.base_collection}_{agent_scope}"

    async def ensure_collection(self, agent_scope: str = "shared", sparse: bool = True) -> None:
        """Ensure the collection for this scope exists."""
        client = self._get_client(agent_scope)
        await client.ensure_collection(sparse=sparse)

    async def upsert(
        self,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
        agent_scope: str = "shared",
        sparse: Optional[dict] = None,
    ) -> None:
        """Upsert a point into the scope's collection."""
        client = self._get_client(agent_scope)
        await client.upsert(point_id, vector, payload, sparse=sparse)

    async def search(
        self,
        vector: list[float],
        agent_scope: str = "shared",
        limit: int = 10,
        score_threshold: float = 0.3,
    ) -> list[dict]:
        """Search in agent's collection + shared collection.

        Merges results, deduplicates by thread_id, keeps best score.
        """
        results = []

        # 1. Search in agent's own collection (if not shared)
        if agent_scope != "shared":
            try:
                own_client = self._get_client(agent_scope)
                own_results = await own_client.search(
                    vector, limit=limit, score_threshold=score_threshold
                )
                results.extend(own_results)
            except Exception as e:
                logger.warning("Search in %s collection failed: %s", agent_scope, e)

        # 2. Search in shared collection
        try:
            shared_client = self._get_client("shared")
            shared_results = await shared_client.search(
                vector, limit=limit, score_threshold=score_threshold
            )
            results.extend(shared_results)
        except Exception as e:
            logger.warning("Search in shared collection failed: %s", e)

        # 3. Deduplicate by thread_id, keep best score
        seen = {}
        for r in results:
            payload = r.get("payload", {})
            tid = payload.get("thread_id", "")
            if tid:
                score = r.get("score", 0)
                if tid not in seen or score > seen[tid].get("score", 0):
                    seen[tid] = r

        # Sort by score descending, limit
        merged = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
        return merged[:limit]

    async def scroll(
        self,
        agent_scope: str = "shared",
        limit: int = 50,
    ) -> list[dict]:
        """Scroll points from agent's collection + shared collection."""
        results = []

        # 1. Agent's own collection
        if agent_scope != "shared":
            try:
                own_client = self._get_client(agent_scope)
                own_results = await own_client.scroll(limit=limit)
                results.extend(own_results)
            except Exception:
                pass

        # 2. Shared collection
        try:
            shared_client = self._get_client("shared")
            shared_results = await shared_client.scroll(limit=limit)
            results.extend(shared_results)
        except Exception:
            pass

        return results[:limit]

    async def health(self) -> bool:
        """Check if Qdrant is reachable."""
        try:
            client = QdrantClient(self.url, "dummy", self.embedding_dim)
            return await client.health()
        except Exception:
            return False

    async def count(self, agent_scope: str = "shared") -> int:
        """Count points in the scope's collection."""
        try:
            client = self._get_client(agent_scope)
            return await client.count()
        except Exception:
            return 0
