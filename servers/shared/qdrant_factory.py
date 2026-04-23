"""Shared QdrantClient factory — single instance per collection.

Instead of each module creating its own QdrantClient(...),
use get_qdrant(collection) to get a shared, pooled instance.
"""
from __future__ import annotations

import os
from shared.qdrant_client import QdrantClient

_clients: dict[str, QdrantClient] = {}


def get_qdrant(collection: str, dim: int | None = None) -> QdrantClient:
    """Get or create a shared QdrantClient for the given collection."""
    if dim is None:
        dim = int(os.getenv("EMBEDDING_DIM", "1024"))
    key = f"{collection}:{dim}"
    if key not in _clients:
        _clients[key] = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
            collection=collection,
            embedding_dim=dim,
        )
    return _clients[key]


def close_all() -> None:
    """Close all shared clients (call on shutdown)."""
    import asyncio
    for client in _clients.values():
        try:
            asyncio.get_event_loop().create_task(client.close())
        except RuntimeError:
            pass
    _clients.clear()
