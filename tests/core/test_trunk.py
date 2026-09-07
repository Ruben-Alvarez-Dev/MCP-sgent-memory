"""M5 trunk tests — human-approved merges with provenance (ISO-06/ISO-16)."""

from __future__ import annotations

import pytest

from shared.memory_db import MemoryDB, ScopeError


@pytest.fixture()
def db(tmp_path):
    d = MemoryDB(str(tmp_path / "memory.db"), collection="L0_L4_memory", embedding_dim=8)
    d._ensure_schema()
    yield d
    d._conn.close()


def _vec(seed: float) -> list[float]:
    v = [seed] * 8
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


SHARED_FILTER = {"must": [{"key": "agent_scope", "match": {"any": ["u1", "shared", "merged"]}}]}


@pytest.mark.unit
async def test_merged_write_blocked_without_flag(db):
    """A11: automatism cannot write the trunk."""
    with pytest.raises(ScopeError):
        await db.upsert("m1", _vec(1.0), {"content": "x", "agent_scope": "merged",
                                          "approved_by": "human", "provenance": [{"from_scope": "shared", "point_id": "p1"}]})


@pytest.mark.unit
async def test_merged_write_requires_approved_by(db):
    with pytest.raises(ScopeError):
        await db.upsert("m1", _vec(1.0), {"content": "x", "agent_scope": "merged",
                                          "provenance": [{"from_scope": "shared", "point_id": "p1"}]},
                        allow_reserved_scope=True)


@pytest.mark.unit
async def test_merged_write_requires_provenance(db):
    with pytest.raises(ScopeError):
        await db.upsert("m1", _vec(1.0), {"content": "x", "agent_scope": "merged",
                                          "approved_by": "human"},
                        allow_reserved_scope=True)
    with pytest.raises(ScopeError):
        await db.upsert("m1", _vec(1.0), {"content": "x", "agent_scope": "merged",
                                          "approved_by": "human", "provenance": []},
                        allow_reserved_scope=True)


@pytest.mark.unit
async def test_approved_trunk_write_stores_and_reads(db):
    await db.upsert("m1", _vec(1.0), {"content": "approved knowledge", "agent_scope": "merged",
                                      "approved_by": "manu", "provenance": [{"from_scope": "shared", "point_id": "src1"}]},
                    allow_reserved_scope=True)
    # readable by any agent scope (public trunk)
    hits = await db.search(_vec(1.0), limit=5, score_threshold=-1.0,
                           filter={"must": [{"key": "agent_scope", "match": {"any": ["u1", "shared", "merged"]}}]})
    assert [h["id"] for h in hits] == ["m1"]


@pytest.mark.unit
async def test_approve_promotion_end_to_end(db):
    """approve_promotion contract: provenance + merged_into + public read."""
    from shared.llm import classify_intent  # noqa: F401  (import sanity of stack)

    await db.upsert("src-1", _vec(0.5), {"content": "fact A", "agent_scope": "shared", "layer": 3})
    await db.upsert("src-2", _vec(0.5), {"content": "fact B", "agent_scope": "shared", "layer": 3})

    payload = {"content": "fact A\n\n---\n\nfact B", "agent_scope": "merged",
               "approved_by": "manu",
               "provenance": [{"from_scope": "shared", "point_id": "src-1"},
                              {"from_scope": "shared", "point_id": "src-2"}],
               "layer": 4}
    await db.upsert("merged-abc", None, payload, allow_reserved_scope=True)
    await db.update_payload("src-1", {"merged_into": "merged-abc"})
    await db.update_payload("src-2", {"merged_into": "merged-abc"})

    row = await db.get("merged-abc", filter=SHARED_FILTER)
    assert row["payload"]["approved_by"] == "manu"
    assert len(row["payload"]["provenance"]) == 2
    assert {p["point_id"] for p in row["payload"]["provenance"]} == {"src-1", "src-2"}
    assert (await db.get("src-1", filter=SHARED_FILTER))["payload"]["merged_into"] == "merged-abc"
    # sources remain in their own scope (no destructive move)
    assert (await db.get("src-1", filter=SHARED_FILTER))["payload"]["agent_scope"] == "shared"


@pytest.mark.unit
async def test_trunk_visible_to_every_agent_in_engine(db):
    """A16: merged appears in engine-filtered reads for foreign scopes."""
    await db.upsert("trunk-row", _vec(0.9), {"content": "common approved fact", "agent_scope": "merged",
                                             "approved_by": "manu", "provenance": [{"from_scope": "shared", "point_id": "x"}]},
                    allow_reserved_scope=True)
    for reader in ["director-1", "engineer-1", "shared"]:
        hits = await db.search(_vec(0.9), limit=10, score_threshold=-1.0,
                               filter={"must": [{"key": "agent_scope",
                                                 "match": {"any": [reader, "shared", "merged"]}}]})
        assert any(h["id"] == "trunk-row" for h in hits), f"missing for {reader}"
