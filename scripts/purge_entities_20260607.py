#!/usr/bin/env python3
"""Junk entity purge — repair plan 2026-06-07, Phase 3 (finding D4/D6).

Exports the full rows (entities + their entity_events + relations +
entity_milestones) as JSON to backups/entity-purge-20260607/, then
deletes them from data/entity_timeline.db. FTS triggers handle index
cleanup. Idempotent: re-running with nothing left to purge is a no-op.

Usage:
    .venv/bin/python3 scripts/purge_entities_20260607.py [--dry-run]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "entity_timeline.db"
BACKUP_DIR = Path("/Users/ruben/MCP-servers/backups/entity-purge-20260607")

# Junk entities — regex-detected garbage (D4)
JUNK_NAMES = [
    "https", "A", "---", "engra",
    ".worktrees/agent-memory_1776993728",
    "/Users/ruben/.hermes/hermes-agent",
    "/Users/ruben/Code/Jart-OS-cloned/.git",
    "current", "test-user",
    "jart-ocr-pipeline", "Jart-OCR-pipeline",
    "ocr-handwritting-bridge", "ocr-handwriting-bridge",
    "OCR-handwritting-bridge",
]

# Fake seed-data duplicates (D6) — ALL rows with these names go
SEED_NAMES = [
    "nexus-backend", "ocr-pipeline", "jartos-dashboard", "browseros-agent",
    "lead-dev", "backend-dev", "frontend-dev", "devops-sre",
]

PURGE_NAMES = JUNK_NAMES + SEED_NAMES


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    counts_before = {
        t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in ("entities", "entity_events", "relations", "entity_milestones")
    }

    ph = ",".join("?" * len(PURGE_NAMES))
    entities = [dict(r) for r in conn.execute(
        f"SELECT * FROM entities WHERE name IN ({ph})", PURGE_NAMES)]
    if not entities:
        print("Nothing to purge — all listed names are already gone.")
        return 0

    ids = [e["entity_id"] for e in entities]
    idph = ",".join("?" * len(ids))

    events = [dict(r) for r in conn.execute(
        f"SELECT * FROM entity_events WHERE entity_id IN ({idph})", ids)]
    relations = [dict(r) for r in conn.execute(
        f"SELECT * FROM relations WHERE source_id IN ({idph}) OR target_id IN ({idph})",
        ids + ids)]
    milestones = [dict(r) for r in conn.execute(
        f"SELECT * FROM entity_milestones WHERE entity_id IN ({idph})", ids)]

    print(f"To purge: {len(entities)} entities, {len(events)} events, "
          f"{len(relations)} relations, {len(milestones)} milestones")
    for e in sorted(entities, key=lambda x: x["name"]):
        print(f"  - {e['name']!r} ({e['kind']}, created {e['created_at'][:10]})")

    # 1. Export FIRST — no deletion without a backup on disk
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "db": str(DB_PATH),
        "purge_names": PURGE_NAMES,
        "entities": entities,
        "entity_events": events,
        "relations": relations,
        "entity_milestones": milestones,
    }
    out = BACKUP_DIR / "entity-purge-export.json"
    out.write_text(json.dumps(export, indent=2, default=str))
    print(f"Exported full rows to {out} ({out.stat().st_size} bytes)")

    if dry_run:
        print("DRY RUN — nothing deleted.")
        return 0

    # 2. Delete children first, then the entities. FTS triggers clean
    #    the entity_events_fts / entities_fts indexes.
    with conn:
        conn.execute(f"DELETE FROM entity_events WHERE entity_id IN ({idph})", ids)
        conn.execute(
            f"DELETE FROM relations WHERE source_id IN ({idph}) OR target_id IN ({idph})",
            ids + ids)
        conn.execute(f"DELETE FROM entity_milestones WHERE entity_id IN ({idph})", ids)
        conn.execute(f"DELETE FROM entities WHERE entity_id IN ({idph})", ids)

    counts_after = {
        t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in ("entities", "entity_events", "relations", "entity_milestones")
    }
    print("Counts before → after:")
    for t in counts_before:
        print(f"  {t}: {counts_before[t]} → {counts_after[t]}")

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"integrity_check: {integrity}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
