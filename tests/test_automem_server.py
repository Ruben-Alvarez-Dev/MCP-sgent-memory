"""Tests for automem.server.main — event ingestion, memory storage."""

from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock

import pytest

import automem.server.main as automem_main


@pytest.mark.asyncio
async def test_ingest_diff_event():
    with patch.object(automem_main, "store_memory", new_callable=AsyncMock), \
         patch.object(automem_main, "append_raw_jsonl"):
        result = await automem_main.ingest_event(
            event_type="diff_proposed",
            content=json.dumps({
                "file_path": "test.py",
                "diff_text": "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new",
                "language": "python",
                "change_id": "abc123",
            }),
            source="ralph_worktree",
        )
    data = json.loads(result)
    assert data["status"] == "ingested"


@pytest.mark.asyncio
async def test_ingest_terminal_event():
    with patch.object(automem_main, "store_memory", new_callable=AsyncMock), \
         patch.object(automem_main, "append_raw_jsonl"):
        result = await automem_main.ingest_event(
            event_type="terminal",
            content='{"cmd": "ls", "exit": 0}',
            source="bash",
        )
    data = json.loads(result)
    assert data["status"] == "ingested"


@pytest.mark.asyncio
async def test_memorize_stores_fact():
    with patch.object(automem_main, "store_memory", new_callable=AsyncMock) as mock_store:
        result = await automem_main.memorize(
            content="User prefers dark mode",
            mem_type="preference",
            scope="personal",
            importance=0.8,
        )
    data = json.loads(result)
    assert data["status"] == "stored"
    mock_store.assert_called_once()


@pytest.mark.asyncio
async def test_memorize_rejects_empty_content():
    with pytest.raises(Exception):  # SanitizeError
        await automem_main.memorize(content="", mem_type="fact")


@pytest.mark.asyncio
async def test_heartbeat_returns_agent_id():
    with patch.object(automem_main, "store_memory", new_callable=AsyncMock):
        result = await automem_main.heartbeat(agent_id="test-agent", turn_count=5)
    data = json.loads(result)
    assert data["agent_id"] == "test-agent"
    assert data["turn_count"] == 5


@pytest.mark.asyncio
async def test_status_returns_daemon_info():
    result = await automem_main.status()
    data = json.loads(result)
    assert data["daemon"] == "AutoMem"
    assert "qdrant" in data
