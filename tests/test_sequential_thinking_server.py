"""Tests for sequential-thinking server (real 522-line implementation)."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _load_real_sequential_thinking(tmp_path):
    fastmcp = types.ModuleType("mcp.server.fastmcp")
    class D:
        def __init__(s,*a,**k): pass
        def tool(s):
            def d(f): return f
            return d
        def run(s): pass
    fastmcp.FastMCP = D
    mcp_m = types.ModuleType("mcp")
    mcp_m.server = types.ModuleType("mcp.server")
    mcp_m.server.fastmcp = fastmcp
    sys.modules["mcp"] = mcp_m
    sys.modules["mcp.server"] = mcp_m.server
    sys.modules["mcp.server.fastmcp"] = fastmcp

    spec = importlib.util.spec_from_file_location(
        "seq_thinking_real", SRC / "sequential-thinking" / "server" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    mod.STAGING_BUFFER_PATH = tmp_path / "staging"
    return mod


@pytest.mark.asyncio
async def test_sequential_thinking_returns_dict(tmp_path):
    mod = _load_real_sequential_thinking(tmp_path)
    result = await mod.sequential_thinking("design the auth system")
    data = json.loads(result)
    assert isinstance(data, dict)
    assert "problem" in data
    assert "session_id" in data
    assert "total_steps" in data


@pytest.mark.asyncio
async def test_sequential_thinking_has_steps(tmp_path):
    mod = _load_real_sequential_thinking(tmp_path)
    result = await mod.sequential_thinking("solve X")
    data = json.loads(result)
    assert data["total_steps"] > 0
    assert "thinking_framework" in data


@pytest.mark.asyncio
async def test_create_plan_returns_dict(tmp_path):
    mod = _load_real_sequential_thinking(tmp_path)
    result = await mod.create_plan("build feature X")
    data = json.loads(result)
    assert isinstance(data, dict)
    assert "goal" in data
    assert "critical_path" in data or "steps" in data


@pytest.mark.asyncio
async def test_propose_and_apply_change_set(tmp_path):
    mod = _load_real_sequential_thinking(tmp_path)
    mod.STAGING_BUFFER_PATH = tmp_path / "staging"

    target = tmp_path / "output.txt"
    changes = json.dumps([{"path": str(target), "content": "hello world"}])

    staged = json.loads(await mod.propose_change_set("sess-1", "demo", changes))
    assert staged["status"] == "staged"

    applied = json.loads(await mod.apply_sandbox(staged["change_set_id"], approved=True))
    assert applied["status"] == "applied"
    assert target.read_text() == "hello world"


@pytest.mark.asyncio
async def test_apply_rejected_does_not_write(tmp_path):
    mod = _load_real_sequential_thinking(tmp_path)
    mod.STAGING_BUFFER_PATH = tmp_path / "staging"

    target = tmp_path / "nope.txt"
    changes = json.dumps([{"path": str(target), "content": "no"}])

    staged = json.loads(await mod.propose_change_set("sess-2", "bad", changes))
    result = json.loads(await mod.apply_sandbox(staged["change_set_id"], approved=False))
    assert result["status"] == "awaiting_approval"
    assert not target.exists()
