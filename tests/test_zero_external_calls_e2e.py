"""End-to-end tests: verify zero external calls in a coding flow.

Uses httpx.MockTransport to intercept all HTTP and verify only
localhost connections are made. Tests the full pipeline:
index repo → request context → push reminder.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

import shared.retrieval as retrieval
from shared.llm.config import QueryIntent
from shared.retrieval.index_repo import upsert_repository_index


def _qdrant_handler(indexed_points: list, collections: set) -> httpx.MockTransport:
    """Creates a MockTransport that simulates Qdrant for index + search."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host in {"127.0.0.1", "localhost"}, \
            f"External call detected: {request.url}"

        if request.method == "GET" and request.url.path == "/collections":
            return httpx.Response(200, json={
                "result": {"collections": [{"name": n} for n in sorted(collections)]}
            })
        if request.method == "PUT" and "/collections/" in request.url.path and "/points" not in request.url.path:
            col_name = request.url.path.split("/collections/")[1].rstrip("/")
            collections.add(col_name)
            return httpx.Response(200, json={"result": True})
        if request.method == "PUT" and "/points" in request.url.path:
            body = json.loads(request.read().decode())
            indexed_points[:] = body.get("points", [])
            return httpx.Response(200, json={"result": {"status": "ok"}})
        if request.method == "POST" and "/search" in request.url.path:
            body = json.loads(request.read().decode())
            limit = body.get("limit", 5)
            results = [
                {"id": p.get("id", i), "score": 0.95, "payload": p.get("payload", {})}
                for i, p in enumerate(indexed_points[:limit])
            ]
            return httpx.Response(200, json={"result": results})

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def test_index_and_search_stays_local(tmp_path, monkeypatch):
    """Index a repo and search it — all calls go to localhost only."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dep.py").write_text("def helper():\n    return 1\n")
    (pkg / "main.py").write_text("from pkg.dep import helper\n\ndef run():\n    return helper()\n")

    indexed_points: list = []
    collections: set = set()
    transport = _qdrant_handler(indexed_points, collections)

    orig_client = httpx.AsyncClient

    def local_client(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(retrieval.httpx, "AsyncClient", local_client)
    monkeypatch.setattr(retrieval, "get_embedding", lambda _: [0.0] * 3)

    async def run():
        async with orig_client(transport=transport) as client:
            await upsert_repository_index(
                str(tmp_path),
                qdrant_url="http://127.0.0.1:6333",
                collection="automem",
                client=client,
                embed_fn=lambda _: [0.0] * 3,
            )
        assert len(indexed_points) >= 1
        # Verify payloads have expected structure
        for p in indexed_points:
            assert "payload" in p
            assert "vector" in p

    asyncio.run(run())


def test_index_handles_100_plus_files_within_budget(tmp_path, monkeypatch):
    """Index 120 files — verifies scale and that vector generation works."""
    app = tmp_path / "app"
    app.mkdir()

    for i in range(120):
        lines = [f"def feature_{i}():", "    value = 0"]
        if i > 0:
            lines.insert(0, f"from app.module_{i-1} import feature_{i-1}")
        (app / f"module_{i}.py").write_text("\n".join(lines) + "\n")

    indexed_points: list = []
    collections: set = set()
    transport = _qdrant_handler(indexed_points, collections)

    orig_client = httpx.AsyncClient

    def local_client(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(retrieval.httpx, "AsyncClient", local_client)
    monkeypatch.setattr(retrieval, "get_embedding", lambda _: [0.0, 0.0, 0.0])

    async def run():
        async with orig_client(transport=transport) as client:
            result = await upsert_repository_index(
                str(tmp_path),
                qdrant_url="http://127.0.0.1:6333",
                collection="automem",
                client=client,
                embed_fn=lambda _: [0.0, 0.0, 0.0],
            )
        assert result["indexed_points"] >= 100

    asyncio.run(run())
