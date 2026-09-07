"""Protocol-level E2E smoke test: spawn the unified MCP server as a real
subprocess (exactly like config/mcp.json does) and exercise tool handlers
through MCP JSON-RPC — the layer unit tests mock away.

Regression root — E2E audit 2026-09-07: four tools were broken in production
(`await None` deprecation leftovers in L3_facts.add_memory and
L2_conversations.search_conversations; threads/messages tables never created
on points-first DBs in conversation_db._ensure_db) while the 403-test suite
stayed green, because nothing exercised the wire protocol against a
production-shaped database.

Sandbox: a fresh MEMORY_SERVER_DIR whose data/memory.db is pre-shaped BY
MemoryDB itself (points schema, NO threads tables) — the exact deployment
failure mode. Externally-set env wins over config/.env (env_loader contract),
so the real deployment is never touched.

Marked `integration` so it runs in the default suite: it boots one subprocess
and makes ~10 fast tool calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "src" / "unified" / "server" / "main.py"

# Env vars that could redirect the subprocess to the developer's real
# deployment. The sandbox sets MEMORY_SERVER_DIR/DATA_DIR itself; everything
# else memory-related must go.
_STRIP_ENV = [
    "MEMORY_DIR", "MEMORY_EVENTS_JSONL", "AUTOMEM_JSONL", "STAGING_BUFFER",
    "L3_DECISIONS_PATH", "DREAM_PATH", "THOUGHTS_PATH", "HEARTBEATS_PATH",
    "REMINDERS_PATH", "VAULT_PATH", "LOG_DIR", "OBSERVE_LOG_DIR",
    "MEMORY_AGENT_ID", "MEMORY_AGENT_TOKEN", "MEMORY_IDENTITY_MODE",
    "MEMORY_HTTP_TOKEN",
]

MARKER = "E2EPROTOCOLSMOKE"


def _shape_points_first_db(db_path: Path) -> None:
    """Create the DB exactly like production: MemoryDB boots first and creates
    the points schema — leaving threads/messages uninitialized (P0-2 trigger).
    """
    from shared.memory_db import MemoryDB  # conftest puts src/ on sys.path

    MemoryDB(db_path=str(db_path))


@pytest.fixture()
def sandbox(tmp_path: Path):
    root = tmp_path / "memory-zero"
    (root / "config").mkdir(parents=True)
    data = root / "data"
    data.mkdir()
    _shape_points_first_db(data / "memory.db")
    return {"root": root, "data": data, "db": data / "memory.db"}


@pytest.fixture()
def server(sandbox):
    env = dict(os.environ)
    env["MEMORY_SERVER_DIR"] = str(sandbox["root"])
    env["DATA_DIR"] = str(sandbox["data"])
    env["PYTHONPATH"] = str(REPO / "src")
    for key in _STRIP_ENV:
        env.pop(key, None)

    proc = subprocess.Popen(
        [sys.executable, "-u", str(SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, cwd=str(REPO),
    )

    class Client:
        def __init__(self) -> None:
            self._id = 0
            self._handshake()

        def _send(self, obj: dict) -> None:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()

        def _recv(self) -> dict:
            assert proc.stdout is not None
            line = proc.stdout.readline()
            if not line.strip():
                err = proc.stderr.read() if proc.stderr else ""
                proc.terminate()
                raise AssertionError(f"server died mid-protocol. stderr:\n{err[-2000:]}")
            return json.loads(line)

        def _handshake(self) -> dict:
            self._send({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                   "clientInfo": {"name": "protocol-smoke", "version": "1"}}})
            resp = self._recv()
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return resp["result"]

        def call(self, tool: str, args: dict) -> dict:
            self._id += 1
            self._send({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                        "params": {"name": tool, "arguments": args}})
            resp = self._recv()
            assert "error" not in resp, resp["error"]
            text = "".join(c.get("text", "") for c in resp["result"].get("content", []))
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"__raw__": text}

        def list_tools(self) -> list[str]:
            self._id += 1
            self._send({"jsonrpc": "2.0", "id": self._id, "method": "tools/list"})
            return [t["name"] for t in self._recv()["result"]["tools"]]

    client = Client()
    yield client
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


OWNER = "smoke-owner-agent"
INTRUDER = "smoke-intruder-agent"


def test_unified_server_boots_with_full_toolbelt(server):
    tools = server.list_tools()
    assert len(tools) >= 50, f"expected the full toolbelt, got {len(tools)}"
    for required in ("health_check", "L3_facts_add_memory",
                     "L2_conversations_save_conversation", "L5_routing_request_context"):
        assert required in tools


def test_l3_facts_add_memory_roundtrip(server, sandbox):
    """P0-1 regression: add_memory must store (was: `await None` TypeError)."""
    content = f"{MARKER} quantum flux blueprint"
    resp = server.call("L3_facts_add_memory", {"content": content, "user_id": OWNER})
    assert resp.get("status") == "stored", resp
    memory_id = resp["memory_id"]

    # Owner sees it; intruder does not (engine-level scope filter, ISO-05).
    found = server.call("L3_facts_search_memory", {"query": MARKER, "user_id": OWNER, "limit": 10})
    assert MARKER in json.dumps(found), found
    intruder = server.call("L3_facts_search_memory", {"query": MARKER, "user_id": INTRUDER, "limit": 10})
    assert MARKER not in json.dumps(intruder), "cross-tenant leak!"

    # P1 regression: deleting the point must also purge the FTS index.
    # Guard: the content must be IN the index before the delete.
    with sqlite3.connect(sandbox["db"]) as conn:
        in_fts = conn.execute(
            "SELECT COUNT(*) FROM points_fts WHERE points_fts MATCH ?", (MARKER,)
        ).fetchone()[0]
    assert in_fts >= 1, "FTS sync on upsert is broken — delete assertion would be vacuous"

    deleted = server.call("L3_facts_delete_memory", {"memory_id": memory_id, "user_id": OWNER})
    assert "not_found" not in json.dumps(deleted).lower(), deleted

    with sqlite3.connect(sandbox["db"]) as conn:
        in_points = conn.execute(
            "SELECT COUNT(*) FROM points WHERE payload LIKE ?", (f"%{MARKER}%",)
        ).fetchone()[0]
        in_fts = conn.execute(
            "SELECT COUNT(*) FROM points_fts WHERE points_fts MATCH ?", (MARKER,)
        ).fetchone()[0]
    assert in_points == 0, "point survived delete"
    assert in_fts == 0, "deleted content lingers in points_fts (retention bug)"


def test_l2_conversations_survive_points_first_db(server, sandbox):
    """P0-2 regression: threads/messages must exist on a points-first DB."""
    thread = f"{MARKER}-thread"
    messages = json.dumps([{"role": "user", "content": f"{MARKER} hello world"}])
    saved = server.call("L2_conversations_save_conversation",
                        {"thread_id": thread, "messages_json": messages})
    assert saved.get("status") == "saved", saved

    got = server.call("L2_conversations_get_conversation", {"thread_id": thread})
    assert MARKER in json.dumps(got), got

    # P0-3 regression: search must not die on the removed `await None`.
    hits = server.call("L2_conversations_search_conversations", {"query": MARKER})
    raw = json.dumps(hits)
    assert "await" not in raw and MARKER in raw, hits
