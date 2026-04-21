"""Tests for vk-cache.server.main — REAL integration, NO MOCKS."""
import json
import uuid
import pytest
import vk_cache.server.main as vk_main

@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    vk_main.QDRANT_COLLECTION = f"test_vkcache_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(vk_main, "_reminders_path", tmp_path / "reminders")
    (tmp_path / "reminders").mkdir()

@pytest.mark.asyncio
async def test_push_reminder_real():
    result = await vk_main.push_reminder("auth expiry", "relevant", "agent-1")
    data = json.loads(result)
    assert "status" in data

@pytest.mark.asyncio
async def test_detect_context_shift_real():
    result = await vk_main.detect_context_shift("auth?", "css fix", "test")
    data = json.loads(result)
    assert "shift_detected" in data

@pytest.mark.asyncio
async def test_status_real():
    result = await vk_main.status()
    data = json.loads(result)
    assert data["daemon"] == "vk-cache"
