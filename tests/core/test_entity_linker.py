"""Tests for catalog-validated entity linker + candidate quarantine (repair plan P2)."""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest

from shared.entity_registry import EntityRegistry
from shared.entity_timeline import EntityTimeline
from shared.relation_manager import RelationManager
from shared.entity_migration import migrate_raw_events, _is_sane_candidate


# ── Sanity filter ────────────────────────────────────────────────


@pytest.mark.parametrize("junk", [
    "A", "--", "---", "https", "http", "www.example",
    "/Users/ruben/.hermes/hermes-agent",
    ".worktrees/agent-memory_1776993728",
    "./relative/path", "~/home/path", "../up",
    "12", "1.2.3",
])
def test_sanity_rejects_junk(junk):
    assert _is_sane_candidate(junk) is False


@pytest.mark.parametrize("good", [
    "MCP-agent-memory", "pi-coding-agent", "nexus", "BrowserOS-OPENCODE",
])
def test_sanity_accepts_real_names(good):
    assert _is_sane_candidate(good) is True


# ── Catalog-validated linking + quarantine ───────────────────────


@pytest.fixture
def stack(tmp_path):
    db = str(tmp_path / "entity_timeline.db")
    registry = EntityRegistry(db)
    timeline = EntityTimeline(db)
    relations = RelationManager(db)
    return db, registry, timeline, relations


def _write_events(tmp_path, contents):
    p = tmp_path / "raw_events.jsonl"
    lines = []
    for i, content in enumerate(contents):
        lines.append(json.dumps({
            "event_id": f"ev-{i}", "actor_id": "ruben",
            "type": "system", "timestamp": "2026-06-07T00:00:00+00:00",
            "attributes": {"content": content},
        }))
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_known_entity_is_linked_not_recreated(stack, tmp_path):
    db, registry, timeline, relations = stack
    known = registry.register(name="MCP-agent-memory", kind="project")
    jsonl = _write_events(tmp_path, ["working on repo: MCP-agent-memory today"])

    before = registry.count()
    migrate_raw_events(jsonl, registry, timeline, relations, dry_run=False)

    # Linked to the existing entity: a reference event lands on its timeline
    events = timeline.query(known.entity_id, limit=10)
    assert any(e["event_type"] == "reference" for e in events)
    # No project entity was created for the match itself (only the actor)
    assert registry.get_by_name("MCP-agent-memory").entity_id == known.entity_id
    assert registry.count() == before + 1  # only the "ruben" actor entity


def test_case_insensitive_match_links(stack, tmp_path):
    db, registry, timeline, relations = stack
    known = registry.register(name="MCP-agent-memory", kind="project")
    jsonl = _write_events(tmp_path, ["fixing repo: mcp-agent-memory now"])

    migrate_raw_events(jsonl, registry, timeline, relations, dry_run=False)

    events = timeline.query(known.entity_id, limit=10)
    assert any(e["event_type"] == "reference" for e in events)
    assert registry.list_candidates() == []


def test_unknown_candidate_is_quarantined(stack, tmp_path):
    db, registry, timeline, relations = stack
    jsonl = _write_events(tmp_path, [
        "check project: totally-new-thing here",
        "again project: totally-new-thing later",
    ])

    before = registry.count()
    migrate_raw_events(jsonl, registry, timeline, relations, dry_run=False)

    assert registry.get_by_name("totally-new-thing") is None
    assert registry.count() == before + 1  # only the actor entity
    cands = registry.list_candidates()
    assert len(cands) == 1
    assert cands[0]["name"] == "totally-new-thing"
    assert cands[0]["occurrences"] == 2
    assert cands[0]["status"] == "pending"
    assert "totally-new-thing" in cands[0]["sample_content"]


def test_junk_is_neither_linked_nor_quarantined(stack, tmp_path):
    db, registry, timeline, relations = stack
    jsonl = _write_events(tmp_path, [
        "see project: https://example.com and repo: /Users/x/y and repo: A",
    ])

    migrate_raw_events(jsonl, registry, timeline, relations, dry_run=False)

    assert registry.get_by_name("https") is None
    assert registry.get_by_name("A") is None
    assert registry.list_candidates() == []
