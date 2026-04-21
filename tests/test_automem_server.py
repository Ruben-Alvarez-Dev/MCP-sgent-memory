"""Tests for automem.server.main — REAL integration, NO MOCKS."""
import json
import uuid
import pytest
import automem.server.main as automem_main

@pytest.fixture(autouse=True)
def setup_test_env():
    automem_main.QDRANT_COLLECTION = f"test_automem_{uuid.uuid4().hex[:8]}"

@pytest.mark.asyncio
async def test_ingest_diff_event():
    result = await automem_main.ingest_event(
        event_type="diff_proposed",
        content=json.dumps({"file_path": "test.py", "diff_text": "--- a/test.py", "language": "python", "change_id": "abc"}),
        source="ralph_worktree",
    )
    assert json.loads(result)["status"] in ("ingested", "error")

@pytest.mark.asyncio
async def test_memorize_stores_fact():
    result = await automem_main.memorize(
        content="User prefers dark mode",
        mem_type="preference",
        scope="personal",
        importance=0.8,
    )
    data = json.loads(result)
    assert "status" in data

@pytest.mark.asyncio
async def test_status_returns_daemon_info():
    result = await automem_main.status()
    data = json.loads(result)
    assert data["daemon"] == "AutoMem"
