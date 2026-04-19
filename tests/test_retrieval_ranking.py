import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.retrieval import _rank_and_fuse
from shared.llm.config import ContextItem, QueryIntent

@pytest.mark.asyncio
async def test_rank_and_fuse_sorts_by_score_by_default():
    """Verifies baseline sorting by score when no LLM ranking is needed."""
    results = {
        "L1": [ContextItem(content="A", score=0.8, source_name="L1", source_level=1)],
        "L2": [ContextItem(content="B", score=0.9, source_name="L2", source_level=2)],
    }
    intent = QueryIntent(intent_type="code_lookup", entities=[], scope="", time_window="", needs_external=False, needs_ranking=False, needs_consolidation=False)
    
    fused = await _rank_and_fuse(results, intent, "query")
    
    assert len(fused) == 2
    assert fused[0].content == "B" # Highest score first

@pytest.mark.asyncio
async def test_rank_and_fuse_calls_llm_ranker_when_needed():
    """Verifies that LLM ranking is invoked when intent.needs_ranking is True."""
    results = {
        "L1": [
            ContextItem(content="Low score, but relevant", score=0.1, source_name="L1", source_level=1),
            ContextItem(content="High score, irrelevant", score=0.9, source_name="L1", source_level=1),
        ]
    }
    intent = QueryIntent(intent_type="code_lookup", entities=[], scope="", time_window="", needs_external=False, needs_ranking=True, needs_consolidation=False)
    
    async def mock_llm_for_rank(p: str): return '{"ranked_indices": [1, 0]}'
    fused = await _rank_and_fuse(results, intent, "query", mock_llm_fn=mock_llm_for_rank)

    assert len(fused) == 2
    assert fused[0].content == "Low score, but relevant"


