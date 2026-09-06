"""M2-storage core tests — memory_db engine enforcement + scope jail.

Traceability: STO-01, STO-02, STO-05, ISO-05, ISO-11, ISO-12 (specs delta
openspec/changes/M2-storage). Adversarial counterparts live in
tests/adversarial/ (A3, A10, A14, A15 shapes).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from shared.memory_db import MemoryDB, ScopeRequiredError, hash_vector
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


# ── STO-05: zero-vectors never persisted ─────────────────────────────

@pytest.mark.unit
async def test_no_zero_vector_persisted(db):
    await db.upsert("m1", [0.0] * 8, {"content": "hello", "user_id": "u1"})
    row = db._conn.execute("SELECT vector, payload FROM points WHERE id='m1'").fetchone()
    assert row["vector"] is None
    assert json.loads(row["payload"])["embedded"] is False


@pytest.mark.unit
async def test_null_vector_retrievable_via_hash_source(db):
    await db.upsert("m1", None, {"content": "stable content", "user_id": "u1"})
    hits = await db.search(None, limit=5, score_threshold=-1.0,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert len(hits) == 1
    assert hits[0]["score_source"] == "hash"
    # deterministic: same content -> same score on repeated searches
    again = await db.search(None, limit=5, score_threshold=-1.0,
                            filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert again[0]["score"] == hits[0]["score"]


@pytest.mark.unit
def test_hash_vector_deterministic():
    a = hash_vector("same text", 16)
    b = hash_vector("same text", 16)
    c = hash_vector("other text", 16)
    assert a == b and a != c
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6  # normalized


@pytest.mark.unit
async def test_dim_mismatch_stored_null(db):
    await db.upsert("m2", [0.1] * 3, {"content": "x", "user_id": "u1"})  # dim 3 != 8
    row = db._conn.execute("SELECT vector FROM points WHERE id='m2'").fetchone()
    assert row["vector"] is None


# ── ISO-05: engine-level filter (nothing foreign scored) ─────────────

@pytest.mark.unit
async def test_engine_filter_excludes_foreign_rows(db, monkeypatch):
    await db.upsert("u1-row", _vec(1.0), {"content": "mine", "user_id": "u1"})
    await db.upsert("u2-row", _vec(1.0), {"content": "theirs", "user_id": "u2"})

    scored_ids = []
    orig = MemoryDB._score_candidates

    def spy(self, rows, qv):
        scored_ids.extend(r["id"] for r in rows)
        return orig(self, rows, qv)

    monkeypatch.setattr(MemoryDB, "_score_candidates", spy)
    hits = await db.search(_vec(1.0), limit=10, score_threshold=0.0,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert scored_ids == ["u1-row"]          # u2 row NEVER fetched into scoring
    assert all(h["payload"]["user_id"] == "u1" for h in hits)


@pytest.mark.unit
async def test_high_similarity_foreign_row_not_returned(db):
    v = _vec(0.5)
    await db.upsert("foreign", v, {"content": "other user", "user_id": "u2"})
    await db.upsert("mine", [x * 0.9 for x in v], {"content": "my fact", "user_id": "u1"})
    hits = await db.search(v, limit=10, score_threshold=0.0,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert [h["id"] for h in hits] == ["mine"]


# ── ISO-11 / fail-closed reads ───────────────────────────────────────

@pytest.mark.unit
async def test_search_without_filter_fails_closed(db):
    with pytest.raises(ScopeRequiredError):
        await db.search(_vec(1.0))


@pytest.mark.unit
async def test_scroll_without_filter_fails_closed(db):
    with pytest.raises(ScopeRequiredError):
        await db.scroll(None)


@pytest.mark.unit
async def test_filter_key_validation(db):
    bad_keys = ["user_id) --", "x'; DROP TABLE points; --", "User-Id", ""]
    for key in bad_keys:
        with pytest.raises(ValueError):
            await db.search(_vec(1.0), filter={"must": [{"key": key, "match": {"value": "u1"}}]})


@pytest.mark.unit
async def test_filter_none_value_rejected(db):
    with pytest.raises(ValueError):
        await db.search(_vec(1.0), filter={"must": [{"key": "user_id", "match": {"value": None}}]})


@pytest.mark.unit
async def test_injection_value_binds_literally(db):
    await db.upsert("a", _vec(1.0), {"content": "x", "user_id": "u1"})
    hits = await db.search(_vec(1.0), score_threshold=-1.0, limit=10,
                           filter={"must": [{"key": "user_id", "match": {"value": "' OR 1=1 --"}}]})
    assert hits == []  # literal match, no injection


# ── ISO-12: default scope ────────────────────────────────────────────

@pytest.mark.unit
async def test_default_scope_is_shared(db):
    await db.upsert("anon", _vec(1.0), {"content": "no scope given"})
    hits = await db.scroll({"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert hits and hits[0]["agent_scope"] == "shared"


# ── STO-01: corrupt payload resilience + counts ──────────────────────

@pytest.mark.unit
async def test_corrupt_payload_does_not_break_search(db):
    await db.upsert("good", _vec(1.0), {"content": "fine", "user_id": "u1"})
    db._conn.execute(
        "INSERT INTO points(id, collection, vector, payload, created_at) VALUES('bad','L3_facts',NULL,'{not json','2026-01-01')"
    )
    db._conn.commit()
    hits = await db.search(_vec(1.0), limit=5, score_threshold=-1.0,
                           filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]})
    assert [h["id"] for h in hits] == ["good"]
    assert await db.count() == 2


@pytest.mark.unit
async def test_upsert_batch_and_delete_roundtrip(db):
    await db.upsert_batch([
        {"id": "b1", "vector": _vec(0.2), "payload": {"content": "one", "user_id": "u1"}},
        {"id": "b2", "vector": _vec(0.3), "payload": {"content": "two", "user_id": "u1"}},
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
