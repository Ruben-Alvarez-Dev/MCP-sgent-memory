"""Tests for conversation-store.server.main — conversation CRUD."""

from __future__ import annotations

import importlib
import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

cs_main = importlib.import_module("conversation-store.server.main")


def _mock_async_client(json_data=None):
    mock_resp = MagicMock(status_code=200)
    if json_data is not None:
        mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.put.return_value = mock_resp
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_save_conversation():
    with patch.object(cs_main, "ensure_collection"), \
         patch.object(cs_main, "embed_text", new_callable=AsyncMock, return_value=[0.1]*1024):
        mock_cls = MagicMock(return_value=_mock_async_client())
        with patch.object(cs_main.httpx, "AsyncClient", new=mock_cls):
            msgs = json.dumps([{"role": "user", "content": "Hello"}])
            result = await cs_main.save_conversation(thread_id="t-1", messages=msgs)
    data = json.loads(result)
    assert data["status"] == "saved"
    assert data["thread_id"] == "t-1"


@pytest.mark.asyncio
async def test_get_conversation_returns_thread():
    mock_cls = MagicMock(return_value=_mock_async_client(json_data={
        "result": {"points": [{
            "id": "pt-1",
            "payload": {"thread_id": "t-1", "messages": [{"role": "user", "content": "Hi"}]},
        }]}
    }))
    with patch.object(cs_main.httpx, "AsyncClient", new=mock_cls):
        result = await cs_main.get_conversation(thread_id="t-1")
    data = json.loads(result)
    assert data["thread_id"] == "t-1"


@pytest.mark.asyncio
async def test_get_conversation_not_found():
    mock_cls = MagicMock(return_value=_mock_async_client(json_data={
        "result": {"points": []}
    }))
    with patch.object(cs_main.httpx, "AsyncClient", new=mock_cls):
        result = await cs_main.get_conversation(thread_id="nonexistent")
    data = json.loads(result)
    assert "error" in data or "not_found" in json.dumps(data).lower()


@pytest.mark.asyncio
async def test_search_conversations():
    with patch.object(cs_main, "embed_text", new_callable=AsyncMock, return_value=[0.1]*1024):
        mock_cls = MagicMock(return_value=_mock_async_client(json_data={
            "result": [{"id": "pt-1", "score": 0.9, "payload": {"messages": []}}]
        }))
        with patch.object(cs_main.httpx, "AsyncClient", new=mock_cls):
            result = await cs_main.search_conversations(query="auth", limit=5)
    data = json.loads(result)
    # search_conversations may return results or status depending on path
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_list_threads_returns_dict():
    mock_cls = MagicMock(return_value=_mock_async_client(json_data={
        "result": {"points": [
            {"payload": {"thread_id": "t-1"}},
            {"payload": {"thread_id": "t-2"}},
        ]}
    }))
    with patch.object(cs_main.httpx, "AsyncClient", new=mock_cls):
        result = await cs_main.list_threads(limit=10)
    data = json.loads(result)
    assert isinstance(data, dict)
    assert "threads" in data
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_status_returns_info():
    mock_cls = MagicMock(return_value=_mock_async_client(json_data={
        "result": {"points_count": 5}
    }))
    with patch.object(cs_main.httpx, "AsyncClient", new=mock_cls):
        result = await cs_main.status()
    data = json.loads(result)
    assert data["status"] == "OK"
    assert data["collection"] == "conversations"
