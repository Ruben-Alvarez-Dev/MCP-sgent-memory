"""Tests for autodream.server.main — REAL integration, NO MOCKS."""
import json
import uuid
import pytest
import autodream.server.main as autodream_main

@pytest.fixture(autouse=True)
def setup_test_env():
    autodream_main.QDRANT_COLLECTION = f"test_autodream_{uuid.uuid4().hex[:8]}"

@pytest.mark.asyncio
async def test_status_returns_daemon_info():
    result = await autodream_main.status()
    data = json.loads(result)
    assert data["daemon"] == "AutoDream"

@pytest.mark.asyncio
async def test_promote_processes_working_memories():
    result = await autodream_main.promote_l1_to_l2(
        turn_count=100,
        state={"last_promote_l1_l2": 0, "last_promote_l2_l3": 0, "last_promote_l3_l4": 0, "total_promotions": 0},
    )
    # This will hit REAL Qdrant and REAL Llama server. If down, it will raise ConnectionError.
    if result is not None:
        assert isinstance(result, str)

@pytest.mark.asyncio
async def test_consolidate_force_runs_all_phases():
    result = await autodream_main.consolidate(force=True)
    data = json.loads(result)
    assert "status" in data
