import sys
import pytest
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MOCK_WORKING = [{"content": "test", "scope_type": "agent", "scope_id": "system", "importance": 0.5, "layer": 1}]


@pytest.mark.asyncio
async def test_consolidate_runs_without_error():
    """Consolidate function runs and returns valid JSON status."""
    with patch("autodream.server.main.query_memories", return_value=MOCK_WORKING), \
         patch("autodream.server.main.update_memory", new_callable=AsyncMock), \
         patch("autodream.server.main.promote_l1_to_l2", new_callable=AsyncMock, return_value='{"status": "ok"}'), \
         patch("autodream.server.main.promote_l2_to_l3", new_callable=AsyncMock, return_value='{"status": "ok"}'), \
         patch("autodream.server.main.promote_l3_to_l4", new_callable=AsyncMock, return_value='{"status": "ok"}'):
        from autodream.server.main import consolidate
        result_json = await consolidate()
        result = json.loads(result_json)
        assert "status" in result


@pytest.mark.asyncio
async def test_promote_l1_to_l2_returns_status():
    """promote_l1_to_l2 returns valid response when threshold is met."""
    with patch("autodream.server.main.query_memories", return_value=MOCK_WORKING), \
         patch("autodream.server.main.update_memory", new_callable=AsyncMock):
        from autodream.server.main import promote_l1_to_l2
        result_json = await promote_l1_to_l2(
            turn_count=100,
            state={"last_promote_l1_l2": 0, "last_promote_l2_l3": 0,
                   "last_promote_l3_l4": 0, "total_promotions": 0}
        )
        if result_json is not None:
            result = json.loads(result_json)
            assert "status" in result
        # None is also valid (no memories to promote after grouping)


@pytest.mark.asyncio
async def test_status_returns_server_info():
    """Status endpoint returns daemon information."""
    from autodream.server.main import status
    result_json = await status()
    data = json.loads(result_json)
    assert data.get("daemon") == "AutoDream"
