import sys
import pytest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodream.server import main as autodream_main
from automem.server import main as automem_main

@pytest.mark.asyncio
async def test_consolidate_mines_diff_patterns():
    """AC-6.1.1, 6.1.2, 6.1.3: Autodream detecta diffs y genera patrones."""
    
    # Setup: Clear and populate automem DB with a rejected python diff
    automem_main.MEMORY_DB.clear()
    rejected_diff_event = {
        "content": json.dumps("- import os\\n+ import os, sys"),
        "layer": 1,
        "type": "STEP",
        "metadata": {
            "event_type": "diff_rejected",
            "language": "python"
        }
    }
    automem_main.MEMORY_DB.append(rejected_diff_event)
    
    # Execute
    result_json = await autodream_main.consolidate()
    result = json.loads(result_json)
    
    # Verify
    assert result["status"] == "consolidation_complete"
    assert result["new_patterns_found"] == 1
    
    # Check that the new pattern was added to L3
    l3_patterns = [item for item in automem_main.MEMORY_DB if item.get("layer") == 3]
    assert len(l3_patterns) == 1
    
    pattern_content = json.loads(l3_patterns[0]["content"])
    assert pattern_content["type"] == "anti_pattern"
    assert "Missing imports" in pattern_content["pattern"]

