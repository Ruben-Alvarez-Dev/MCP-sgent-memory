"""Tests for shared.llm.config.rank_by_relevance — LLM ranking."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from shared.llm.config import rank_by_relevance


def _items(n):
    return [{"content": f"item {i}", "idx": i} for i in range(n)]


def test_rank_uses_small_llm():
    items = _items(15)
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.ask.return_value = '{"ranked_indices": [2, 0, 1]}'

    with patch("shared.llm.config.get_small_llm", return_value=mock_llm):
        ranked = rank_by_relevance("query", items, top_k=3)
    assert len(ranked) <= 3


def test_fallback_when_llm_unavailable():
    items = _items(12)
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False

    with patch("shared.llm.config.get_small_llm", return_value=mock_llm):
        ranked = rank_by_relevance("query", items, top_k=5)
    # Returns original items (all of them since no LLM to filter)
    assert len(ranked) == 12


def test_malformed_response_falls_back():
    items = _items(15)
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.ask.return_value = "garbage response"

    with patch("shared.llm.config.get_small_llm", return_value=mock_llm):
        ranked = rank_by_relevance("query", items, top_k=5)
    assert len(ranked) > 0


def test_no_ranking_below_top_k():
    items = _items(3)
    with patch("shared.llm.config.get_small_llm") as m:
        ranked = rank_by_relevance("query", items, top_k=10)
    m.assert_not_called()
    assert ranked == items


def test_llm_exception_falls_back():
    items = _items(15)
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.ask.side_effect = RuntimeError("crash")

    with patch("shared.llm.config.get_small_llm", return_value=mock_llm):
        ranked = rank_by_relevance("query", items, top_k=5)
    assert len(ranked) > 0
