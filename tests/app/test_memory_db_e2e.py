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
    """L3_facts: add → scoped search → cross-user silence → atomic delete."""
    l3 = _load("L3_facts_e2e", "src/L3_facts/server/main.py")

    async def fake_safe_embed(text: str) -> list[float]:
        return _hash(text)

    monkeypatch.setattr(l3, "safe_embed", fake_safe_embed)

    added = await l3.add_memory("Qdrant was demolished in M2", user_id="u1")
    assert added.status == "stored"

    # owner finds it; the engine never scores it for another user
    mine = await l3.search_memory("Qdrant was demolished in M2", user_id="u1", min_score=0.5)
    assert mine.count == 1
    theirs = await l3.search_memory("Qdrant was demolished in M2", user_id="u2", min_score=-1.0)
    assert theirs.count == 0

    # ownership-enforced delete: foreign user cannot delete, owner can
    assert (await l3.delete_memory(added.memory_id, user_id="u2")).status == "not_found"
    assert (await l3.delete_memory(added.memory_id, user_id="u1")).status == "deleted"
    assert (await l3.search_memory("Qdrant was demolished in M2", user_id="u1", min_score=-1.0)).count == 0


@pytest.mark.integration
async def test_scoped_retrieval_merges_own_and_shared_only(env):
    """retrieval: director-1 sees own+shared; engineer-1 sees shared only."""
    import shared.retrieval as retr

    db = retr._get_db("L0_L4_memory")
    await db.ensure_collection()
    await db.upsert("row-dir", _hash("postgres indexing strategy"),
                    {"content": "PRIVATE postgres notes for director-1", "layer": 1, "agent_scope": "director-1"})
    await db.upsert("row-shared", _hash("postgres indexing strategy"),
                    {"content": "SHARED postgres notes", "layer": 1, "agent_scope": "shared"})
    await db.upsert("row-eng", _hash("postgres indexing strategy"),
                    {"content": "PRIVATE engineer-1 notes", "layer": 1, "agent_scope": "engineer-1"})

    pack_dir = await retr.retrieve("postgres indexing strategy", agent_scope="director-1")
    contents_dir = "\n".join(s["content"] for s in pack_dir.sections)
    assert "PRIVATE postgres notes for director-1" in contents_dir   # own
    assert "SHARED postgres notes" in contents_dir                   # + shared
    assert "PRIVATE engineer-1 notes" not in contents_dir            # never siblings

    pack_eng = await retr.retrieve("postgres indexing strategy", agent_scope="engineer-1")
    contents_eng = "\n".join(s["content"] for s in pack_eng.sections)
    assert "PRIVATE engineer-1 notes" in contents_eng                # own
    assert "SHARED postgres notes" in contents_eng                   # + shared
    assert "PRIVATE postgres notes for director-1" not in contents_eng  # isolation holds
