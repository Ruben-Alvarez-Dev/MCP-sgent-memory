import sys
import pytest
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.llm.config import rank_by_relevance
from shared.retrieval import ContextItem

# --- Unit Tests (SPEC-4.1: LLM Ranking Robust to JSON) ---

@pytest.mark.asyncio
async def test_rank_reorders_by_relevance_json():
    """AC-4.1.1: rank_by_relevance now requires structured JSON and reorders correctly."""
    items = [
        ContextItem(content="About dogs", source_name="doc1", source_level=1, score=0.8),
        ContextItem(content="About cats", source_name="doc2", source_level=1, score=0.9),
        ContextItem(content="A story about a cat chasing a dog", source_name="doc3", source_level=1, score=0.7),
    ]
    
    async def mock_llm_call(prompt: str):
        # Simulate an LLM structured output
        return '{"ranked_indices": [1, 2, 0]}'

    ranked = await rank_by_relevance("Tell me about felines", items, mock_llm_call)
    
    assert len(ranked) == 3
    assert ranked[0].content == "About cats"
    assert ranked[1].content == "A story about a cat chasing a dog"
    assert ranked[2].content == "About dogs"

@pytest.mark.asyncio
async def test_fallback_when_llm_fails_json():
    """AC-4.1.2: If LLM fails to return valid JSON, fall back to the original list without crashing."""
    items = [
        ContextItem(content="A", source_name="doc1", source_level=1, score=0.9),
        ContextItem(content="B", source_name="doc2", source_level=1, score=0.8),
    ]
    
    async def mock_llm_fail(prompt: str):
        raise ValueError("LLM is down")

    ranked = await rank_by_relevance("query", items, mock_llm_fail)
    
    assert len(ranked) == 2
    assert ranked[0].content == "A" # Should maintain original order

@pytest.mark.asyncio
async def test_handles_malformed_llm_response_json():
    """AC-4.1.3: Handles malformed non-JSON responses from the LLM."""
    items = [
        ContextItem(content="A", source_name="doc1", source_level=1, score=0.9),
        ContextItem(content="B", source_name="doc2", source_level=1, score=0.8),
        ContextItem(content="C", source_name="doc3", source_level=1, score=0.7),
    ]
    
    async def mock_llm_malformed(prompt: str):
        # LLM ignored the JSON instruction and hallucinated text
        return "I think the order is 2, 0, 1"

    ranked = await rank_by_relevance("query", items, mock_llm_malformed)
    
    # Should fall back to the original order cleanly
    assert len(ranked) == 3
    assert ranked[0].content == "A"
    assert ranked[1].content == "B"
    assert ranked[2].content == "C"
