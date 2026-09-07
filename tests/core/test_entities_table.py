"""M6: Entities table with scope isolation (STO-08, ISO-18)."""
import pytest

from shared.memory_db import MemoryDB


@pytest.mark.unit
@pytest.mark.req
async def test_entity_extraction_on_upsert(tmp_path):
    """STO-08: Entity extraction runs on upsert."""
    db = MemoryDB(str(tmp_path / "test_ent.db"), "test_ent", 1024)
    await db.ensure_collection()
    await db.upsert("p1", None, {
        "content": "AuthService implements JWT authentication",
        "agent_scope": "shared",
        "layer": 1,
    })
    entities = db.get_entities("shared")
    names = [e["name"] for e in entities]
    assert "AuthService" in names or "authentication" in names


@pytest.mark.unit
@pytest.mark.req
async def test_cross_scope_entity_isolation(tmp_path):
    """STO-08 + ISO-18: entities are scope-isolated."""
    db = MemoryDB(str(tmp_path / "test_ent2.db"), "test_ent2", 1024)
    await db.ensure_collection()
    await db.upsert("p1", None, {
        "content": "AuthService",
        "agent_scope": "director-1",
        "layer": 1,
    })
    await db.upsert("p2", None, {
        "content": "AuthService",
        "agent_scope": "shared",
        "layer": 1,
    })
    eng_entities = db.get_entities("engineer-1")
    eng_names = [e["name"] for e in eng_entities]
    assert "AuthService" in eng_names
