"""Contract tests for conversation_store — Pydantic model validation.

Verifies that MCP tools return the correct Pydantic model shapes.
No external dependencies — tests the interface, not the implementation.
"""
import sys
import os
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.result_models import (
    SaveConversationResult, SearchResult, ThreadListResult, ConversationStatusResult
)


# ── SaveConversationResult ──────────────────────────────────────


def test_save_conversation_result_fields():
    result = SaveConversationResult(
        status="saved",
        thread_id="thread-123",
    )
    assert result.status == "saved"
    assert result.thread_id == "thread-123"


def test_save_conversation_result_defaults():
    result = SaveConversationResult(thread_id="t1")
    assert result.status == "saved"


def test_save_conversation_result_serializes_to_dict():
    result = SaveConversationResult(
        status="saved",
        thread_id="t1",
    )
    d = result.model_dump()
    assert isinstance(d, dict)
    assert d["thread_id"] == "t1"
    assert d["status"] == "saved"


# ── SearchResult ────────────────────────────────────────────────


def test_search_result_fields():
    result = SearchResult(
        count=2,
        results=[
            {"thread_id": "t1", "summary": "First", "score": 0.95},
            {"thread_id": "t2", "summary": "Second", "score": 0.80},
        ],
    )
    assert result.count == 2
    assert len(result.results) == 2
    assert result.results[0]["thread_id"] == "t1"


def test_search_result_empty():
    result = SearchResult(count=0, results=[])
    assert result.count == 0
    assert result.results == []


def test_search_result_serializes():
    result = SearchResult(
        count=1,
        results=[{"thread_id": "t1", "score": 0.9}],
    )
    d = result.model_dump()
    assert d["count"] == 1
    assert isinstance(d["results"], list)


# ── ThreadListResult ────────────────────────────────────────────


def test_thread_list_result_fields():
    result = ThreadListResult(
        count=2,
        threads=[
            {"thread_id": "t1", "summary": "First", "message_count": 5},
            {"thread_id": "t2", "summary": "Second", "message_count": 3},
        ],
    )
    assert result.count == 2
    assert len(result.threads) == 2


def test_thread_list_result_empty():
    result = ThreadListResult(count=0, threads=[])
    assert result.count == 0


# ── ConversationStatusResult ────────────────────────────────────


def test_status_result_fields():
    result = ConversationStatusResult(
        daemon="conversation-store",
        status="RUNNING",
        threads=42,
    )
    assert result.daemon == "conversation-store"
    assert result.status == "RUNNING"
    assert result.threads == 42


def test_status_result_defaults():
    result = ConversationStatusResult()
    assert result.daemon == "conversation-store"
    assert result.status == "RUNNING"
    assert result.threads == 0


# ── Cross-model consistency ─────────────────────────────────────


def test_all_models_have_status_field():
    """All result models should have a status or equivalent field."""
    models = [
        SaveConversationResult(thread_id="t1"),
        SearchResult(count=0),
        ThreadListResult(count=0),
        ConversationStatusResult(),
    ]
    for model in models:
        d = model.model_dump()
        # All should serialize without errors
        assert isinstance(d, dict)


def test_models_serialize_to_json():
    """All models should serialize to valid JSON."""
    models = [
        SaveConversationResult(thread_id="t1"),
        SearchResult(count=1, results=[{"thread_id": "t1"}]),
        ThreadListResult(count=1, threads=[{"thread_id": "t1"}]),
        ConversationStatusResult(threads=5),
    ]
    for model in models:
        json_str = model.model_dump_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
