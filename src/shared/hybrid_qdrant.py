"""Hybrid Qdrant client — collection per level + payload filter (Fase 2C).

Combines Fase 2A (payload filter) and Fase 2B (collection per level).

Collections:
    conversations_shared       → visible to all agents
    conversations_directors    → all directors, filtered by agent_scope payload
    conversations_engineers    → all engineers, filtered by agent_scope payload
    conversations_technicians  → all technicians, filtered by agent_scope payload

Agent levels (configurable):
    director   → conversations_directors
    catedratico → conversations_directors (same level as directors)
    engineer   → conversations_engineers
    technician → conversations_technicians

Usage:
    client = HybridQdrantClient("http://127.0.0.1:6333", "conversations", 1024)
    await client.upsert("point-1", vector, payload, agent_scope="director-1")
    # Goes to conversations_directors with agent_scope="director-1" in payload

    results = await client.search(vector, agent_scope="director-1")
    # Searches conversations_directors (filtered) + conversations_shared
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from shared.qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

# Agent level → collection suffix mapping
LEVEL_MAP = {
    "director": "directors",
    "catedratico": "directors",
    "engineer": "engineers",
    "technician": "technicians",
}


def _parse_agent_level(agent_scope: str) -> tuple[str, str]:
    """Parse agent_scope into (level, full_scope).

    Examples:
        "director-1"   → ("director", "director-1")
        "engineer-3"   → ("engineer", "engineer-3")
        "shared"       → ("shared", "shared")
    """
    if agent_scope == "shared":
        return ("shared", "shared")
    # Parse "level-N" format
    parts = agent_scope.rsplit("-", 1)
    if len(parts) == 2:
        return (parts[0], agent_scope)
    return (agent_scope, agent_scope)


class HybridQdrantClient:
    """Qdrant client with collection-per-level + payload filter isolation.

    Each agent LEVEL gets its own collection. Individual agents within
    a level are isolated by payload filter.
    """

    def __init__(self, url: str, base_collection: str, embedding_dim: int = 1024):
        self.url = url
        self.base_collection = base_collection
        self.embedding_dim = embedding_dim
        self._clients: dict[str, QdrantClient] = {}

    def _get_client(self, collection_suffix: str) -> QdrantClient:
        """Get or create a QdrantClient for the given collection."""
        collection = f"{self.base_collection}_{collection_suffix}"
        if collection not in self._clients:
            self._clients[collection] = QdrantClient(
                self.url, collection, self.embedding_dim
            )
        return self._clients[collection]

    def _get_collection_suffix(self, agent_scope: str) -> str:
        """Map agent_scope to collection suffix."""
        level, _ = _parse_agent_level(agent_scope)
        if level == "shared":
            return "shared"
        return LEVEL_MAP.get(level, "shared")

    async def ensure_collection(self, agent_scope: str = "shared", sparse: bool = True) -> None:
        """Ensure the collection for this scope exists."""
        suffix = self._get_collection_suffix(agent_scope)
        client = self._get_client(suffix)
        await client.ensure_collection(sparse=sparse)

    async def upsert(
        self,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
        agent_scope: str = "shared",
        sparse: Optional[dict] = None,
    ) -> None:
        """Upsert a point into the level's collection with agent_scope in payload."""
        suffix = self._get_collection_suffix(agent_scope)
        # Add agent_scope to payload for filtering
        payload["agent_scope"] = agent_scope
        client = self._get_client(suffix)
        await client.upsert(point_id, vector, payload, sparse=sparse)

    async def search(
        self,
        vector: list[float],
        agent_scope: str = "shared",
        limit: int = 10,
        score_threshold: float = 0.3,
    ) -> list[dict]:
        """Search in agent's level collection (filtered) + shared collection."""
        results = []
        level, full_scope = _parse_agent_level(agent_scope)

        # 1. Search in agent's level collection (with payload filter)
        if level != "shared":
            try:
                level_suffix = self._get_collection_suffix(agent_scope)
                level_client = self._get_client(level_suffix)
                # Filter: agent's own scope OR shared within this level
                scope_filter = {
                    "should": [
                        {"key": "agent_scope", "match": {"value": full_scope}},
                        {"key": "agent_scope", "match": {"value": "shared"}},
                    ]
                }
                level_results = await level_client.search(
                    vector, limit=limit, score_threshold=score_threshold,
                    filter=scope_filter,
                )
                results.extend(level_results)
            except Exception as e:
                logger.warning("Search in %s collection failed: %s", level, e)

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

        merged = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
        return merged[:limit]

    async def scroll(
        self,
        agent_scope: str = "shared",
        limit: int = 50,
    ) -> list[dict]:
        """Scroll points from agent's level collection + shared collection."""
        results = []
        level, full_scope = _parse_agent_level(agent_scope)

        # 1. Agent's level collection
        if level != "shared":
            try:
                level_suffix = self._get_collection_suffix(agent_scope)
                level_client = self._get_client(level_suffix)
                level_results = await level_client.scroll(limit=limit)
                # Filter by agent_scope in payload
                filtered = [
                    r for r in level_results
                    if r.get("agent_scope") in (full_scope, "shared")
                ]
                results.extend(filtered)
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
            suffix = self._get_collection_suffix(agent_scope)
            client = self._get_client(suffix)
            return await client.count()
        except Exception:
            return 0
