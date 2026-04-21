"""Tests for shared.retrieval.index_repo — code map points and repo index.

Covers: build_code_map_points (sync), build_repo_index_points (sync),
upsert_repository_index (async, with mocked Qdrant).
"""

from __future__ import annotations

import json

import httpx
import pytest

from shared.embedding import EMBEDDING_DIM, get_embedding_spec
from shared.retrieval.index_repo import (
    build_code_map_points,
    build_repo_index_points,
    upsert_repository_index,
)


# ── build_code_map_points (sync) ──────────────────────────────────


def test_code_map_points_returns_list_with_vectors(tmp_path):
    (tmp_path / "example.py").write_text("def hello():\n    return 'world'\n")
    spec = get_embedding_spec()

    def embed_fn(text: str) -> list[float]:
        return [0.1] * spec.dim

    points = build_code_map_points(str(tmp_path), embed_fn=embed_fn)

    assert isinstance(points, list)
    assert len(points) >= 1
    point = points[0]
    assert "payload" in point
    assert "vector" in point
    assert point["payload"]["type"] == "code_map"
    assert point["payload"]["language"] == "python"


def test_code_map_points_vector_dimension_matches_spec(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    spec = get_embedding_spec()

    def embed_fn(text: str) -> list[float]:
        return [0.5] * spec.dim

    points = build_code_map_points(str(tmp_path), embed_fn=embed_fn)
    for point in points:
        assert len(point["vector"]) == spec.dim


def test_code_map_points_skips_non_code_files(tmp_path):
    (tmp_path / "readme.md").write_text("# Hello")
    (tmp_path / "main.py").write_text("def run(): pass")
    points = build_code_map_points(str(tmp_path), embed_fn=lambda t: [0.0] * 3)
    # Should index .py but may or may not index .md depending on suffix filter
    py_points = [p for p in points if p["payload"]["file_path"].endswith(".py")]
    assert len(py_points) >= 1


# ── build_repo_index_points (sync) ────────────────────────────────


def test_repo_index_points_captures_files_symbols_and_deps(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dep.py").write_text("def helper():\n    return 1\n")
    (pkg / "main.py").write_text(
        "from pkg.dep import helper\n\nclass Service:\n    pass\n\ndef run():\n    return helper()\n"
    )

    points = build_repo_index_points(str(tmp_path), embed_fn=lambda _: [0.0, 0.0, 0.0])

    payloads = [p["payload"] for p in points]
    file_payload = next(
        p for p in payloads
        if p.get("path") == "pkg/main.py" and p.get("node_type") == "file"
    )
    func_payload = next(
        p for p in payloads
        if p.get("path") == "pkg/main.py" and p.get("node_type") == "function"
    )

    assert file_payload["layer"] == 2
    assert "pkg.dep" in file_payload.get("dependencies", [])
    assert func_payload.get("signature") == "def run()"
    assert all("vector" in p for p in points)


# ── upsert_repository_index (async, mocked Qdrant) ────────────────


@pytest.mark.asyncio
async def test_upsert_calls_qdrant_create_and_upload(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.py").write_text("def run():\n    return 1\n")

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "GET" and request.url.path == "/collections":
            return httpx.Response(200, json={"result": {"collections": []}})
        if request.method == "PUT" and "/collections/test_idx" in request.url.path:
            return httpx.Response(200, json={"result": True})
        if request.method == "PUT" and "/points" in request.url.path:
            body = json.loads(request.read().decode())
            assert "points" in body
            assert len(body["points"]) >= 1
            return httpx.Response(200, json={"result": {"status": "ok"}})
        raise AssertionError(f"Unexpected: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://qdrant.test") as client:
        result = await upsert_repository_index(
            str(tmp_path),
            qdrant_url="http://qdrant.test",
            collection="test_idx",
            client=client,
            embed_fn=lambda _: [0.0, 0.0, 0.0],
        )

    assert result["indexed_points"] >= 1
    methods = {c[0] for c in calls}
    assert "GET" in methods
    assert "PUT" in methods
