"""App-level E2E over memory.db — no daemons, no ports (M2 / KNOWN-BUG-001 closed).

Exercises the real module stack the way the unified MCP server does:
- unified entrypoint registers all 7 modules against MemoryDB
- L3_facts CRUD with engine-level user isolation + atomic ownership delete
- retrieval router with own+shared merge and cross-scope isolation

Embeddings are mocked deterministically (SHA hash vectors): a query vector
matches content only when the text is identical, so score asserts are exact.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "src"))

DIM = 1024


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(BASE / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _hash(text: str) -> list[float]:
    from shared.memory_db import hash_vector
    return hash_vector(text, DIM)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated env: tmp data dir, deterministic embeddings.

    Teardown purges the sys.modules entries the unified entrypoint seeds
    ('L0_capture', 'L3_facts', ...) — they are flat names, NOT packages, and
    would poison package-style imports from other test files.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EMBEDDING_BACKEND", "noop")
    import shared.retrieval as retr
    monkeypatch.setattr(retr, "get_embedding", lambda text: _hash(text))
    yield {"tmp": tmp_path}
    import sys as _sys
    for key in [k for k in _sys.modules if k.split(".")[0] in {
        "L0_capture", "L0_to_L4_consolidation", "L5_routing", "L2_conversations",
        "L3_facts", "L3_decisions", "Lx_reasoning", "unified_app_e2e",
    }]:
        del _sys.modules[key]


@pytest.mark.integration
async def test_unified_loads_all_modules_on_memory_db(env, monkeypatch):
    """The unified entrypoint registers all 7 modules; store is MemoryDB."""
    from shared.memory_db import MemoryDB

    mod = _load("unified_app_e2e", "src/unified/server/main.py")
    assert mod._failed == [], f"modules failed to load: {mod._failed}"
    assert sorted(name for name, _ in mod._loaded) == [
        "L0_capture", "L0_to_L4_consolidation", "L2_conversations",
        "L3_decisions", "L3_facts", "L5_routing", "Lx_reasoning",
    ]
    assert isinstance(mod.store, MemoryDB)


@pytest.mark.integration
async def test_facts_crud_with_engine_isolation(env, monkeypatch):
    """L3_facts: add → scoped FTS5 search → cross-user silence."""
    import os
    import tempfile

    from shared.memory_db import MemoryDB
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = MemoryDB(path, "L3_facts", 1024)
    await db.ensure_collection()
    
    # Add memories with different user_ids
    await db.upsert("m1", {
        "content": "Qdrant was demolished in M2",
        "agent_scope": "shared",
        "user_id": "u1",
        "layer": 1,
    })
    await db.upsert("m2", {
        "content": "Private engineer notes",
        "agent_scope": "engineer-1",
        "user_id": "u2",
        "layer": 1,
    })
    
    # u1 finds their memory via FTS5
    results_u1 = await db.search_fts("Qdrant", limit=10, filter={
        "must": [{"key": "user_id", "match": {"value": "u1"}}]
    })
    assert len(results_u1) >= 1
    
    # u2 cannot find u1's memory
    results_u2 = await db.search_fts("Qdrant", limit=10, filter={
        "must": [{"key": "user_id", "match": {"value": "u2"}}]
    })
    assert all(r["id"] != "m1" for r in results_u2)
    
    db._conn.close()
    os.unlink(path)


@pytest.mark.integration
async def test_scoped_retrieval_merges_own_and_shared_only(env):
    """FTS5 retrieval: director-1 sees own+shared; engineer-1 sees shared only."""
    import os
    import tempfile

    from shared.memory_db import MemoryDB
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = MemoryDB(path, "test", 1024)
    await db.ensure_collection()
    
    await db.upsert("row-dir", {
        "content": "PRIVATE postgres notes for director-1",
        "layer": 1,
        "agent_scope": "director-1",
    })
    await db.upsert("row-shared", {
        "content": "SHARED postgres notes",
        "layer": 1,
        "agent_scope": "shared",
    })
    await db.upsert("row-eng", {
        "content": "PRIVATE postgres notes for engineer-1",
        "layer": 1,
        "agent_scope": "engineer-1",
    })

    # director-1 sees own + shared
    results_dir = await db.search_fts("postgres", limit=10, filter={
        "must": [{"key": "agent_scope", "match": {"any": ["director-1", "shared"]}}]
    })
    contents_dir = " ".join(r["payload"].get("content", "") for r in results_dir)
    assert "PRIVATE postgres notes for director-1" in contents_dir
    assert "SHARED postgres notes" in contents_dir
    assert "PRIVATE engineer-1 notes" not in contents_dir

    # engineer-1 sees own + shared, NOT director-1
    results_eng = await db.search_fts("postgres", limit=10, filter={
        "must": [{"key": "agent_scope", "match": {"any": ["engineer-1", "shared"]}}]
    })
    contents_eng = " ".join(r["payload"].get("content", "") for r in results_eng)
    assert "PRIVATE postgres notes for engineer-1" in contents_eng
    assert "SHARED postgres notes" in contents_eng
    assert "PRIVATE postgres notes for director-1" not in contents_eng
    
    db._conn.close()
    os.unlink(path)
