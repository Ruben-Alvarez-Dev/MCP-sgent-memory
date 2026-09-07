"""STO-06 — migration from events.jsonl is idempotent (no Qdrant involved)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "scripts"))
sys.path.insert(0, str(BASE / "src"))

import migrate_to_memory_db as mig


@pytest.fixture()
def events_file(tmp_path):
    p = tmp_path / "events.jsonl"
    rows = [
        {"type": "memory", "id": "m1", "content": "alpha", "user_id": "u1", "layer": 1},
        {"type": "memory", "id": "m2", "content": "beta", "user_id": "u1", "layer": 2},
        {"type": "conversation", "id": "c1"},  # not migratable
        "not-json-would-be-skipped-by-loader",
    ]
    with p.open("w") as fh:
        for r in rows[:-1]:
            fh.write(json.dumps(r) + "\n")
        fh.write(rows[-1] + "\n")
    return p


@pytest.mark.integration
async def test_idempotent_rebuild(tmp_path, events_file, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from shared.memory_db import MemoryDB

    # run 1
    sys.argv = ["migrate", "--events", str(events_file)]
    assert mig.main() == 0
    db = MemoryDB(str(tmp_path / "data" / "memory.db"), "L0_L4_memory", 1024)
    assert await db.count() == 2

    # run 2 — idempotent: no duplicates
    sys.argv = ["migrate", "--events", str(events_file)]
    assert mig.main() == 0
    assert await db.count() == 2

    ids = {r["id"] for r in db._conn.execute("SELECT id FROM points").fetchall()}
    assert ids == {"m1", "m2"}
