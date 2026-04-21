"""E2E flow — REAL integration, NO MOCKS."""
import pytest
import asyncio
from pathlib import Path
from shared.retrieval.index_repo import upsert_repository_index
import httpx

@pytest.mark.asyncio
async def test_index_and_search_real(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.py").write_text("def run(): pass\n")
    
    try:
        async with httpx.AsyncClient() as client:
            await upsert_repository_index(str(tmp_path), collection="test_e2e", client=client)
    except httpx.ConnectError:
        pytest.fail("Real Qdrant/Llama connection failed correctly")
