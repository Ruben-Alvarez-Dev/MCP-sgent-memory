"""Tests for shared.llm.config.rank_by_relevance — REAL integration, NO MOCKS."""
import pytest
from shared.llm.config import rank_by_relevance

def test_rank_by_relevance_real():
    items = [{"content": f"item {i}", "idx": i} for i in range(15)]
    # This will actually attempt to hit the local LLM if available
    ranked = rank_by_relevance("query", items, top_k=3)
    assert len(ranked) > 0
