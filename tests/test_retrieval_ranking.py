"""Tests for shared.retrieval._rank_and_fuse — multi-source ranking.

NOTE: _rank_and_fuse is SYNC (def, not async def).
Signature: _rank_and_fuse(results, profile: RetrievalProfile, intent: QueryIntent)
"""

from __future__ import annotations

import pytest

from shared.llm.config import QueryIntent
from shared.retrieval import ContextItem, PROFILES, _rank_and_fuse


def _make_item(content: str, score: float, level: int = 1) -> ContextItem:
    return ContextItem(content=content, score=score, source_name=f"L{level}", source_level=level)


# ── Basic sorting ─────────────────────────────────────────────────


def test_sorts_by_combined_score():
    results = {
        "L1": [
            _make_item("low", 0.3),
            _make_item("high", 0.9),
            _make_item("mid", 0.6),
        ]
    }
    intent = QueryIntent(
        intent_type="code_lookup", entities=[], scope="this_project",
        time_window="all", needs_external=False, needs_ranking=False,
        needs_consolidation=False,
    )
    profile = PROFILES["dev"]
    ranked = _rank_and_fuse(results, profile, intent)

    assert len(ranked) == 3
    assert ranked[0].content == "high"
    assert ranked[2].content == "low"


def test_cross_level_weighting():
    """L2 items with same score rank differently from L1 based on level_weights."""
    results = {
        "L1": [_make_item("working", 0.8, level=1)],
        "L2": [_make_item("episodic", 0.8, level=2)],
    }
    intent = QueryIntent(
        intent_type="code_lookup", entities=[], scope="this_project",
        time_window="all", needs_external=False, needs_ranking=False,
        needs_consolidation=False,
    )
    profile = PROFILES["dev"]
    ranked = _rank_and_fuse(results, profile, intent)

    assert len(ranked) == 2
    # In "dev" profile, L1 weight=1.0, L2=0.9 → L1 should rank higher
    assert ranked[0].content == "working"


def test_empty_results_returns_empty():
    intent = QueryIntent(
        intent_type="code_lookup", entities=[], scope="this_project",
        time_window="all", needs_external=False, needs_ranking=False,
        needs_consolidation=False,
    )
    ranked = _rank_and_fuse({}, PROFILES["default"], intent)
    assert ranked == []


def test_single_item_returns_it():
    results = {"L1": [_make_item("only", 0.5)]}
    intent = QueryIntent(
        intent_type="code_lookup", entities=[], scope="this_project",
        time_window="all", needs_external=False, needs_ranking=False,
        needs_consolidation=False,
    )
    ranked = _rank_and_fuse(results, PROFILES["default"], intent)
    assert len(ranked) == 1
    assert ranked[0].content == "only"
