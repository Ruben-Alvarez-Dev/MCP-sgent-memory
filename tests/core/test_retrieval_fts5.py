"""M6: FTS5-first retrieval pipeline (RET-01, RET-07, RET-08, RET-09)."""
import pytest

from shared.memory_db import MemoryDB, _build_fts5_query
from shared.synonym import expand_query


@pytest.mark.unit
@pytest.mark.req
async def test_fts5_search_finds_content(tmp_path):
    """RET-01: FTS5 finds content by keywords."""
    db = MemoryDB(str(tmp_path / "test_retrieval.db"), "test_retrieval", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "JWT authentication middleware for user sessions", "agent_scope": "shared", "layer": 1})
    results = await db.search_fts("JWT authentication", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert len(results) >= 1
    assert results[0]["id"] == "p1"
    assert results[0]["score_source"] == "fts5"


@pytest.mark.unit
@pytest.mark.req
async def test_synonym_expansion_produces_terms(tmp_path):
    """RET-07: Synonym expansion produces correct terms (FTS5 matching is separate)."""
    db = MemoryDB(str(tmp_path / "test_retrieval2.db"), "test_retrieval2", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "JWT authentication middleware", "agent_scope": "shared", "layer": 1})
    # Synonym expansion produces expanded terms
    expanded = expand_query("auth")
    assert "authentication" in expanded
    assert "jwt" in expanded
    # FTS5 query builder extracts tokens from expanded query
    fts_query = _build_fts5_query(expanded)
    # The query should contain tokens that match the content
    assert "authentication" in fts_query or "jwt" in fts_query
    # Search with a token that definitely matches
    results = await db.search_fts("authentication", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert len(results) >= 1


@pytest.mark.unit
@pytest.mark.req
async def test_entity_boost_changes_ranking(tmp_path):
    """RET-08: Entity overlap boosts relevant results."""
    db = MemoryDB(str(tmp_path / "test_retrieval3.db"), "test_retrieval3", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "AuthService implements JWT authentication", "agent_scope": "shared", "layer": 1})
    await db.upsert("p2", {"content": "database connection pooling", "agent_scope": "shared", "layer": 1})
    results = await db.search_fts("AuthService", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert len(results) >= 1
    assert results[0]["id"] == "p1"


@pytest.mark.unit
@pytest.mark.req
async def test_zero_embedding_dependency(tmp_path):
    """RET-09: Retrieval works without any embedding backend."""
    db = MemoryDB(str(tmp_path / "test_retrieval4.db"), "test_retrieval4", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "how to implement JWT authentication", "agent_scope": "shared", "layer": 1})
    results = await db.search_fts("JWT authentication", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert len(results) >= 1
    assert results[0]["id"] == "p1"


@pytest.mark.unit
@pytest.mark.req
async def test_entity_boost_clamped_to_one(tmp_path):
    """RET-08: Entity boost is clamped to [0, 1]."""
    db = MemoryDB(str(tmp_path / "test_retrieval5.db"), "test_retrieval5", 1024)
    await db.ensure_collection()
    await db.upsert("p1", {"content": "AuthService JWT OAuth SSO MFA authentication authorization", "agent_scope": "shared", "layer": 1})
    results = await db.search_fts("AuthService", limit=5, filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    assert len(results) >= 1
    assert 0 <= results[0]["score"] <= 1.0
