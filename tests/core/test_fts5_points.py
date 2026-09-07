"""M6: FTS5 full-text search on points (STO-07)."""
import pytest

from shared.memory_db import MemoryDB


@pytest.mark.unit
@pytest.mark.req
async def test_fts5_sync_on_upsert(tmp_path):
    """STO-07: FTS5 stays in sync after upsert."""
    db = MemoryDB(str(tmp_path / "test_fts.db"), "test_fts", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "AuthService JWT authentication", "agent_scope": "shared"})
    results = await db.search_fts("JWT authentication", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert len(results) >= 1
    assert results[0]["id"] == "p1"
    assert results[0]["score_source"] == "fts5"


@pytest.mark.unit
@pytest.mark.req
async def test_fts5_parameterized_no_injection(tmp_path):
    """FTS5 query is parameterized — SQL metacharacters are safe."""
    db = MemoryDB(str(tmp_path / "test_fts2.db"), "test_fts2", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "normal content", "agent_scope": "shared"})
    results = await db.search_fts("'; DROP TABLE; --", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert isinstance(results, list)


@pytest.mark.unit
@pytest.mark.req
async def test_fts5_with_scope_filter(tmp_path):
    """FTS5 respects engine-level scope filter."""
    db = MemoryDB(str(tmp_path / "test_fts3.db"), "test_fts3", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "AuthService", "agent_scope": "director-1"})
    await db.upsert("p2", {"content": "AuthService", "agent_scope": "shared"})
    results = await db.search_fts("AuthService", limit=5, filter={"must": [{"key": "agent_scope", "match": {"any": ["engineer-1", "shared"]}}]})
    ids = [r["id"] for r in results]
    assert "p2" in ids
    assert "p1" not in ids


@pytest.mark.unit
@pytest.mark.req
async def test_fts5_fallback_on_corrupt(tmp_path):
    """FTS5 fallback: corrupt payload does not break search."""
    db = MemoryDB(str(tmp_path / "test_fts4.db"), "test_fts4", 1024)
    await db.ensure_collection()
    await db.upsert("good", {"content": "fine content", "agent_scope": "shared"})
    db._conn.execute(
        "INSERT INTO points(id, collection, payload, agent_scope, layer, sparse_json, created_at)"
            " VALUES(\'bad\',\'test_fts4\',\'{not json\',\'shared\',1,NULL,\'2026-01-01\')",
    )
    db._conn.commit()
    results = await db.search_fts("fine", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert any(r["id"] == "good" for r in results)


@pytest.mark.unit
@pytest.mark.req
async def test_fts5_empty_table(tmp_path):
    """FTS5 on empty table returns empty results."""
    db = MemoryDB(str(tmp_path / "test_fts5.db"), "test_fts5", 1024)
    await db.ensure_collection()
    results = await db.search_fts("anything", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert results == []
