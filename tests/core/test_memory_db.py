"""M2-storage core tests — memory_db engine enforcement + scope jail.

Traceability: STO-01, STO-02, STO-05, ISO-05, ISO-11, ISO-12 (specs delta
openspec/changes/M2-storage). Adversarial counterparts live in
tests/adversarial/ (A3, A10, A14, A15 shapes).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from shared.memory_db import MemoryDB, ScopeRequiredError
from shared.scope import ScopeError, scope_jail_path


@pytest.fixture()
def db(tmp_path):
    d = MemoryDB(str(tmp_path / "memory.db"), collection="L3_facts", embedding_dim=8)
    d._ensure_schema()
    yield d
    d._conn.close()


def _vec(seed: float, dim: int = 8) -> list[float]:
    v = [seed] * dim
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


# ── M9: vector column dropped, FTS5-only retrieval ───────────────────

@pytest.mark.unit
async def test_vector_column_dropped_from_schema(db):
    cols = {r[1] for r in db._conn.execute("PRAGMA table_info(points)").fetchall()}
    assert "vector" not in cols
    assert "payload" in cols and "agent_scope" in cols


@pytest.mark.unit
async def test_fts5_search_deterministic(db):
    await db.upsert("m1", {"content": "stable content", "user_id": "u1"})
    filt = {"must": [{"key": "user_id", "match": {"value": "u1"}}]}
    hits = await db.search("stable content", limit=5, filter=filt)
    assert len(hits) == 1
    assert hits[0]["score_source"] == "fts5"
    # deterministic: same query -> same score on repeated searches
    again = await db.search("stable content", limit=5, filter=filt)
    assert again[0]["score"] == hits[0]["score"]


@pytest.mark.unit
async def test_migration_drops_vector_column(tmp_path):
    """Pre-M9 database (with vector column + data) migrates at boot."""
    import sqlite3
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE points(
             id TEXT NOT NULL, collection TEXT NOT NULL, vector BLOB,
             payload TEXT NOT NULL, agent_scope TEXT NOT NULL DEFAULT 'shared',
             user_id TEXT, layer INTEGER, sparse_json TEXT, created_at TEXT NOT NULL,
             PRIMARY KEY(collection, id))"""
    )
    conn.execute(
        "INSERT INTO points(id, collection, vector, payload, created_at)"
        " VALUES('legacy1','c1',NULL,'{\"content\": \"kept\"}','2026-01-01')"
    )
    conn.commit()
    conn.close()

    db = MemoryDB(db_path, "c1")
    cols = {r[1] for r in db._conn.execute("PRAGMA table_info(points)").fetchall()}
    assert "vector" not in cols
    row = db._conn.execute("SELECT payload FROM points WHERE id='legacy1'").fetchone()
    assert json.loads(row["payload"])["content"] == "kept"  # data survives


# ── ISO-05: engine-level filter (nothing foreign fetched) ────────────

@pytest.mark.unit
async def test_engine_filter_excludes_foreign_rows(db, monkeypatch):
    await db.upsert("u1-row", {"content": "mine", "user_id": "u1"})
    await db.upsert("u2-row", {"content": "mine", "user_id": "u2"})  # identical content

    seen: list = []
    orig = MemoryDB._search_fts_sync

    def spy(self, fts_query, limit, filter_):
        where, params = self._translate_filter(filter_)
        seen.append((where, params))
        return orig(self, fts_query, limit, filter_)

    monkeypatch.setattr(MemoryDB, "_search_fts_sync", spy)
    hits = await db.search("mine", limit=10,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    # the caller's filter reached the ENGINE (SQL WHERE), not a post-filter
    assert seen and all("user_id" in where for where, _ in seen)
    assert [h["id"] for h in hits] == ["u1-row"]  # u2 row NEVER returned
    assert all(h["payload"]["user_id"] == "u1" for h in hits)


@pytest.mark.unit
async def test_high_similarity_foreign_row_not_returned(db):
    await db.upsert("foreign", {"content": "shared fact text", "user_id": "u2"})
    await db.upsert("mine", {"content": "my fact", "user_id": "u1"})
    # query matching the FOREIGN content: engine filter must still exclude it
    # (OR semantics: u1's own row may also match on "fact" — that's correct;
    # the security property is that u2's row NEVER leaks to u1)
    hits = await db.search("shared fact text", limit=10,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert "foreign" not in [h["id"] for h in hits]
    assert all(h["payload"]["user_id"] == "u1" for h in hits)
    hits = await db.search("my fact", limit=10,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert [h["id"] for h in hits] == ["mine"]


# ── ISO-11 / fail-closed reads ───────────────────────────────────────

@pytest.mark.unit
async def test_search_without_filter_fails_closed(db):
    with pytest.raises(ScopeRequiredError):
        await db.search("x")


@pytest.mark.unit
async def test_scroll_without_filter_fails_closed(db):
    with pytest.raises(ScopeRequiredError):
        await db.scroll(None)


@pytest.mark.unit
async def test_filter_key_validation(db):
    bad_keys = ["user_id) --", "x'; DROP TABLE points; --", "User-Id", ""]
    for key in bad_keys:
        with pytest.raises(ValueError):
            await db.search("x", filter={"must": [{"key": key, "match": {"value": "u1"}}]})


@pytest.mark.unit
async def test_filter_none_value_rejected(db):
    with pytest.raises(ValueError):
        await db.search("x", filter={"must": [{"key": "user_id", "match": {"value": None}}]})


@pytest.mark.unit
async def test_injection_value_binds_literally(db):
    await db.upsert("a", {"content": "x", "user_id": "u1"})
    hits = await db.search("x", limit=10,
                           filter={"must": [{"key": "user_id", "match": {"value": "' OR 1=1 --"}}]})
    assert hits == []  # literal match, no injection


# ── ISO-12: default scope ────────────────────────────────────────────

@pytest.mark.unit
async def test_default_scope_is_shared(db):
    await db.upsert("anon", {"content": "no scope given"})
    hits = await db.scroll({"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert hits and hits[0]["agent_scope"] == "shared"


# ── STO-01: corrupt payload resilience + counts ──────────────────────

@pytest.mark.unit
async def test_corrupt_payload_does_not_break_search(db):
    await db.upsert("good", {"content": "fine", "user_id": "u1"})
    db._conn.execute(
        "INSERT INTO points(id, collection, payload, created_at) VALUES('bad','L3_facts','{not json','2026-01-01')"
    )
    db._conn.commit()
    hits = await db.search("fine", limit=5,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert [h["id"] for h in hits] == ["good"]
    assert await db.count() == 2


@pytest.mark.unit
async def test_upsert_batch_and_delete_roundtrip(db):
    await db.upsert_batch([
        {"id": "b1", "payload": {"content": "one", "user_id": "u1"}},
        {"id": "b2", "payload": {"content": "two", "user_id": "u1"}},
    ])
    assert await db.count() == 2
    assert await db.delete("b1") is True
    assert await db.delete("b1") is False
    assert await db.count() == 1


# ── STO-02: conversations unified into memory.db ─────────────────────

@pytest.mark.unit
def test_conversations_unified_file(tmp_path, monkeypatch):
    import shared.conversation_db as cdb

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cdb, "_db_path", "")  # force re-resolve
    path = cdb._get_db_path()
    assert path.endswith("memory.db")
    # both schemas coexist in the same file
    cdb._init_db(path)
    conn = sqlite3.connect(path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "threads" in names  # conversations schema alive inside memory.db
    conn.close()


# ── STO-04 / ISO-07: scope jail ──────────────────────────────────────

@pytest.mark.unit
def test_jail_rejects_traversal(tmp_path):
    with pytest.raises(ScopeError):
        scope_jail_path(tmp_path, "director-1", "../../etc/passwd")


@pytest.mark.unit
def test_jail_rejects_absolute(tmp_path):
    with pytest.raises(ScopeError):
        scope_jail_path(tmp_path, "director-1", "/etc/passwd")


@pytest.mark.unit
def test_jail_rejects_symlink_escape(tmp_path):
    (tmp_path / "_scopes" / "director-1").mkdir(parents=True)
    link = tmp_path / "out-link"
    link.symlink_to("/tmp")
    with pytest.raises(ScopeError):
        scope_jail_path(tmp_path, "director-1", "../../out-link/x.txt")


@pytest.mark.unit
def test_jail_allows_legitimate_write(tmp_path):
    p = scope_jail_path(tmp_path, "director-1", "notes/a.md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ok", encoding="utf-8")
    assert p.read_text(encoding="utf-8") == "ok"
    assert str(p).startswith(str(tmp_path.resolve()))


# ── 5-level namespace (M2 contract) ──────────────────────────────────

@pytest.mark.unit
def test_namespaced_scope_canonical_order():
    assert "c:acme/p:mem/a:d1/s:s1/u:manu" == __import__("shared.scope", fromlist=["x"]).normalize_scope(
        "u:manu/s:s1/a:d1/p:mem/c:acme"
    )


@pytest.mark.unit
def test_namespaced_scope_rejects_bad_levels():
    from shared.scope import normalize_scope
    for bad in ["x:foo", "c:a/c:b", "c:/p:y", "c:../evil"]:
        with pytest.raises(ScopeError):
            normalize_scope(bad)


@pytest.mark.unit
def test_hashed_dir_accepts_namespaced(tmp_path):
    from shared.scope import scope_dir_hashed
    d1 = scope_dir_hashed(tmp_path, "c:acme/a:d1")
    d2 = scope_dir_hashed(tmp_path, "c:acme/a:d1")
    assert d1 == d2 and d1.parent == tmp_path  # opaque, inside base


@pytest.mark.unit
def test_subdir_rejects_namespaced(tmp_path):
    from shared.scope import scope_subdir
    with pytest.raises(ScopeError):
        scope_subdir(tmp_path, "c:acme/a:d1")
