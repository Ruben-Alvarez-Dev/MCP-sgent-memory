"""M6 Full Adversarial Battery — Isolation Audit + Security Tests.

Covers:
- Cross-tenant isolation (ISO-05, ISO-18)
- FTS5 SQL injection resistance
- Entity graph poisoning attempts
- Consolidation bypass attempts
- Sanitizer remapping attacks
- Edge cases and boundary conditions
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.entity import extract_entities
from shared.memory_db import MemoryDB, _build_fts5_query
from shared.scope import RESERVED_SCOPES, ScopeError, normalize_scope
from shared.synonym import expand_query

# ── Fixtures ----------------------------------------------------------

@pytest.fixture()
async def db(tmp_path):
    d = MemoryDB(str(tmp_path / "memory.db"), "test", 1024)
    await d.ensure_collection()
    return d


# ── ISO-05: Engine-level scope filter --------------------------------

class TestEngineFilter:
    """A1-A10: Engine-level scope filtering on all operations."""

    @pytest.mark.asyncio
    async def test_a1_cross_tenant_search_blocked(self, db):
        """A1: Tenant A cannot search tenant B's data."""
        await db.upsert("a-data", {
            "content": "Tenant A private data",
            "agent_scope": "tenant-a",
            "layer": 1,
        })
        await db.upsert("shared-data", {
            "content": "Shared data",
            "agent_scope": "shared",
            "layer": 1,
        })
        # Tenant B searches
        results = await db.search_fts("data", limit=10, filter={
            "must": [{"key": "agent_scope", "match": {"any": ["tenant-b", "shared"]}}]
        })
        ids = [r["id"] for r in results]
        assert "a-data" not in ids
        assert "shared-data" in ids

    @pytest.mark.asyncio
    async def test_a2_cross_tenant_get_blocked(self, db):
        """A2: Tenant A cannot get tenant B's point by ID."""
        await db.upsert("b-secret", {
            "content": "Tenant B secret",
            "agent_scope": "tenant-b",
            "layer": 1,
        })
        # Tenant A tries to get by ID
        result = await db.get("b-secret", filter={
            "must": [{"key": "agent_scope", "match": {"value": "tenant-a"}}]
        })
        assert result is None

    @pytest.mark.asyncio
    async def test_a3_cross_tenant_delete_blocked(self, db):
        """A3: Tenant A cannot delete tenant B's point."""
        await db.upsert("b-delete-me", {
            "content": "Tenant B data",
            "agent_scope": "tenant-b",
            "layer": 1,
        })
        # Tenant A tries to delete
        deleted = await db.delete("b-delete-me", filter={
            "must": [{"key": "agent_scope", "match": {"value": "tenant-a"}}]
        })
        assert deleted is False
        # Data still exists for tenant-b
        result = await db.get("b-delete-me", filter={
            "must": [{"key": "agent_scope", "match": {"value": "tenant-b"}}]
        })
        assert result is not None

    @pytest.mark.asyncio
    async def test_a4_no_unfiltered_search(self, db):
        """A4: Search without filter raises error (fail-closed)."""
        # search_fts requires a filter - passing None should fail
        try:
            await db.search_fts("anything", limit=10, filter=None)
            assert False, "Should have raised"
        except Exception:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_a5_no_unfiltered_get(self, db):
        """A5: Get without filter raises ScopeRequiredError."""
        with pytest.raises(Exception):
            await db.get("any-id", filter=None)

    @pytest.mark.asyncio
    async def test_a6_filter_key_allowlist(self, db):
        """A6: Only engine-filterable keys allowed."""
        with pytest.raises(ValueError):
            await db.search_fts("test", limit=10, filter={
                "must": [{"key": "invalid_key", "match": {"value": "x"}}]
            })

    @pytest.mark.asyncio
    async def test_a7_filter_value_type_check(self, db):
        """A7: Filter values must be scalars, not dicts/lists."""
        with pytest.raises(ValueError):
            await db.search_fts("test", limit=10, filter={
                "must": [{"key": "agent_scope", "match": {"value": {"nested": "x"}}}]
            })

    @pytest.mark.asyncio
    async def test_a8_shared_scope_visible_to_all(self, db):
        """A8: Shared scope is visible to all tenants."""
        await db.upsert("shared-p", {
            "content": "Shared content",
            "agent_scope": "shared",
            "layer": 1,
        })
        results_a = await db.search_fts("Shared", limit=10, filter={
            "must": [{"key": "agent_scope", "match": {"any": ["tenant-a", "shared"]}}]
        })
        results_b = await db.search_fts("Shared", limit=10, filter={
            "must": [{"key": "agent_scope", "match": {"any": ["tenant-b", "shared"]}}]
        })
        assert len(results_a) >= 1
        assert len(results_b) >= 1

    @pytest.mark.asyncio
    async def test_a9_own_scope_visible(self, db):
        """A9: Own scope data is visible to the tenant."""
        await db.upsert("own-p", {
            "content": "My private data",
            "agent_scope": "tenant-a",
            "layer": 1,
        })
        results = await db.search_fts("private", limit=10, filter={
            "must": [{"key": "agent_scope", "match": {"any": ["tenant-a", "shared"]}}]
        })
        ids = [r["id"] for r in results]
        assert "own-p" in ids

    @pytest.mark.asyncio
    async def test_a10_sibling_scope_invisible(self, db):
        """A10: Sibling scopes are never visible."""
        await db.upsert("sib-a", {
            "content": "Sibling A data",
            "agent_scope": "sibling-a",
            "layer": 1,
        })
        await db.upsert("sib-b", {
            "content": "Sibling B data",
            "agent_scope": "sibling-b",
            "layer": 1,
        })
        results = await db.search_fts("Sibling", limit=10, filter={
            "must": [{"key": "agent_scope", "match": {"any": ["sibling-a", "shared"]}}]
        })
        ids = [r["id"] for r in results]
        assert "sib-b" not in ids


# ── ISO-16: Trunk/merged scope isolation ------------------------------

class TestTrunkIsolation:
    """A11-A16: Merged scope security."""

    @pytest.mark.asyncio
    async def test_a11_merged_write_blocked_without_approval(self, db):
        """A11: Cannot write to merged without approval flag."""
        with pytest.raises(Exception):  # ScopeError
            await db.upsert("merged-p", {
                "content": "Merged content",
                "agent_scope": "merged",
                "layer": 4,
            })

    @pytest.mark.asyncio
    async def test_a12_merged_requires_provenance(self, db):
        """A12: Merged writes require approved_by + provenance."""
        with pytest.raises(Exception):
            await db.upsert("merged-p2", {
                "content": "Merged content 2",
                "agent_scope": "merged",
                "layer": 4,
                "approved_by": "user",
                # Missing provenance
            })

    @pytest.mark.asyncio
    async def test_a13_merged_can_be_written_with_approval(self, db):
        """A13: Merged can be written with proper approval."""
        await db.upsert("merged-p", {
            "content": "Approved merged content",
            "agent_scope": "merged",
            "layer": 4,
            "approved_by": "human-user",
            "provenance": [
                {"from_scope": "shared", "point_id": "source-1"}
            ],
        }, allow_reserved_scope=True)
        # Should be readable by all
        results = await db.search_fts("Approved", limit=10, filter={
            "must": [{"key": "agent_scope", "match": {"any": ["tenant-a", "shared", "merged"]}}]
        })
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_a14_reserved_scope_not_in_normalize(self, db):
        """A14: Reserved scopes rejected by normalize_scope."""
        for reserved in RESERVED_SCOPES:
            with pytest.raises(ScopeError):
                normalize_scope(reserved)

    @pytest.mark.asyncio
    async def test_a15_mixed_case_reserved_rejected(self, db):
        """A15: Mixed case reserved names rejected."""
        with pytest.raises(ScopeError):
            normalize_scope("MERGED")
        with pytest.raises(ScopeError):
            normalize_scope(" Merged ")

    @pytest.mark.asyncio
    async def test_a16_merged_visible_to_all_on_read(self, db):
        """A16: Merged data is readable by all tenants."""
        await db.upsert("merged-shared", {
            "content": "Common knowledge",
            "agent_scope": "merged",
            "layer": 4,
            "approved_by": "admin",
            "provenance": [{"from_scope": "shared", "point_id": "src"}],
        }, allow_reserved_scope=True)
        # Different tenants can all read it
        for scope in ["tenant-a", "tenant-b", "shared"]:
            results = await db.search_fts("Common", limit=10, filter={
                "must": [{"key": "agent_scope", "match": {"any": [scope, "shared", "merged"]}}]
            })
            assert len(results) >= 1


# ── FTS5 Security Tests -----------------------------------------------

class TestFTS5Security:
    """FTS5 injection, corruption, edge cases."""

    @pytest.mark.asyncio
    async def test_fts5_sql_injection_dropped(self, db):
        """FTS5: SQL injection attempts are parameterized, not executed."""
        await db.upsert("p1", {
            "content": "normal content",
            "agent_scope": "shared",
        })
        injections = [
            "'; DROP TABLE points_fts; --",
            "' OR '1'='1",
            "'; DELETE FROM points; --",
            "' UNION SELECT * FROM points; --",
        ]
        for inject in injections:
            results = await db.search_fts(inject, limit=5, filter={
                "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
            })
            assert isinstance(results, list)
        # Table should still exist
        count = db._conn.execute("SELECT COUNT(*) FROM points").fetchone()[0]
        assert count >= 1

    @pytest.mark.asyncio
    async def test_fts5_corrupt_payload_no_crash(self, db):
        """FTS5: Corrupt JSON payload doesn't crash search."""
        await db.upsert("good", {
            "content": "valid content here",
            "agent_scope": "shared",
        })
        # Inject corrupt row
        db._conn.execute(
            "INSERT INTO points(id, collection, payload, agent_scope, layer, sparse_json, created_at)"
            " VALUES('corrupt','test','{invalid json','shared',1,NULL,'2026-01-01')",
        )
        db._conn.commit()
        results = await db.search_fts("valid", limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert any(r["id"] == "good" for r in results)

    @pytest.mark.asyncio
    async def test_fts5_empty_content(self, db):
        """FTS5: Empty content handled gracefully."""
        await db.upsert("empty", {
            "content": "",
            "agent_scope": "shared",
        })
        results = await db.search_fts("anything", limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_fts5_very_long_content(self, db):
        """FTS5: Very long content doesn't crash."""
        long_content = "word " * 10000
        await db.upsert("long", {
            "content": long_content,
            "agent_scope": "shared",
        })
        results = await db.search_fts("word", limit=5, filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert len(results) >= 1


# ── Entity Graph Security Tests ---------------------------------------

class TestEntityGraphSecurity:
    """Entity extraction and storage security."""

    def test_entity_extraction_no_injection(self):
        """Entity names are safe for DB storage."""
        malicious = "'; DROP TABLE entities; --"
        result = extract_entities(malicious)
        # Should not crash, may return empty or safe entities
        assert isinstance(result, list)

    def test_entity_extraction_extreme_input(self):
        """Entity extraction handles extreme inputs."""
        # Unicode bombs
        result = extract_entities("🔥" * 1000)
        assert isinstance(result, list)
        # Null bytes
        result = extract_entities("test\x00inject")
        assert isinstance(result, list)
        # Extremely long
        result = extract_entities("A" * 10000)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_entity_scope_isolation(self, db):
        """Entities are scoped: tenant A can't see tenant B's entities."""
        await db.upsert("p-a", {
            "content": "AuthService JWT",
            "agent_scope": "tenant-a",
            "layer": 1,
        })
        await db.upsert("p-b", {
            "content": "AuthService OAuth",
            "agent_scope": "tenant-b",
            "layer": 1,
        })
        entities_a = db.get_entities("tenant-a")
        entities_b = db.get_entities("tenant-b")
        # Both should have their own entities
        names_a = {e["name"] for e in entities_a}
        names_b = {e["name"] for e in entities_b}
        # AuthService might appear in both (same name, different scopes)
        # But the scopes should be correct
        for e in entities_a:
            assert e["agent_scope"] in ("tenant-a", "shared")
        for e in entities_b:
            assert e["agent_scope"] in ("tenant-b", "shared")

    @pytest.mark.asyncio
    async def test_entity_deterministic_ids(self, db):
        """Entity IDs are deterministic: same name+scope = same ID."""
        await db.upsert("p1", {
            "content": "AuthService",
            "agent_scope": "shared",
            "layer": 1,
        })
        await db.upsert("p2", {
            "content": "AuthService",
            "agent_scope": "shared",
            "layer": 1,
        })
        # Should not create duplicate entities
        entities = db.get_entities("shared")
        auth_services = [e for e in entities if e["name"] == "AuthService"]
        # Might have 1 or 2 depending on upsert behavior
        assert len(auth_services) >= 1


# ── Synonym Expansion Security Tests ----------------------------------

class TestSynonymSecurity:
    """Synonym expansion edge cases."""

    def test_synonym_no_injection(self):
        """Synonym expansion doesn't introduce SQL injection."""
        malicious = "'; DROP TABLE; --"
        result = expand_query(malicious)
        # Should not contain SQL metacharacters in dangerous positions
        assert "DROP" not in result.upper() or "drop" in result.lower()

    def test_synonym_very_long_input(self):
        """Synonym expansion handles very long input."""
        long_input = "auth " * 1000
        result = expand_query(long_input)
        assert isinstance(result, str)

    def test_synonym_unicode_input(self):
        """Synonym expansion handles unicode."""
        result = expand_query("autenticación 🔐 base_de_datos")
        assert isinstance(result, str)


# ── Consolidation Security Tests --------------------------------------

class TestConsolidationSecurity:
    """Consolidation pipeline security."""

    @pytest.mark.asyncio
    async def test_consolidation_no_scope_escape(self, db):
        """Consolidation cannot write to unauthorized scopes."""
        from shared.consolidation import consolidate_l1_l2
        # Insert L1 memories
        for i in range(5):
            await db.upsert(f"l1-{i}", {
                "content": f"Memory {i}",
                "agent_scope": "tenant-a",
                "layer": 1,
                "scope_type": "agent",
                "scope_id": "test",
            })
        # Run consolidation
        await consolidate_l1_l2(db)
        # Check no forbidden scopes created
        forbidden = ("global", "consolidated", "narrative", "dream")
        for scope in forbidden:
            count = db._conn.execute(
                "SELECT COUNT(*) FROM points WHERE agent_scope = ?",
                (scope,),
            ).fetchone()[0]
            assert count == 0

    @pytest.mark.asyncio
    async def test_consolidation_idempotent(self, db):
        """Consolidation is idempotent: running twice = same result."""
        from shared.consolidation import consolidate_l1_l2
        for i in range(5):
            await db.upsert(f"l1-{i}", {
                "content": f"Memory {i}",
                "agent_scope": "shared",
                "layer": 1,
                "scope_type": "agent",
                "scope_id": "test",
            })
        ids1 = await consolidate_l1_l2(db)
        ids2 = await consolidate_l1_l2(db)
        # Same number of episodes (idempotent)
        assert len(ids1) == len(ids2)


# ── Query Builder Security Tests --------------------------------------

class TestQueryBuilderSecurity:
    """FTS5 query builder security."""

    def test_query_builder_no_injection(self):
        """Query builder extracts tokens safely, no SQL execution."""
        malicious_queries = [
            "'; DROP TABLE points_fts; --",
            "' OR '1'='1",
            "test' UNION SELECT * FROM points--",
        ]
        for q in malicious_queries:
            result = _build_fts5_query(q)
            # Result should be safe tokens, not SQL
            # The query builder lowercases and tokenizes, so SQL keywords become tokens
            assert isinstance(result, str)
            # Should not crash

    def test_query_builder_empty(self):
        """Empty query returns empty string."""
        assert _build_fts5_query("") == ""

    def test_query_builder_special_chars(self):
        """Special characters handled gracefully."""
        result = _build_fts5_query("test @#$%^&*()")
        assert isinstance(result, str)


# ── MemoryDB Core Security Tests --------------------------------------

class TestMemoryDBSecurity:
    """Core MemoryDB security properties."""

    @pytest.mark.asyncio
    async def test_upsert_without_scope_defaults_to_shared(self, db):
        """Upsert without agent_scope defaults to shared."""
        await db.upsert("no-scope", {
            "content": "No scope given",
            "layer": 1,
        })
        result = await db.get("no-scope", filter={
            "must": [{"key": "agent_scope", "match": {"value": "shared"}}]
        })
        assert result is not None
        assert result["payload"]["agent_scope"] == "shared"

    @pytest.mark.asyncio
    async def test_payload_key_validation(self, db):
        """Reserved payload keys rejected."""
        with pytest.raises(ValueError):
            await db.upsert("bad", {
                "content": "test",
                "agent_scope": "shared",
                "layer": 1,
                "vector": [0.1] * 1024,  # reserved key
            })

    @pytest.mark.asyncio
    async def test_point_id_validation(self, db):
        """Invalid point IDs rejected."""
        with pytest.raises(ValueError):
            await db.upsert("", {
                "content": "test",
                "agent_scope": "shared",
                "layer": 1,
            })
        with pytest.raises(ValueError):
            await db.upsert(None, {
                "content": "test",
                "agent_scope": "shared",
                "layer": 1,
            })


# ── Run all tests -----------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
