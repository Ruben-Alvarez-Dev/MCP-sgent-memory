"""Tests for Timeline backends (A: SQLite, B: Hybrid, C: JSONL)."""
import sys
import os
import json
import pytest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.timeline import SQLiteTimeline, JSONLTimeline, create_timeline


# ── Option A: SQLiteTimeline ────────────────────────────────────


@pytest.fixture
def sqlite_tl(tmp_path):
    return SQLiteTimeline(str(tmp_path / "timeline.db"))


def test_sqlite_append(sqlite_tl):
    r = sqlite_tl.append("test", "agent-1", "Hello world")
    assert r["status"] == "appended"
    assert "id" in r


def test_sqlite_query_by_agent(sqlite_tl):
    sqlite_tl.append("test", "agent-1", "Agent 1 event")
    sqlite_tl.append("test", "agent-2", "Agent 2 event")
    results = sqlite_tl.query(agent_id="agent-1")
    assert len(results) == 1
    assert results[0]["agent_id"] == "agent-1"


def test_sqlite_query_by_type(sqlite_tl):
    sqlite_tl.append("terminal", "agent-1", "Terminal event")
    sqlite_tl.append("git", "agent-1", "Git event")
    results = sqlite_tl.query(event_type="terminal")
    assert len(results) == 1
    assert results[0]["event_type"] == "terminal"


def test_sqlite_query_limit(sqlite_tl):
    for i in range(10):
        sqlite_tl.append("test", "agent-1", f"Event {i}")
    results = sqlite_tl.query(limit=3)
    assert len(results) == 3


def test_sqlite_search(sqlite_tl):
    sqlite_tl.append("test", "agent-1", "SQLite FTS5 implementation")
    sqlite_tl.append("test", "agent-1", "Python decorators")
    results = sqlite_tl.search("FTS5")
    assert len(results) == 1
    assert "FTS5" in results[0]["content"]


def test_sqlite_search_multi_word(sqlite_tl):
    sqlite_tl.append("test", "agent-1", "How to implement SQLite FTS5?")
    results = sqlite_tl.search("SQLite FTS5")
    assert len(results) >= 1


def test_sqlite_count(sqlite_tl):
    assert sqlite_tl.count() == 0
    sqlite_tl.append("test", "agent-1", "Event 1")
    assert sqlite_tl.count() == 1
    sqlite_tl.append("test", "agent-1", "Event 2")
    assert sqlite_tl.count() == 2


def test_sqlite_metadata(sqlite_tl):
    sqlite_tl.append("test", "agent-1", "Event", metadata={"key": "value"})
    results = sqlite_tl.query()
    meta = json.loads(results[0]["metadata"])
    assert meta["key"] == "value"


# ── Option C: JSONLTimeline ─────────────────────────────────────


@pytest.fixture
def jsonl_tl(tmp_path):
    return JSONLTimeline(str(tmp_path / "timeline.jsonl"))


def test_jsonl_append(jsonl_tl):
    r = jsonl_tl.append("test", "agent-1", "Hello JSONL")
    assert r["status"] == "appended"


def test_jsonl_query(jsonl_tl):
    jsonl_tl.append("test", "agent-1", "Event 1")
    jsonl_tl.append("test", "agent-2", "Event 2")
    results = jsonl_tl.query(agent_id="agent-1")
    assert len(results) == 1


def test_jsonl_search(jsonl_tl):
    jsonl_tl.append("test", "agent-1", "SQLite implementation")
    jsonl_tl.append("test", "agent-1", "Python code")
    results = jsonl_tl.search("SQLite")
    assert len(results) == 1


def test_jsonl_count(jsonl_tl):
    assert jsonl_tl.count() == 0
    jsonl_tl.append("test", "agent-1", "Event")
    assert jsonl_tl.count() == 1


# ── Factory ─────────────────────────────────────────────────────


def test_factory_sqlite(tmp_path):
    tl = create_timeline("sqlite", db_path=str(tmp_path / "factory.db"))
    assert isinstance(tl, SQLiteTimeline)
    tl.append("test", "agent-1", "Factory test")
    assert tl.count() == 1


def test_factory_jsonl(tmp_path):
    tl = create_timeline("jsonl", jsonl_path=str(tmp_path / "factory.jsonl"))
    assert isinstance(tl, JSONLTimeline)
    tl.append("test", "agent-1", "Factory test")
    assert tl.count() == 1


def test_factory_invalid():
    with pytest.raises(ValueError, match="Unknown timeline backend"):
        create_timeline("invalid")
