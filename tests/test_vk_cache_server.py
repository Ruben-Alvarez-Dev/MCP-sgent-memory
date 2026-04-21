"""Tests for vk-cache.server.main — reminders, context shift, status."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

vk_main = importlib.import_module("vk-cache.server.main")


@pytest.fixture
def isolated_reminders(tmp_path, monkeypatch):
    reminders_dir = tmp_path / "reminders"
    reminders_dir.mkdir(parents=True)
    monkeypatch.setattr(vk_main, "_reminders_path", reminders_dir)
    return reminders_dir


def _mock_embed_and_qdrant():
    """Return context manager that mocks embed_text and search_qdrant."""
    return patch.object(vk_main, "search_qdrant", new_callable=AsyncMock, return_value=[{"id": "r1", "score": 0.9, "content": "test result", "scope": "agent", "layer": 1, "payload": {"content": "test", "layer": 1}}])


@pytest.mark.asyncio
async def test_push_reminder_creates_file(isolated_reminders):
    with _mock_embed_and_qdrant():
        result = await vk_main.push_reminder("auth expiry", "relevant_to_current_task", "agent-1")
    data = json.loads(result)
    assert data["status"] == "reminder_pushed"
    assert data["reminder_id"]
    assert len(list(isolated_reminders.glob("*.json"))) == 1


@pytest.mark.asyncio
async def test_push_reminder_stores_query(isolated_reminders):
    with _mock_embed_and_qdrant():
        await vk_main.push_reminder("DB migration", "recent_decision_not_used", "dev-1")
    files = list(isolated_reminders.glob("*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text())
    assert "migration" in str(stored).lower() or "DB" in str(stored)


@pytest.mark.asyncio
async def test_check_reminders_empty(isolated_reminders):
    result = await vk_main.check_reminders(agent_id="test-agent")
    data = json.loads(result)
    assert data.get("reminders") is None or data.get("reminders") == []


@pytest.mark.asyncio
async def test_check_reminders_finds_pushed(isolated_reminders):
    with _mock_embed_and_qdrant():
        await vk_main.push_reminder("test query", "relevant_to_current_task", "test-agent")
    result = await vk_main.check_reminders(agent_id="test-agent")
    data = json.loads(result)
    assert data.get("reminders") is not None
    assert len(data["reminders"]) >= 1


@pytest.mark.asyncio
async def test_dismiss_reminder_removes_file(isolated_reminders):
    with _mock_embed_and_qdrant():
        pushed = json.loads(await vk_main.push_reminder("temp", "test", "agent-1"))
    rid = pushed["reminder_id"]
    result = await vk_main.dismiss_reminder(rid)
    data = json.loads(result)
    assert data["status"] == "dismissed"
    assert not (isolated_reminders / f"{rid}.json").exists()


@pytest.mark.asyncio
async def test_dismiss_nonexistent(isolated_reminders):
    result = await vk_main.dismiss_reminder("nonexistent-id")
    data = json.loads(result)
    assert data["status"] == "not_found"


@pytest.mark.asyncio
async def test_detect_context_shift_returns_json():
    with _mock_embed_and_qdrant():
        result = await vk_main.detect_context_shift("auth?", "css fix", "test")
    data = json.loads(result)
    assert "shift_detected" in data


@pytest.mark.asyncio
async def test_status_returns_server_info():
    mock_cls = MagicMock()
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"result": {"collections": []}}
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_cls.return_value = mock_client

    with patch.object(vk_main.httpx, "AsyncClient", new=mock_cls):
        result = await vk_main.status()
    data = json.loads(result)
    assert data.get("server") == "vk-cache" or "status" in data
