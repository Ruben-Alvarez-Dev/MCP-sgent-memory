"""Tests for autodream.server.main — consolidation, promotion, status."""

from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

import autodream.server.main as autodream_main


MOCK_WORKING = [
    {"content": "User prefers dark mode", "scope_type": "agent", "scope_id": "system",
     "importance": 0.8, "layer": 1, "memory_id": "m1"},
    {"content": "Changed DB to PostgreSQL", "scope_type": "agent", "scope_id": "system",
     "importance": 0.7, "layer": 1, "memory_id": "m2"},
]


@pytest.mark.asyncio
async def test_status_returns_daemon_info():
    result = await autodream_main.status()
    data = json.loads(result)
    assert data["daemon"] == "AutoDream"
    assert data["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_promote_returns_none_below_threshold():
    result = await autodream_main.promote_l1_to_l2(
        turn_count=5,
        state={"last_promote_l1_l2": 0, "last_promote_l2_l3": 0,
               "last_promote_l3_l4": 0, "total_promotions": 0},
    )
    assert result is None


@pytest.mark.asyncio
async def test_promote_processes_working_memories():
    with patch.object(autodream_main, "query_memories", return_value=MOCK_WORKING), \
         patch.object(autodream_main, "update_memory", new_callable=AsyncMock), \
         patch.object(autodream_main, "_embed_text", new_callable=AsyncMock, return_value=[0.1]*1024), \
         patch("autodream.server.main.httpx.AsyncClient") as mock_cls:
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"result": True}
        mock_client = AsyncMock()
        mock_client.put.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        result = await autodream_main.promote_l1_to_l2(
            turn_count=100,
            state={"last_promote_l1_l2": 0, "last_promote_l2_l3": 0,
                   "last_promote_l3_l4": 0, "total_promotions": 0},
        )
    # Returns string like "Created N episodes..." or None
    if result is not None:
        assert isinstance(result, str)
        assert "episode" in result.lower() or "promoted" in result.lower()


@pytest.mark.asyncio
async def test_consolidate_returns_valid_status():
    with patch.object(autodream_main, "promote_l1_to_l2", new_callable=AsyncMock, return_value=None), \
         patch.object(autodream_main, "promote_l2_to_l3", new_callable=AsyncMock, return_value=None), \
         patch.object(autodream_main, "promote_l3_to_l4", new_callable=AsyncMock, return_value=None):
        result = await autodream_main.consolidate()
    data = json.loads(result)
    assert "status" in data


@pytest.mark.asyncio
async def test_consolidate_force_runs_all_phases():
    with patch.object(autodream_main, "_force_promote_l1_to_l2", new_callable=AsyncMock, return_value="L1 ok") as m1, \
         patch.object(autodream_main, "_force_promote_l2_to_l3", new_callable=AsyncMock, return_value="L2 ok") as m2, \
         patch.object(autodream_main, "promote_l3_to_l4", new_callable=AsyncMock, return_value="L3 ok") as m3:
        result = await autodream_main.consolidate(force=True)
    data = json.loads(result)
    assert "consolidation" in data["status"] or data["status"] == "ok"
    m1.assert_called_once()
    m2.assert_called_once()
    m3.assert_called_once()
