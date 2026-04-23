import sys
import pytest
import json
from pathlib import Path

# Add src to pythonpath
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from automem.server import main as automem_main

# --- Unit Tests (SPEC-3.2 adapted for Worktrees) ---

@pytest.mark.asyncio
async def test_ingest_event_creates_memory_item_for_diff():
    """AC-3.2.1: ingest_event("diff_proposed", ...) crea MemoryItem en L1. Uses real git-diff strings now."""
    
    # Reset in-memory DB for test isolation
    automem_main.MEMORY_DB.clear()
    
    diff_payload = {
        "file_path": "test.py",
        "diff_text": "--- a/test.py\\n+++ b/test.py\\n@@ -1 +1 @@\\n-old\\n+new",
        "language": "python",
        "change_id": "test_commit_hash_123"
    }
    
    result_json = await automem_main.ingest_event(
        event_type="diff_proposed",
        content=json.dumps(diff_payload),
        source="ralph_worktree"
    )
    result = json.loads(result_json)
    
    assert result["status"] == "ingested"
    assert len(automem_main.MEMORY_DB) == 1
    
    mem_item = automem_main.MEMORY_DB[0]
    assert mem_item["layer"] == 1
    assert mem_item["type"] == "STEP"
    assert mem_item["metadata"]["event_type"] == "diff_proposed"
    assert mem_item["metadata"]["file_path"] == "test.py"
    assert json.loads(mem_item["content"]) == diff_payload["diff_text"]

@pytest.mark.asyncio
async def test_ingest_event_ignores_non_diff_events():
    """Verifies that other event types are ignored for now."""
    automem_main.MEMORY_DB.clear()
    
    result_json = await automem_main.ingest_event(
        event_type="user_login",
        content='{"user": "test"}',
        source="auth_service"
    )
    result = json.loads(result_json)
    
    assert result["status"] == "ignored"
    assert len(automem_main.MEMORY_DB) == 0
