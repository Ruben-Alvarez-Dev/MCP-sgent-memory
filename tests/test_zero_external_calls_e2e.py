from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.llm.config import QueryIntent
from shared.retrieval import upsert_repository_index
import shared.retrieval as retrieval


def _load_mcp_module(module_path: Path, module_name: str):
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    class DummyFastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self):
            def decorator(fn):
                return fn

            return decorator

        def run(self):
            return None

    fastmcp_module.FastMCP = DummyFastMCP
    sys.modules["mcp"] = types.ModuleType("mcp")
    sys.modules["mcp.server"] = types.ModuleType("mcp.server")
    sys.modules["mcp.server.fastmcp"] = fastmcp_module

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_complex_coding_flow_uses_only_local_calls(tmp_path: Path, monkeypatch):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dep.py").write_text("def helper():\n    return 1\n")
    (pkg / "main.py").write_text(
        "from pkg.dep import helper\n\n"
        "def run():\n"
        "    return helper()\n"
    )

    vk_main = _load_mcp_module(ROOT / "vk-cache" / "server" / "main.py", "vk_cache_main")
    seq_main = _load_mcp_module(ROOT / "sequential-thinking" / "server" / "main.py", "sequential_thinking_main")

    allowed_hosts = {"127.0.0.1", "localhost"}
    request_log: list[str] = []
    collections: set[str] = set()
    indexed_points: list[dict] = []

    def qdrant_handler(request: httpx.Request) -> httpx.Response:
        request_log.append(str(request.url))
        assert request.url.host in allowed_hosts

        if request.method == "GET" and request.url.path == "/collections":
            return httpx.Response(
                200,
                json={"result": {"collections": [{"name": name} for name in sorted(collections)]}},
            )

        if request.method == "PUT" and request.url.path == "/collections/automem":
            collections.add("automem")
            return httpx.Response(200, json={"result": True})

        if request.method == "PUT" and request.url.path == "/collections/automem/points":
            body = json.loads(request.read().decode())
            indexed_points[:] = body["points"]
            return httpx.Response(200, json={"result": {"status": "ok"}})

        if request.method == "POST" and request.url.path in {
            "/collections/automem/points/search",
            "/collections/automem/points/search/sparse",
        }:
            body = json.loads(request.read().decode())
            limit = body.get("limit", 5)
            must = body.get("filter", {}).get("must", [])
            wanted_layer = None
            for clause in must:
                if clause.get("key") == "layer":
                    wanted_layer = clause.get("match", {}).get("value")

            points = []
            for point in indexed_points:
                payload = point["payload"]
                if wanted_layer is not None and payload.get("layer") != wanted_layer:
                    continue
                points.append({"id": point["id"], "score": 0.95, "payload": payload})

            return httpx.Response(200, json={"result": points[:limit]})

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(qdrant_handler)
    original_async_client = httpx.AsyncClient

    def local_async_client(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(retrieval.httpx, "AsyncClient", local_async_client)
    monkeypatch.setattr(vk_main.httpx, "AsyncClient", local_async_client)
    monkeypatch.setattr(retrieval, "get_embedding", lambda _text: [0.0, 0.0, 0.0])
    monkeypatch.setattr(vk_main, "llama_embed", lambda _text: [0.0, 0.0, 0.0])
    monkeypatch.setattr(
        retrieval,
        "classify_intent",
        lambda *_args, **_kwargs: QueryIntent(
            intent_type="code_lookup",
            entities=["pkg", "main", "helper"],
            scope="this_project",
            time_window="all",
            needs_external=False,
            needs_ranking=False,
            needs_consolidation=False,
        ),
    )
    monkeypatch.setattr(retrieval, "_retrieve_engram", lambda *_args, **_kwargs: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(retrieval, "_retrieve_facts", lambda *_args, **_kwargs: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(seq_main, "STAGING_BUFFER_PATH", tmp_path / "staging")
    monkeypatch.setattr(vk_main, "_reminders_path", tmp_path / "reminders")
    vk_main._reminders_path.mkdir(parents=True, exist_ok=True)

    async def run_flow():
        async with original_async_client(transport=transport) as client:
            await upsert_repository_index(
                str(tmp_path),
                qdrant_url="http://127.0.0.1:6333",
                collection="automem",
                client=client,
                embed_fn=lambda _text: [0.0, 0.0, 0.0],
            )

        context_json = await vk_main.request_context(
            query="Inspect pkg/main.py and its helper dependency",
            intent="answer",
            token_budget=4000,
        )
        reminder_json = await vk_main.push_reminder(
            query="pkg/main.py helper",
            reason="complex_coding_task",
            agent_id="test-agent",
        )
        staged_json = await seq_main.propose_change_set(
            "sess-e2e",
            "apply local fix",
            json.dumps([{"path": str(tmp_path / "result.txt"), "content": "ok"}]),
        )
        applied_json = await seq_main.apply_sandbox(
            json.loads(staged_json)["change_set_id"],
            approved=True,
        )
        return (
            json.loads(context_json),
            json.loads(reminder_json),
            json.loads(staged_json),
            json.loads(applied_json),
        )

    context_payload, reminder_payload, staged_payload, applied_payload = asyncio.run(run_flow())

    assert context_payload["metadata"]["sources_used"]
    assert "pkg/main.py" in context_payload["injection_text"]
    assert "def helper()" in context_payload["injection_text"]
    assert reminder_payload["status"] == "reminder_pushed"
    assert staged_payload["status"] == "staged"
    assert applied_payload["status"] == "applied"
    assert (tmp_path / "result.txt").read_text() == "ok"
    assert request_log
    assert all(httpx.URL(url).host in allowed_hosts for url in request_log)


def test_project_audit_virtualizes_over_hundred_files_within_budget(tmp_path: Path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()

    for idx in range(120):
        lines = [
            f"# module {idx}",
            f"def feature_{idx}():",
            "    value = 0",
        ]
        if idx > 0:
            lines.insert(0, f"from app.module_{idx-1} import feature_{idx-1}")
            lines.append(f"    return feature_{idx-1}() + value")
        else:
            lines.append("    return value")
        (app / f"module_{idx}.py").write_text("\n".join(lines) + "\n")

    transport_points: list[dict] = []

    def qdrant_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/collections":
            return httpx.Response(200, json={"result": {"collections": [{"name": "automem"}]}})

        if request.method == "PUT" and request.url.path == "/collections/automem/points":
            transport_points[:] = json.loads(request.read().decode())["points"]
            return httpx.Response(200, json={"result": {"status": "ok"}})

        if request.method == "POST" and request.url.path in {
            "/collections/automem/points/search",
            "/collections/automem/points/search/sparse",
        }:
            body = json.loads(request.read().decode())
            limit = body.get("limit", 10)
            must = body.get("filter", {}).get("must", [])
            wanted_layer = None
            for clause in must:
                if clause.get("key") == "layer":
                    wanted_layer = clause.get("match", {}).get("value")
            results = []
            for point in transport_points:
                payload = point["payload"]
                if wanted_layer is not None and payload.get("layer") != wanted_layer:
                    continue
                results.append({"id": point["id"], "score": 0.9, "payload": payload})
            return httpx.Response(200, json={"result": results[:limit]})

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(qdrant_handler)
    original_async_client = httpx.AsyncClient

    def local_async_client(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(retrieval.httpx, "AsyncClient", local_async_client)
    monkeypatch.setattr(retrieval, "get_embedding", lambda _text: [0.0, 0.0, 0.0])
    monkeypatch.setattr(
        retrieval,
        "classify_intent",
        lambda *_args, **_kwargs: QueryIntent(
            intent_type="code_lookup",
            entities=["app", "module_119", "feature_119"],
            scope="this_project",
            time_window="all",
            needs_external=False,
            needs_ranking=False,
            needs_consolidation=False,
        ),
    )
    monkeypatch.setattr(retrieval, "_retrieve_engram", lambda *_args, **_kwargs: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(retrieval, "_retrieve_facts", lambda *_args, **_kwargs: asyncio.sleep(0, result=[]))

    async def run_audit():
        async with original_async_client(transport=transport) as client:
            await upsert_repository_index(
                str(tmp_path),
                qdrant_url="http://127.0.0.1:6333",
                collection="automem",
                client=client,
                embed_fn=lambda _text: [0.0, 0.0, 0.0],
            )
        return await retrieval.retrieve(
            "Run a project audit for app/module_119.py and follow dependencies",
            session_type="dev",
            token_budget=2500,
        )

    pack = asyncio.run(run_audit())

    assert len(list(app.glob("*.py"))) == 120
    assert any(section["source"] == "qdrant" for section in pack.sections)
    assert pack.total_tokens <= 2500
    assert pack.query.startswith("Run a project audit")
