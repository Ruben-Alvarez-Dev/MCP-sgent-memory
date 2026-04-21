"""Tests for engram.server.main — model packs, decisions, vault, status."""

from __future__ import annotations

import json

import pytest

import engram.server.main as engram_main
from unittest.mock import patch


@pytest.fixture
def mock_engram_env(tmp_path, monkeypatch):
    packs_dir = tmp_path / "model-packs"
    packs_dir.mkdir()
    (packs_dir / "default.yaml").write_text(
        "name: default\nroles:\n  coder:\n    temperature: 0.1\n  planner:\n    temperature: 0.7\n"
    )
    (packs_dir / "creative.yaml").write_text(
        "name: creative\nroles:\n  coder:\n    temperature: 0.5\n"
    )
    monkeypatch.setattr(engram_main, "_MODEL_PACKS_DIR", packs_dir)
    monkeypatch.setattr(engram_main, "_get_packs_dir", lambda: packs_dir)
    return packs_dir


# ── Model packs ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_model_pack_returns_pack(mock_engram_env):
    result = await engram_main.get_model_pack("default")
    data = json.loads(result)
    pack = data.get("pack", data)
    assert pack["name"] == "default"
    assert "coder" in pack["roles"]


@pytest.mark.asyncio
async def test_get_model_pack_nonexistent_returns_fallback(mock_engram_env):
    result = await engram_main.get_model_pack("nonexistent")
    data = json.loads(result)
    assert data["status"] == "fallback"


@pytest.mark.asyncio
async def test_list_model_packs_returns_dict(mock_engram_env):
    result = await engram_main.list_model_packs()
    data = json.loads(result)
    assert isinstance(data, dict)
    assert "packs" in data
    names = [p.get("name") for p in data["packs"]]
    assert "default" in names


@pytest.mark.asyncio
async def test_set_model_pack_saves(mock_engram_env):
    yaml_content = '{"name": "exp", "roles": {"coder": {"temperature": 0.0}}}'
    result = await engram_main.set_model_pack("exp", yaml_content)
    data = json.loads(result)
    assert data["status"] == "saved"


@pytest.mark.asyncio
async def test_set_model_pack_rejects_invalid_roles():
    result = await engram_main.set_model_pack("bad", '{"name": "bad", "roles": }')
    data = json.loads(result)
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_set_model_pack_rejects_missing_roles():
    result = await engram_main.set_model_pack("nope", '{"name": "nope"}')
    data = json.loads(result)
    assert data["status"] == "error"


# ── Decisions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_decision_returns_saved():
    result = await engram_main.save_decision(
        title="Use PostgreSQL",
        content="Chose PostgreSQL over MongoDB",
        category="decision",
        tags="database",
        scope="agent",
    )
    data = json.loads(result)
    assert data["status"] == "saved"
    assert "file" in data
    assert data["category"] == "decision"


@pytest.mark.asyncio
async def test_search_decisions_empty():
    with patch.object(engram_main, "_get_engram_files", return_value=[]):
        result = await engram_main.search_decisions("database")
    data = json.loads(result)
    assert data["results"] == []


# ── Status ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_returns_info():
    result = await engram_main.status()
    data = json.loads(result)
    assert "status" in data
