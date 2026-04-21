"""Tests for shared.retrieval.index_repo — REAL integration, NO MOCKS."""
import pytest
import uuid
import httpx
from shared.retrieval.index_repo import build_repo_index_points, upsert_repository_index

@pytest.mark.asyncio
async def test_upsert_repository_index_real(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.py").write_text("def run():\n    return 1\n")
    
    collection = f"test_idx_{uuid.uuid4().hex[:8]}"
    
    # Actually hits Qdrant. Will fail if Qdrant is down.
    try:
        async with httpx.AsyncClient() as client:
            result = await upsert_repository_index(
                str(tmp_path),
                qdrant_url="http://127.0.0.1:6333",
                collection=collection,
                client=client,
            )
        assert result["indexed_points"] >= 1
    except httpx.ConnectError:
        pytest.fail("Qdrant is down - real test failed correctly")
