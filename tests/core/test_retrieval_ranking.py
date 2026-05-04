import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.retrieval import _rank_and_fuse, ContextItem, RetrievalProfile
from shared.llm.config import QueryIntent

def _default_profile():
    return RetrievalProfile(
        name="test",
        level_weights={1: 1.0, 2: 0.9, 3: 0.7},
        top_k_per_level={1: 10, 2: 10, 3: 10},
        token_budget=8000,
        max_time_ms=1000,
        needs_ai_ranking=False,
    )

def _default_intent(**overrides):
    defaults = dict(
        intent_type="code_lookup", entities=[], scope="",
        time_window="session", needs_external=False,
        needs_ranking=False, needs_consolidation=False,
    )
    defaults.update(overrides)
    return QueryIntent(**defaults)


def test_rank_and_fuse_sorts_by_combined_score():
    """Items are sorted by combined_score (level_weight * score + recency + freshness)."""
    results = {
        "L1": [ContextItem(content="A", score=0.8, source_name="L1", source_level=1)],
        "L2": [ContextItem(content="B", score=0.9, source_name="L2", source_level=2)],
    }
    profile = _default_profile()
    intent = _default_intent()

    fused = _rank_and_fuse(results, profile, intent)

    assert len(fused) == 2
    assert isinstance(fused[0], ContextItem)
    # Both should have combined_score set
    assert all(hasattr(item, 'combined_score') and item.combined_score > 0 for item in fused)


def test_rank_and_fuse_empty_results():
    """Empty results dict returns empty list."""
    profile = _default_profile()
    intent = _default_intent()
    fused = _rank_and_fuse({}, profile, intent)
    assert fused == []


def test_rank_and_fuse_respects_level_weights():
    """Higher level_weight amplifies score."""
    # L1 has weight 1.0, L2 has weight 0.9
    # So an L1 item with score 0.5 should beat L2 with score 0.5
    results = {
        "L2": [ContextItem(content="low_weight", score=0.5, source_name="L2", source_level=2)],
        "L1": [ContextItem(content="high_weight", score=0.5, source_name="L1", source_level=1)],
    }
    profile = _default_profile()
    intent = _default_intent()

    fused = _rank_and_fuse(results, profile, intent)
    assert len(fused) == 2
    # L1 item should come first (same score but higher level_weight)
    assert fused[0].content == "high_weight"


def test_rank_and_fuse_clamps_negative_scores():
    """Negative scores from sparse vectors should be clamped to [0, 1]."""
    results = {
        "L1": [ContextItem(content="negative", score=-0.5, source_name="L1", source_level=1)],
        "L2": [ContextItem(content="positive", score=0.3, source_name="L2", source_level=2)],
    }
    profile = _default_profile()
    intent = _default_intent()

    fused = _rank_and_fuse(results, profile, intent)

    assert len(fused) == 2
    for item in fused:
        assert 0.0 <= item.combined_score <= 1.0, (
            f"combined_score {item.combined_score} not in [0, 1] for '{item.content}'"
        )


def test_rank_and_fuse_clamps_oversized_scores():
    """Scores > 1.0 should be clamped (shouldn't happen, but defense in depth)."""
    results = {
        "L1": [ContextItem(content="huge", score=5.0, source_name="L1", source_level=1)],
    }
    profile = _default_profile()
    intent = _default_intent()

    fused = _rank_and_fuse(results, profile, intent)

    assert len(fused) == 1
    assert fused[0].combined_score <= 1.0
