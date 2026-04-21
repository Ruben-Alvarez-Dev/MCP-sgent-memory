import sys
import pytest
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.mark.asyncio
async def test_ingest_event_creates_diff_event():
    """ingest_event with diff_proposed returns ingested status."""
    with patch("automem.server.main.store_memory", new_callable=AsyncMock) as mock_store, \
         patch("automem.server.main.append_raw_jsonl") as mock_append:
        mock_store.return_value = None
        from automem.server.main import ingest_event

        diff_payload = {
            "file_path": "test.py",
            "diff_text": "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new",
            "language": "python",
            "change_id": "test_commit_hash_123",
        }
        result_json = await ingest_event(
            event_type="diff_proposed",
            content=json.dumps(diff_payload),
            source="ralph_worktree",
        )
        result = json.loads(result_json)
        assert result["status"] == "ingested"
        assert result.get("status") == "ingested" or result.get("event_type") == "diff_proposed"


@pytest.mark.asyncio
async def test_ingest_event_handles_terminal():
    """ingest_event with terminal event works."""
    with patch("automem.server.main.store_memory", new_callable=AsyncMock) as mock_store, \
         patch("automem.server.main.append_raw_jsonl"):
        mock_store.return_value = None
        from automem.server.main import ingest_event

        result_json = await ingest_event(
            event_type="terminal",
            content='{"cmd": "ls", "exit": 0}',
            source="bash",
        )
        result = json.loads(result_json)
        assert result["status"] == "ingested"
        assert result.get("status") == "ingested" or result.get("event_type") == "terminal"
