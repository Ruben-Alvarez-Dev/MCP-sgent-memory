from __future__ import annotations

import httpx
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.retrieval.index_repo import build_repo_index_points, upsert_repository_index


def test_build_repo_index_points_captures_files_symbols_and_dependencies(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dep.py").write_text("def helper():\n    return 1\n")
    (pkg / "main.py").write_text(
        "from pkg.dep import helper\n\n"
        "class Service:\n"
        "    pass\n\n"
        "def run():\n"
        "    return helper()\n"
    )

    points = build_repo_index_points(str(tmp_path), embed_fn=lambda _text: [0.0, 0.0, 0.0])

    payloads = [point["payload"] for point in points]
    file_payload = next(payload for payload in payloads if payload["path"] == "pkg/main.py" and payload["node_type"] == "file")
    function_payload = next(payload for payload in payloads if payload["path"] == "pkg/main.py" and payload["node_type"] == "function")

    assert file_payload["layer"] == 2
    assert "pkg.dep" in file_payload["dependencies"]
    assert function_payload["signature"] == "def run()"
    assert all("vector" in point for point in points)
    assert all("sparse_vectors" in point for point in points)


@pytest.mark.asyncio
async def test_upsert_repository_index_creates_collection_and_uploads_points(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.py").write_text("def run():\n    return 1\n")

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "GET" and request.url.path == "/collections":
            return httpx.Response(200, json={"result": {"collections": []}})
        if request.method == "PUT" and request.url.path == "/collections/automem":
            return httpx.Response(200, json={"result": True})
        if request.method == "PUT" and request.url.path == "/collections/automem/points":
            body = request.read().decode()
            assert '"layer":2' in body
            assert '"repo_symbol"' in body
            return httpx.Response(200, json={"result": {"status": "ok"}})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://qdrant.test") as client:
        result = await upsert_repository_index(
            str(tmp_path),
            qdrant_url="http://qdrant.test",
            collection="automem",
            client=client,
            embed_fn=lambda _text: [0.0, 0.0, 0.0],
        )

    assert result["indexed_points"] >= 1
    assert ("GET", "http://qdrant.test/collections") in calls
    assert ("PUT", "http://qdrant.test/collections/automem") in calls
    assert ("PUT", "http://qdrant.test/collections/automem/points?wait=true") in calls
