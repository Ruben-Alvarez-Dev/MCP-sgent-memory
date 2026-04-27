"""Smoke tests for conversation_store — SQLite + FTS5 + Qdrant.

Tests the basic flow: save → get → search → list → status.
No mocks — uses real SQLite and real Qdrant (if available).
"""
import sys
import os
import json
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.conversation_db import (
    save_thread, get_thread, search_fts, list_threads, thread_count, set_db_path
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Each test gets a fresh SQLite database."""
    db_path = str(tmp_path / "test_conversations.db")
    set_db_path(db_path)
    yield
    # Cleanup handled by tmp_path fixture


# ── Save ────────────────────────────────────────────────────────


def test_save_creates_thread():
    msgs = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    result = save_thread("t1", msgs, summary="Greeting")
    assert result["status"] == "saved"
    assert result["thread_id"] == "t1"
    assert result["message_count"] == 2


def test_save_empty_messages():
    result = save_thread("t-empty", [], summary="Empty thread")
    assert result["status"] == "saved"
    assert result["message_count"] == 0


def test_save_overwrites_existing():
    msgs1 = [{"role": "user", "content": "First"}]
    msgs2 = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Updated"},
    ]
    save_thread("t-overwrite", msgs1, summary="v1")
    result = save_thread("t-overwrite", msgs2, summary="v2")
    assert result["message_count"] == 2

    thread = get_thread("t-overwrite")
    assert thread["summary"] == "v2"
    assert len(thread["messages"]) == 2


# ── Get ─────────────────────────────────────────────────────────


def test_get_returns_full_messages():
    msgs = [
        {"role": "user", "content": "Question about SQLite"},
        {"role": "assistant", "content": "SQLite is a C library..."},
    ]
    save_thread("t-get", msgs, summary="SQLite discussion")

    thread = get_thread("t-get")
    assert thread is not None
    assert thread["thread_id"] == "t-get"
    assert thread["summary"] == "SQLite discussion"
    assert len(thread["messages"]) == 2
    assert thread["messages"][0]["role"] == "user"
    assert thread["messages"][0]["content"] == "Question about SQLite"
    assert thread["messages"][1]["role"] == "assistant"


def test_get_preserves_message_order():
    msgs = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "msg2"},
        {"role": "user", "content": "msg3"},
    ]
    save_thread("t-order", msgs)
    thread = get_thread("t-order")
    assert thread["messages"][0]["content"] == "msg1"
    assert thread["messages"][1]["content"] == "msg2"
    assert thread["messages"][2]["content"] == "msg3"


def test_get_nonexistent_returns_none():
    result = get_thread("does-not-exist")
    assert result is None


# ── FTS Search ──────────────────────────────────────────────────


def test_fts_finds_by_content():
    msgs = [
        {"role": "user", "content": "How to implement SQLite FTS5?"},
        {"role": "assistant", "content": "Create a virtual table with fts5..."},
    ]
    save_thread("t-fts", msgs)

    results = search_fts("FTS5")
    assert len(results) >= 1
    assert results[0]["thread_id"] == "t-fts"


def test_fts_multi_word_or():
    msgs = [
        {"role": "user", "content": "Tell me about Python decorators"},
        {"role": "assistant", "content": "Decorators are functions that modify..."},
    ]
    save_thread("t-multi", msgs)

    # "Python decorators" should match (OR semantics)
    results = search_fts("Python decorators")
    assert len(results) >= 1


def test_fts_no_match_returns_empty():
    save_thread("t-nomatch", [{"role": "user", "content": "Hello world"}])
    results = search_fts("xyznonexistent")
    assert results == []


def test_fts_empty_query_returns_empty():
    results = search_fts("")
    assert results == []


# ── List ────────────────────────────────────────────────────────


def test_list_returns_recent_threads():
    save_thread("t-old", [{"role": "user", "content": "old"}], summary="Old")
    save_thread("t-new", [{"role": "user", "content": "new"}], summary="New")

    threads = list_threads(limit=10)
    assert len(threads) == 2
    # Most recent first
    assert threads[0]["thread_id"] == "t-new"
    assert threads[1]["thread_id"] == "t-old"


def test_list_respects_limit():
    for i in range(5):
        save_thread(f"t-{i}", [{"role": "user", "content": f"msg {i}"}])

    threads = list_threads(limit=3)
    assert len(threads) == 3


def test_list_empty_returns_empty():
    threads = list_threads()
    assert threads == []


# ── Count ───────────────────────────────────────────────────────


def test_count_reflects_saves():
    assert thread_count() == 0
    save_thread("t-count-1", [{"role": "user", "content": "a"}])
    assert thread_count() == 1
    save_thread("t-count-2", [{"role": "user", "content": "b"}])
    assert thread_count() == 2


def test_count_does_not_double_on_overwrite():
    save_thread("t-count-over", [{"role": "user", "content": "v1"}])
    save_thread("t-count-over", [{"role": "user", "content": "v2"}])
    assert thread_count() == 1


# ── Edge Cases ──────────────────────────────────────────────────


def test_unicode_content():
    msgs = [{"role": "user", "content": "¿Cómo estás? 日本語テスト 🚀"}]
    save_thread("t-unicode", msgs)
    thread = get_thread("t-unicode")
    assert "日本語" in thread["messages"][0]["content"]
    assert "🚀" in thread["messages"][0]["content"]


def test_large_content():
    large_text = "x" * 50000
    msgs = [{"role": "user", "content": large_text}]
    save_thread("t-large", msgs)
    thread = get_thread("t-large")
    assert len(thread["messages"][0]["content"]) == 50000


def test_special_chars_in_thread_id():
    save_thread("project/session-abc.123", [{"role": "user", "content": "test"}])
    thread = get_thread("project/session-abc.123")
    assert thread is not None
    assert thread["thread_id"] == "project/session-abc.123"


# ── Agent Scope ─────────────────────────────────────────────────


def test_save_with_agent_scope():
    msgs = [{"role": "user", "content": "Private note"}]
    result = save_thread("t-scope", msgs, summary="Private", agent_scope="director-1")
    assert result["agent_scope"] == "director-1"

    thread = get_thread("t-scope")
    assert thread["agent_scope"] == "director-1"


def test_save_default_scope_is_shared():
    msgs = [{"role": "user", "content": "Public note"}]
    save_thread("t-shared", msgs)
    thread = get_thread("t-shared")
    assert thread["agent_scope"] == "shared"


def test_list_filters_by_scope():
    save_thread("t-shared-1", [{"role": "user", "content": "shared"}], agent_scope="shared")
    save_thread("t-dir-1", [{"role": "user", "content": "dir1"}], agent_scope="director-1")
    save_thread("t-dir-2", [{"role": "user", "content": "dir2"}], agent_scope="director-2")

    # Director-1 sees own + shared
    threads = list_threads(agent_scope="director-1")
    ids = {t["thread_id"] for t in threads}
    assert "t-shared-1" in ids
    assert "t-dir-1" in ids
    assert "t-dir-2" not in ids

    # Director-2 sees own + shared
    threads2 = list_threads(agent_scope="director-2")
    ids2 = {t["thread_id"] for t in threads2}
    assert "t-shared-1" in ids2
    assert "t-dir-2" in ids2
    assert "t-dir-1" not in ids2

    # No filter = all
    all_threads = list_threads()
    assert len(all_threads) == 3


def test_fts_filters_by_scope():
    save_thread("t-fts-shared", [{"role": "user", "content": "SQLite FTS5 tutorial"}], agent_scope="shared")
    save_thread("t-fts-dir", [{"role": "user", "content": "SQLite FTS5 advanced"}], agent_scope="director-1")
    save_thread("t-fts-eng", [{"role": "user", "content": "SQLite FTS5 basics"}], agent_scope="engineer-1")

    # Director-1 sees own + shared
    results = search_fts("FTS5", agent_scope="director-1")
    ids = {r["thread_id"] for r in results}
    assert "t-fts-shared" in ids
    assert "t-fts-dir" in ids
    assert "t-fts-eng" not in ids

    # No filter = all
    all_results = search_fts("FTS5")
    assert len(all_results) == 3
