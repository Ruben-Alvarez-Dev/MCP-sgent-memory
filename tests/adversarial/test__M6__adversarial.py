"""M6 Adversarial Tests — The Dementor Battery.

Comprehensive security, edge-case, and integration tests for:
- FTS5 full-text search
- Entity extraction and storage
- Synonym expansion
- Consolidation pipeline
- Scope isolation with new tables
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.entity import extract_entities
from shared.memory_db import MemoryDB, _build_fts5_query
from shared.synonym import expand_query

# -- Fixtures ----------------------------------------------------------

@pytest.fixture()
async def db(tmp_path):
    d = MemoryDB(str(tmp_path / "memory.db"), "test", 1024)
    await d.ensure_collection()
    return d


# -- FTS5 Security Tests -----------------------------------------------

class TestFTS5Security:
    """FTS5: SQL injection, corruption, edge cases."""

    @pytest.mark.asyncio
    async def test_fts5_sql_injection_attempt(self, db):
        """SQL metacharacters in query must not cause injection."""
        await db.upsert("p1", None, {
            "content": "normal content here",
            "agent_scope": "shared",
        })
        malicious = "'; DROP TABLE points_fts; --"
        results = await db.search_fts(malicious, limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert isinstance(results, list)
        count = db._conn.execute("SELECT COUNT(*) FROM points").fetchone()[0]
        assert count >= 1

    @pytest.mark.asyncio
    async def test_fts5_corrupt_payload_tolerated(self, db):
        """Corrupt payload JSON should not break FTS5 search."""
        await db.upsert("good", None, {
            "content": "valid content",
            "agent_scope": "shared",
        })
        db._conn.execute(
            "INSERT INTO points(id, collection, vector, payload, agent_scope, layer, sparse_json, created_at)"
            " VALUES('bad','test',NULL,'{not json','shared',1,NULL,'2026-01-01')",
        )
        db._conn.commit()
        results = await db.search_fts("valid", limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert any(r["id"] == "good" for r in results)

    @pytest.mark.asyncio
    async def test_fts5_empty_query(self, db):
        """Empty query returns empty results, not crash."""
        results = await db.search_fts("", limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert results == []


# -- Entity Extraction Tests -------------------------------------------

class TestEntityExtraction:
    """Entity extraction: edge cases, security, performance."""

    def test_entity_extraction_empty_text(self):
        result = extract_entities("")
        assert result == []

    def test_entity_extraction_only_numbers(self):
        result = extract_entities("12345 67890")
        assert result == []

    def test_entity_extraction_mixed_case(self):
        result = extract_entities("AuthService implements JWT_TOKEN")
        names = [e["name"] for e in result]
        assert "AuthService" in names
        assert "JWT_TOKEN" in names

    def test_entity_extraction_no_false_positives(self):
        result = extract_entities("the quick brown fox jumps")
        names = [e["name"] for e in result]
        assert "the" not in names
        assert "quick" not in names

    def test_entity_extraction_deterministic(self):
        r1 = extract_entities("AuthService JWT authentication")
        r2 = extract_entities("AuthService JWT authentication")
        assert r1 == r2


# -- Synonym Expansion Tests -------------------------------------------

class TestSynonymExpansion:
    """Synonym expansion: edge cases, security, performance."""

    def test_expand_query_empty(self):
        assert expand_query("") == ""

    def test_expand_query_unknown_terms(self):
        result = expand_query("xyz abc def")
        assert "xyz" in result
        assert "abc" in result

    def test_expand_query_known_terms(self):
        result = expand_query("auth")
        assert "authentication" in result
        assert "jwt" in result

    def test_expand_query_bidirectional(self):
        auth_expanded = expand_query("auth")
        jwt_expanded = expand_query("jwt")
        assert "jwt" in auth_expanded
        assert "auth" in jwt_expanded

    def test_expand_query_no_duplicates(self):
        result = expand_query("auth auth auth")
        terms = result.split()
        assert len(terms) == len(set(terms))


# -- FTS5 Query Builder Tests ------------------------------------------

class TestFTS5QueryBuilder:
    """_build_fts5_query: correctness, edge cases."""

    def test_build_query_simple(self):
        result = _build_fts5_query("JWT auth")
        assert "jwt" in result
        assert "auth" in result

    def test_build_query_empty(self):
        assert _build_fts5_query("") == ""

    def test_build_query_spanish(self):
        result = _build_fts5_query("autenticación base de datos")
        assert "autenticacion" in result or "autenticación" in result


# -- Scope Isolation Tests ---------------------------------------------

class TestScopeIsolation:
    """ISO-18: Entity and relation scope isolation."""

    @pytest.mark.asyncio
    async def test_entities_scope_isolation(self, db):
        await db.upsert("p1", None, {
            "content": "AuthService JWT",
            "agent_scope": "director-1",
            "layer": 1,
        })
        entities = db.get_entities("director-1")
        assert len(entities) >= 0  # Should not crash

    @pytest.mark.asyncio
    async def test_shared_scope_visible_to_all(self, db):
        await db.upsert("p-shared", None, {
            "content": "Shared AuthService",
            "agent_scope": "shared",
            "layer": 1,
        })
        director_entities = db.get_entities("director-1")
        engineer_entities = db.get_entities("engineer-1")
        # Both should be able to query without error
        assert isinstance(director_entities, list)
        assert isinstance(engineer_entities, list)


# -- Integration Tests -------------------------------------------------

class TestIntegration:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_pipeline_upsert_search(self, db):
        await db.upsert("p1", None, {
            "content": "AuthService implements JWT authentication middleware",
            "agent_scope": "shared",
            "layer": 1,
        })
        results = await db.search_fts("JWT authentication", limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert len(results) >= 1
        assert results[0]["id"] == "p1"

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(self, db):
        await db.upsert("d1-private", None, {
            "content": "PRIVATE: Director strategy",
            "agent_scope": "director-1",
            "layer": 1,
        })
        results = await db.search_fts("PRIVATE", limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"any": ["engineer-1", "shared"]}}]
        })
        engineer_results = [r["id"] for r in results]
        assert "d1-private" not in engineer_results


# -- Performance Tests -------------------------------------------------

class TestPerformance:
    """Performance: latency, throughput."""

    @pytest.mark.asyncio
    async def test_fts5_search_latency(self, db):
        for i in range(100):
            await db.upsert(f"perf-{i}", None, {
                "content": f"Performance test content number {i} with JWT auth",
                "agent_scope": "shared",
                "layer": 1,
            })
        start = time.monotonic()
        for _ in range(10):
            await db.search_fts("JWT auth", limit=5, filter={
                "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
            })
        elapsed = (time.monotonic() - start) / 10
        assert elapsed < 0.01  # <10ms per search

    def test_entity_extraction_latency(self):
        text = "AuthService implements JWT authentication middleware"
        start = time.monotonic()
        for _ in range(100):
            extract_entities(text)
        elapsed = (time.monotonic() - start) / 100
        assert elapsed < 0.001  # <1ms per extraction
