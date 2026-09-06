"""Adversarial engine-filter matrix — M2-storage (ISO-05: A3 + A10).

Proves user isolation is enforced by the STORAGE ENGINE (SQL WHERE), not by
harness-side Python post-filtering. Adversarial stance:

  A3  — a foreign row that is MORE similar to the query than any own row must
        never be scored (spied via MemoryDB._score_candidates) nor returned.
        Includes the L3_facts server wiring: search_memory MUST delegate the
        filter to the engine (regression guard against reintroduced
        post-filtering, which the spy makes detectable).
  A10 — malformed filters (non-allowlisted key, None value) fail closed with
        ValueError; a missing filter raises ScopeRequiredError instead of
        silently scanning cross-user rows.

Core (non-adversarial) counterparts: tests/core/test_memory_db.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.isolation, pytest.mark.req("ISO-05")]

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.memory_db import MemoryDB, ScopeRequiredError


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


def _user_filter(user_id: str) -> dict:
    return {"must": [{"key": "user_id", "match": {"value": user_id}}]}


def _spy_score_candidates(monkeypatch, seen_ids: list):
    """Record the ids of every row the engine hands to the scorer.

    If a foreign row appears here, the engine filter failed BEFORE scoring —
    exactly what ISO-05 forbids (post-filtering after scoring is too late:
    it leaks via scores/timings and wastes work on foreign rows).
    """
    orig = MemoryDB._score_candidates

    def spy(self, rows, query_vec):
        seen_ids.extend(r["id"] for r in rows)
        return orig(self, rows, query_vec)

    monkeypatch.setattr(MemoryDB, "_score_candidates", spy)


# ── A3: falsified identity — engine never even scores foreign rows ──


class TestA3EngineFilterNeverScoresForeignRows:
    async def test_foreign_row_never_scored_nor_returned(self, db, monkeypatch):
        # adversarial setup: u2's row is IDENTICAL to the query vector, u1's
        # is only ~90% aligned — a post-filter bug would rank u2 first.
        await db.upsert("u2-decoy", _vec(1.0), {"content": "decoy", "user_id": "u2"})
        await db.upsert("u1-own", [0.9] * 8, {"content": "mine", "user_id": "u1"})

        seen: list = []
        _spy_score_candidates(monkeypatch, seen)

        hits = await db.search(_vec(1.0), limit=10, score_threshold=0.0, filter=_user_filter("u1"))

        assert seen == ["u1-own"], f"engine scored foreign rows: {seen}"
        assert [h["id"] for h in hits] == ["u1-own"]
        assert all(h["payload"]["user_id"] == "u1" for h in hits)

    async def test_many_users_only_caller_scored(self, db, monkeypatch):
        for i in range(5):
            await db.upsert(f"victim-{i}", _vec(1.0), {"content": f"c{i}", "user_id": f"user-{i}"})
        await db.upsert("caller", _vec(0.7), {"content": "mine", "user_id": "victim-0"})

        seen: list = []
        _spy_score_candidates(monkeypatch, seen)

        hits = await db.search(_vec(1.0), limit=10, score_threshold=-1.0, filter=_user_filter("victim-0"))

        assert seen == ["caller"]
        assert [h["id"] for h in hits] == ["caller"]

    async def test_hash_scored_rows_still_isolated(self, db, monkeypatch):
        """NULL-vector rows (hash scoring) must respect the engine filter too."""
        await db.upsert("u2-null", None, {"content": "decoy secret", "user_id": "u2"})
        await db.upsert("u1-null", None, {"content": "my secret", "user_id": "u1"})

        seen: list = []
        _spy_score_candidates(monkeypatch, seen)

        hits = await db.search(None, limit=10, score_threshold=-1.0, filter=_user_filter("u1"))

        assert seen == ["u1-null"]
        assert [h["id"] for h in hits] == ["u1-null"]

    async def test_scroll_never_returns_foreign_rows(self, db):
        await db.upsert("u1-a", _vec(1.0), {"content": "a", "user_id": "u1"})
        await db.upsert("u2-b", _vec(1.0), {"content": "b", "user_id": "u2"})
        rows = await db.scroll(filter=_user_filter("u1"), limit=50)
        assert [r["user_id"] for r in rows] == ["u1"]

    async def test_atomic_delete_cannot_cross_users(self, db):
        """Ownership-enforced delete: u2's filter must not remove u1's point."""
        await db.upsert("u1-row", _vec(1.0), {"content": "mine", "user_id": "u1"})
        assert await db.delete("u1-row", filter=_user_filter("u2")) is False
        assert await db.get("u1-row") is not None  # untouched — no TOCTOU window
        assert await db.delete("u1-row", filter=_user_filter("u1")) is True
        assert await db.get("u1-row") is None


class TestA3ServerWiring:
    """The L3_facts server must delegate filtering to the engine, never
    post-filter in Python (ISO-05). The search spy verifies the filter kwarg
    actually reaches db.search with the caller's user_id."""

    @pytest.fixture()
    def l3(self, tmp_path, monkeypatch, db):
        import L3_facts.server.main as mod

        monkeypatch.setattr(mod, "db", db)

        async def _fake_embed(text: str) -> list[float]:
            return _vec(1.0)

        monkeypatch.setattr(mod, "safe_embed", _fake_embed)
        return mod

    async def test_search_memory_passes_engine_filter(self, l3, db, monkeypatch):
        await db.upsert("mine", _vec(0.9), {"content": "mine", "user_id": "u1"})
        await db.upsert("decoy", _vec(1.0), {"content": "decoy", "user_id": "u2"})

        calls: list = []
        orig = MemoryDB.search

        async def spy(self, vector, **kwargs):
            calls.append(kwargs.get("filter"))
            return await orig(self, vector, **kwargs)

        monkeypatch.setattr(MemoryDB, "search", spy)

        res = await l3.search_memory("find stuff", user_id="u1", limit=10, min_score=0.0)

        assert calls == [_user_filter("u1")], "server must forward user_id as engine filter"
        assert res.count == 1
        assert res.results[0]["user_id"] == "u1"  # decoy never returned

    async def test_get_all_memories_scoped(self, l3, db):
        await db.upsert("mine", _vec(1.0), {"content": "mine", "user_id": "u1"})
        await db.upsert("theirs", _vec(1.0), {"content": "theirs", "user_id": "u2"})
        res = await l3.get_all_memories(user_id="u1")
        assert res.count == 1
        assert res.memories[0]["user_id"] == "u1"

    async def test_delete_memory_scoped(self, l3, db):
        await db.upsert("mine", _vec(1.0), {"content": "mine", "user_id": "u1"})
        res = await l3.delete_memory("mine", user_id="u2")
        assert res.status == "not_found"
        assert await db.get("mine") is not None  # u1's row survived u2's attempt
        res = await l3.delete_memory("mine", user_id="u1")
        assert res.status == "deleted"
        assert await db.get("mine") is None


# ── A10: arbitrary filter keys — fail closed, never silent ──────────


class TestA10FilterShapeFailClosed:
    @pytest.mark.parametrize(
        "bad_filter",
        [
            {"must": [{"key": "no_permitida", "match": {"value": "u1"}}]},
            {"must": [{"key": "agent_scope; DROP TABLE points;--", "match": {"value": "u1"}}]},
            {"must": [{"key": "user_id", "match": {"value": None}}]},
            {"must": [{"key": "user_id", "match": {"value": {"$gt": ""}}}]},  # non-scalar
            {"must": []},                                   # empty condition list
            {"must": [{"key": "user_id", "match": None}]},   # no match struct
            {"must": ["user_id"]},                           # non-dict condition
        ],
    )
    async def test_malformed_filter_raises_valueerror(self, db, bad_filter):
        with pytest.raises(ValueError):
            await db.search(_vec(1.0), filter=bad_filter)

    async def test_search_without_filter_fails_closed(self, db):
        with pytest.raises(ScopeRequiredError):
            await db.search(_vec(1.0))

    async def test_scroll_without_filter_fails_closed(self, db):
        with pytest.raises(ScopeRequiredError):
            await db.scroll(filter=None)

    async def test_scroll_bad_key_raises_valueerror(self, db):
        with pytest.raises(ValueError):
            await db.scroll(filter={"must": [{"key": "no_permitida", "match": {"value": "u1"}}]})

    async def test_cross_user_value_is_literal_not_wildcard(self, db):
        """A crafted user_id value must bind literally and match nothing."""
        await db.upsert("a", _vec(1.0), {"content": "x", "user_id": "u1"})
        hits = await db.search(_vec(1.0), score_threshold=-1.0, limit=10, filter=_user_filter("*"))
        assert hits == []
