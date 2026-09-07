"""Determinism + integrity tests for the eval-40 fixture corpus.

Property under test: same working tree -> same fixture, no matter how many
times build_fixture_db runs on the same path (DROP/recreate, never append).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fixture_corpus import COLLECTION, build_fixture_db, build_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERIES_YAML = REPO_ROOT / "openspec/changes/M0-baseline/evidence/eval-40.yaml"
JUDGMENTS_YAML = REPO_ROOT / "tests/eval/judgments.yaml"


async def test_fixture_determinista(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    m1 = await build_fixture_db(db)
    m2 = await build_fixture_db(db)  # same path twice -> DROP + rebuild
    assert m1 == m2, "fixture manifest must be identical across rebuilds"
    assert len(m1) >= 34
    assert list(m1) == [f"eval-{n}" for n in range(1, len(m1) + 1)]
    # Chunks are the size the eval contract promises.
    for doc_id, doc in m1.items():
        assert 180 <= len(doc["content"]) <= 700, (doc_id, len(doc["content"]))
        assert doc["layer"] in (1, 2, 3, 4)
    # Layers actually vary (routing depends on them).
    layers = {doc["layer"] for doc in m1.values()}
    assert layers == {1, 2, 3, 4}


async def test_fixture_db_rebuilt_not_appended(tmp_path: Path) -> None:
    import sqlite3

    from shared.memory_db import MemoryDB

    db = str(tmp_path / "memory.db")
    manifest = await build_fixture_db(db)
    await build_fixture_db(db)  # second build must not duplicate rows
    conn = sqlite3.connect(db)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM points WHERE collection=?", (COLLECTION,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == len(manifest)
    mdb = MemoryDB(db, COLLECTION, 1024)
    try:
        rows = await mdb.scroll(
            filter={"must": [{"key": "agent_scope", "match": {"any": ["shared"]}}]},
            limit=100,
        )
        assert len(rows) == len(manifest)
    finally:
        await mdb.close()


def test_judgments_align_with_frozen_queries_and_manifest() -> None:
    manifest = build_manifest()
    queries = yaml.safe_load(QUERIES_YAML.read_text())["queries"]
    entries = yaml.safe_load(JUDGMENTS_YAML.read_text())["entries"]
    assert len(entries) == len(queries) == 38
    for q, e in zip(queries, entries, strict=True):
        assert e["q"] == q["q"], f"judgment query drift: {e['q']!r} != {q['q']!r}"
        assert e["lang"] == q["lang"] and e["intent"] == q["intent"]
        assert 1 <= len(e["relevant"]) <= 4
        for doc_id in e["relevant"]:
            assert doc_id in manifest, f"judgment references unknown doc {doc_id}"
