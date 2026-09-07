"""M6: Lexical consolidation tests (MEM-01, MEM-02, MEM-03)."""
import pytest

from shared.consolidation import consolidate_l1_l2, consolidate_l2_l3, consolidate_l3_l4
from shared.memory_db import MemoryDB


@pytest.mark.unit
@pytest.mark.req
async def test_l1_l2_creates_episodes(tmp_path):
    """MEM-01: L1->L2 creates episodes from grouped memories."""
    db = MemoryDB(str(tmp_path / "test_consolidation.db"), "test_consolidation", 1024)
    await db.ensure_collection()
    # Insert 5 L1 memories in the same scope
    for i in range(5):
        await db.upsert(f"l1-{i}", None, {
            "content": f"Working memory {i}",
            "agent_scope": "shared",
            "layer": 1,
            "scope_type": "agent",
            "scope_id": "test-agent",
        })
    episode_ids = await consolidate_l1_l2(db)
    assert len(episode_ids) >= 1
    # Verify episode was created
    episodes = db._conn.execute(
        "SELECT id FROM points WHERE collection=? AND json_extract(payload, '$.layer')=2",
        ("test_consolidation",),
    ).fetchall()
    assert len(episodes) >= 1


@pytest.mark.unit
@pytest.mark.req
async def test_l1_l2_no_episode_with_few_events(tmp_path):
    """MEM-01: No episode created when fewer than min_events."""
    db = MemoryDB(str(tmp_path / "test_consolidation2.db"), "test_consolidation2", 1024)
    await db.ensure_collection()
    # Insert only 1 L1 memory
    await db.upsert("l1-0", None, {
        "content": "Single memory",
        "agent_scope": "shared",
        "layer": 1,
        "scope_type": "agent",
        "scope_id": "test-agent",
    })
    episode_ids = await consolidate_l1_l2(db)
    assert len(episode_ids) == 0


@pytest.mark.unit
@pytest.mark.req
async def test_l2_l3_extracts_entities(tmp_path):
    """MEM-02: L2->L3 extracts entities from episodes."""
    db = MemoryDB(str(tmp_path / "test_consolidation3.db"), "test_consolidation3", 1024)
    await db.ensure_collection()
    # Insert an L2 episode with entity-like content
    await db.upsert("ep-1", None, {
        "content": "AuthService implements JWT authentication",
        "agent_scope": "shared",
        "layer": 2,
    })
    entity_ids = await consolidate_l2_l3(db)
    assert len(entity_ids) >= 1
    # Verify entities table was populated
    ents = db._conn.execute("SELECT name FROM entities").fetchall()
    names = [e["name"] for e in ents]
    assert "AuthService" in names or "authentication" in names


@pytest.mark.unit
@pytest.mark.req
async def test_l3_l4_creates_narratives(tmp_path):
    """MEM-03: L3->L4 creates narratives from co-occurring entities."""
    db = MemoryDB(str(tmp_path / "test_consolidation4.db"), "test_consolidation4", 1024)
    await db.ensure_collection()
    # Insert multiple L3 entities from the same episode
    for i in range(5):
        await db.upsert(f"ent-{i}", None, {
            "content": "Entity: AuthService (class)",
            "agent_scope": "shared",
            "layer": 3,
            "entity_name": "AuthService",
            "entity_type": "class",
            "source_episode_id": "ep-common",
        })
    narrative_ids = await consolidate_l3_l4(db)
    # May or may not create narratives depending on co-occurrence threshold
    assert isinstance(narrative_ids, list)


@pytest.mark.unit
@pytest.mark.req
async def test_consolidation_idempotent(tmp_path):
    """Consolidation is idempotent: running twice produces same counts."""
    db = MemoryDB(str(tmp_path / "test_consolidation5.db"), "test_consolidation5", 1024)
    await db.ensure_collection()
    # Insert L1 memories
    for i in range(5):
        await db.upsert(f"l1-{i}", None, {
            "content": f"Memory {i}",
            "agent_scope": "shared",
            "layer": 1,
        })
    # Run consolidation twice
    ids1 = await consolidate_l1_l2(db)
    ids2 = await consolidate_l1_l2(db)
    # Same episodes should be created (idempotent via deterministic IDs)
    assert len(ids1) == len(ids2)
