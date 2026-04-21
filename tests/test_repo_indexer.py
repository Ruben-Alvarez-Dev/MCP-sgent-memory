"""Tests for shared.retrieval — repo index integration.

Covers: build_repo_index_points and upsert_repository_index with
mocked Qdrant HTTP transport.
"""

from __future__ import annotations

import json

import httpx
import pytest

from shared.retrieval.index_repo import build_repo_index_points, upsert_repository_index


def test_build_repo_index_points_captures_structure(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dep.py").write_text("def helper():\n    return 1\n")
    (pkg / "main.py").write_text(
        "from pkg.dep import helper\n\n"
        "class Service:\n    pass\n\n"
        "def run():\n    return helper()\n"
    )

    points = build_repo_index_points(str(tmp_path), embed_fn=lambda _: [0.0, 0.0, 0.0])

    payloads = [p["payload"] for p in points]
    file_p = next(
        (p for p in payloads if p.get("path") == "pkg/main.py" and p.get("node_type") == "file"),
        None,
    )
    func_p = next(
        (p for p in payloads if p.get("path") == "pkg/main.py" and p.get("node_type") == "function"),
        None,
    )
    assert file_p is not None, "File-level point missing"
    assert func_p is not None, "Function-level point missing"
    assert file_p["layer"] == 2
    assert "pkg.dep" in file_p.get("dependencies", [])


@pytest.mark.asyncio
async def test_upsert_creates_collection_and_uploads(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.py").write_text("def run():\n    return 1\n")

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "GET" and request.url.path == "/collections":
            return httpx.Response(200, json={"result": {"collections": []}})
        if request.method == "PUT" and "/collections/automem" in request.url.path:
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
            collection="automem",
            client=client,
            embed_fn=lambda _: [0.0, 0.0, 0.0],
        )

    assert result["indexed_points"] >= 1
    methods = {c[0] for c in calls}
    assert "GET" in methods
    assert "PUT" in methods
