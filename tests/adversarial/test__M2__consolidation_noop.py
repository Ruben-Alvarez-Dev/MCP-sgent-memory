"""M2 adversarial — ISO-06: promotion & dream are hard no-ops (zero writes).

Seeds a real SQLite MemoryDB with data across layers, injects it into the
consolidation daemon module, invokes the three disabled write paths
(_promote_l2_l3, _promote_l3_l4, dream) plus the full consolidate() pipeline,
and proves:

  1. each disabled path reports status == 'disabled' (visible, not silent);
  2. ZERO rows exist with payload scope_id in ('consolidated', 'narrative',
     'dream') — the scope-global write classes are unreachable;
  3. seeded rows are neither added to nor destroyed (count stable) — the
     no-ops are inert, not destructive.

Traceability: ISO-06, M2-storage (openspec/changes/M2-storage).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.isolation]

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Redirect the daemon's module-level side effects (state dir, default
# data/memory.db) into a scratch dir BEFORE importing the server module.
_SCRATCH = tempfile.mkdtemp(prefix="m2-iso06-")
os.environ["MEMORY_SERVER_DIR"] = _SCRATCH
os.environ["DATA_DIR"] = os.path.join(_SCRATCH, "data")

from shared.memory_db import MemoryDB
from L0_to_L4_consolidation.server import main as consolidation

FORBIDDEN_SCOPE_IDS = ("consolidated", "narrative", "dream")


def _count_forbidden(d: MemoryDB) -> int:
    """Count rows whose payload scope_id is a forbidden scope-global class."""
    row = d._conn.execute(
        "SELECT COUNT(*) AS c FROM points "
        "WHERE collection=? AND json_extract(payload, '$.scope_id') IN (?, ?, ?)",
        (d.collection, *FORBIDDEN_SCOPE_IDS),
    ).fetchone()
    return row["c"]


@pytest.fixture()
async def seeded_db(tmp_path):
    d = MemoryDB(str(tmp_path / "memory.db"), collection="L0_L4_memory", embedding_dim=8)
    await d.ensure_collection()
    seed_plan = [1, 1, 1, 2, 2, 2, 3, 3, 4]  # enough data for every promotion path
    for i, layer in enumerate(seed_plan):
        await d.upsert(
            f"seed-L{layer}-{i}",
            [0.1 * (i + 1)] * 8,
            {
                "layer": layer,
                "content": f"seed memory L{layer} #{i}",
                "scope_type": "agent",
                "scope_id": f"sess-{i % 2}",
                "agent_scope": "shared",
                "importance": 0.5,
            },
        )
    yield d
    d._conn.close()


@pytest.fixture()
def daemon(seeded_db, monkeypatch):
    """Consolidation module bound to the seeded tmp MemoryDB."""
    monkeypatch.setattr(consolidation, "db", seeded_db)
    return consolidation


async def test_promote_l2_l3_is_disabled_noop(daemon, seeded_db):
    res = await daemon._promote_l2_l3({"turn_count": 0}, now=9999999999.0)
    assert res["status"] == "disabled"
    assert _count_forbidden(seeded_db) == 0


async def test_promote_l3_l4_is_disabled_noop(daemon, seeded_db):
    res = await daemon._promote_l3_l4({"turn_count": 0}, now=9999999999.0)
    assert res["status"] == "disabled"
    assert _count_forbidden(seeded_db) == 0


async def test_dream_is_disabled_noop(daemon, seeded_db):
    res = await daemon.dream()
    assert res["status"] == "disabled"
    assert _count_forbidden(seeded_db) == 0


async def test_full_pipeline_never_mints_scope_global_rows(daemon, seeded_db):
    before = await seeded_db.count()
    res = await daemon.consolidate(force=True)
    await daemon.dream()
    assert res.status == "consolidation complete"
    assert _count_forbidden(seeded_db) == 0
    assert await seeded_db.count() == before  # inert no-ops: no adds, no destruction
