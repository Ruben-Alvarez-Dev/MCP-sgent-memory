"""Tests for engram.server.main — REAL integration, NO MOCKS."""

from __future__ import annotations
import json
import pytest
import engram.server.main as engram_main

@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    engram_main._MODEL_PACKS_DIR = tmp_path / "model-packs"
    engram_main._get_packs_dir = lambda: tmp_path / "model-packs"
    (tmp_path / "model-packs").mkdir(parents=True, exist_ok=True)
    # create default pack
    (tmp_path / "model-packs" / "default.yaml").write_text("name: default\nroles:\n  coder:\n    temperature: 0.1\n")
    
    # Redirect decision path to temp
    monkeypatch.setenv("ENGRAM_PATH", str(tmp_path / "engram"))
    (tmp_path / "engram").mkdir()

@pytest.mark.asyncio
async def test_get_model_pack_real():
    result = await engram_main.get_model_pack("default")
    assert "default" in result

@pytest.mark.asyncio
async def test_save_decision_real():
    result = await engram_main.save_decision(
        title="Use PostgreSQL", 
        content="Chose PostgreSQL", 
        category="decision", 
        tags="db", 
        scope="agent"
    )
    data = json.loads(result)
    assert data.get("status") == "saved"
