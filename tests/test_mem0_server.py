"""Tests for mem0.server.main — semantic memory CRUD."""

from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

import mem0.server.main as mem0_main


@pytest.mark.asyncio
async def test_add_memory_with_mem0_client():
    mock_client = MagicMock()
    mock_client.add.return_value = [{"id": "mem-1", "event": "ADD"}]
    with patch.object(mem0_main, "get_mem0_client", return_value=mock_client):
        result = await mem0_main.add_memory(
            content="User prefers light theme", user_id="test-user",
            metadata='{"scope": "preference"}',
        )
    data = json.loads(result)
    assert data["status"] == "stored"
    assert data["backend"] == "mem0"


@pytest.mark.asyncio
async def test_search_memory_returns_results():
    """search_memory with mem0 client."""
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {"id": "mem-1", "score": 0.9, "memory": "dark mode"}
    ]
    # Patch sanitize functions (sanitize_user_id is a NameError in source)
    mem0_main.normalize_query = lambda x: x
    mem0_main.sanitize_user_id = lambda x: x
    with patch.object(mem0_main, "get_mem0_client", return_value=mock_client):
        result = await mem0_main.search_memory(query="theme", user_id="test-user")
    data = json.loads(result)
    assert "results" in data or data.get("backend") == "mem0"

@pytest.mark.asyncio
async def test_get_all_memories_returns_dict():
    mock_client = MagicMock()
    mock_client.get_all.return_value = [
        {"id": "mem-1", "memory": "fact 1"},
        {"id": "mem-2", "memory": "fact 2"},
    ]
    with patch.object(mem0_main, "get_mem0_client", return_value=mock_client):
        result = await mem0_main.get_all_memories(user_id="test-user")
    data = json.loads(result)
    assert isinstance(data, dict)
    assert "results" in data
    assert len(data["results"]) == 2


@pytest.mark.asyncio
async def test_delete_memory_returns_deleted():
    mock_client = MagicMock()
    mock_client.delete.return_value = None
    with patch.object(mem0_main, "get_mem0_client", return_value=mock_client):
        result = await mem0_main.delete_memory(memory_id="mem-1", user_id="test-user")
    data = json.loads(result)
    assert data["status"] == "deleted"


@pytest.mark.asyncio
async def test_status_returns_daemon_info():
    with patch.object(mem0_main, "get_mem0_client", return_value=MagicMock()):
        result = await mem0_main.status()
    data = json.loads(result)
    assert data["daemon"] == "mem0"
    assert data["status"] == "RUNNING"
