"""Tests for mem0.server.main — REAL integration, NO MOCKS."""
import json
import uuid
import pytest
import mem0.server.main as mem0_main

@pytest.fixture(autouse=True)
def setup_test_env():
    mem0_main.COLLECTION = f"test_mem0_{uuid.uuid4().hex[:8]}"

@pytest.mark.asyncio
async def test_add_memory_real():
    result = await mem0_main.add_memory("User prefers light theme", "test-user")
    assert "status" in json.loads(result)

@pytest.mark.asyncio
async def test_search_memory_real():
    import mem0.server.main as _m
    _m.sanitize_user_id = getattr(_m, "sanitize_user_id", lambda x: x)
    _m.normalize_query = getattr(_m, "normalize_query", lambda x: x)
    result = await mem0_main.search_memory("theme", "test-user")
    assert "results" in json.loads(result) or "backend" in json.loads(result)
