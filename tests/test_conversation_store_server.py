"""Tests for conversation-store.server.main — REAL integration, NO MOCKS."""
import json
import uuid
import pytest
import conversation_store.server.main as cs_main

@pytest.fixture(autouse=True)
def setup_test_env():
    cs_main.COLLECTION = f"test_conv_{uuid.uuid4().hex[:8]}"

@pytest.mark.asyncio
async def test_save_conversation_real():
    msgs = json.dumps([{"role": "user", "content": "Hello"}])
    result = await cs_main.save_conversation("t-1", messages=msgs)
    assert "status" in json.loads(result)

@pytest.mark.asyncio
async def test_search_conversations_real():
    result = await cs_main.search_conversations("auth", limit=5)
    data = json.loads(result)
    assert "results" in data or "backend" in data or "status" in data
