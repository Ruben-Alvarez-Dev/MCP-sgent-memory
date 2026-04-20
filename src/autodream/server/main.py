from __future__ import annotations
import json
from typing import List, Dict, Any

# In-memory storage for consolidated memory events.
# In production this connects to the shared MEMORY_DB from automem.
from automem.server.main import MEMORY_DB

def _mine_diff_patterns(diffs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Mines patterns from a list of diff events. Implements SPEC-6.1.
    """
    patterns = []
    
    # Simple anti-pattern: find common errors in rejected diffs
    rejected_python_diffs = [
        d for d in diffs 
        if d.get("metadata", {}).get("event_type") == "diff_rejected" and 
           d.get("metadata", {}).get("language") == "python"
    ]

    # Heuristic: rejected diffs containing 'import' suggest dependency issues.
    if any("import" in json.loads(d.get("content", '""')) for d in rejected_python_diffs):
        patterns.append({
            "type": "anti_pattern",
            "language": "python",
            "pattern": "Missing imports are a common cause of failure.",
            "evidence_count": len(rejected_python_diffs),
            "source": "diff_mining"
        })
        
    return patterns

async def consolidate(*args, **kwargs) -> str:
    """
    Runs consolidation, including mining diff patterns from L1 memory.
    """
    # 1. Get L1 diff events from automem's memory
    l1_diffs = [
        item for item in MEMORY_DB
        if item.get("layer") == 1 and item.get("type") == "STEP"
    ]
    
    # 2. Mine patterns
    new_patterns = _mine_diff_patterns(l1_diffs)
    
    # 3. Store new patterns in L3 (for simplicity, we add them back to the same DB)
    for pattern in new_patterns:
        mem_item = {
            "content": json.dumps(pattern),
            "layer": 3, # Semantic Memory
            "type": "PATTERN",
            "metadata": {"source": "autodream"}
        }
        MEMORY_DB.append(mem_item)
        
    return json.dumps({
        "status": "consolidation_complete",
        "new_patterns_found": len(new_patterns)
    })
