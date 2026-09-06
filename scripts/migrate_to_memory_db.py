#!/usr/bin/env python3
"""Migrate L0 events.jsonl → data/memory.db (STO-06, post-Qdrant rebuild).

Reads the JSONL audit log (source of truth for ingestion, STO-03) and rebuilds
the dense-memory `points` table WITHOUT ever contacting Qdrant (it is demolished
in M2). Idempotent: rows already present by (collection, id) are skipped.

Usage:
    .venv/bin/python scripts/migrate_to_memory_db.py [--dry-run] [--events PATH]

Event shapes supported (subset of L0_capture ingestion history):
- {"type": "memory", "id": ..., "content": ..., "user_id": ..., "layer": ..., "created_at": ...}
- {"type": "conversation", ...}            → skipped (conversations live via conversation_db)
- anything else                            → counted as skipped
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "src"))

from shared.memory_db import MemoryDB, default_db_path


def load_events(path: Path) -> list[dict]:
    events = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"WARN line {lineno}: invalid JSON, skipped")
    return events


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    ap.add_argument(
        "--events",
        default=os.getenv("EVENTS_JSONL", str(Path.home() / ".memory" / "data" / "events.jsonl")),
    )
    args = ap.parse_args()

    events_path = Path(args.events)
    if not events_path.exists():
        print(f"No events file at {events_path} — nothing to migrate (fresh install).")
        return 0

    events = load_events(events_path)
    migratable = [e for e in events if isinstance(e, dict) and e.get("type") == "memory"]
    print(f"{len(events)} events, {len(migratable)} migratable memories")

    if args.dry_run:
        return 0

    db = MemoryDB(default_db_path(), "L0_L4_memory", int(os.getenv("EMBEDDING_DIM", "1024")))
    db._ensure_schema()

    migrated = skipped = 0
    for e in migratable:
        pid = str(e.get("id") or "")
        if not pid:
            skipped += 1
            continue
        row = db._conn.execute(
            "SELECT 1 FROM points WHERE collection=? AND id=?", (db.collection, pid)
        ).fetchone()
        if row is not None:  # idempotent (admin check: no scope semantics here)
            skipped += 1
            continue
        # sync internal write (script context — no event loop)
        db._upsert_one(
            pid,
            None,  # vector: re-embed later or hash-fallback at query time (STO-05)
            {
                "content": e.get("content", ""),
                "user_id": e.get("user_id", "default"),
                "agent_scope": e.get("agent_scope", "shared"),
                "layer": e.get("layer"),
                "created_at": e.get("created_at"),
                "migrated_from": "events.jsonl",
            },
            None,
        )
        migrated += 1

    print(f"migrated={migrated} skipped(already-present/invalid)={skipped}")
    print(f"memory.db at {db.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
