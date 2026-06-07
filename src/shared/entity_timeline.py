"""Entity Timeline — per-entity ordered events.

Each entity has its own chronological timeline.
Events are beads on a string: ordered, immutable, traceable.

Contact points (relations) are anchored to specific events,
so you can jump from one entity's timeline to another at
the exact moment they intersected.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class EntityTimeline:
    """Thread-safe per-entity timeline backed by SQLite.

    Schema:
        entity_events:
            id          INTEGER PRIMARY KEY AUTOINCREMENT
            entity_id   TEXT NOT NULL (FK to entities)
            timestamp   TEXT NOT NULL (ISO 8601)
            event_type  TEXT NOT NULL
            content     TEXT NOT NULL
            metadata    TEXT (JSON)
            source_event_id TEXT (link back to raw_events.jsonl if any)

        entity_events_fts: FTS5 virtual table over content

        entity_milestones:
            id          INTEGER PRIMARY KEY AUTOINCREMENT
            entity_id   TEXT NOT NULL
            milestone   TEXT NOT NULL ('created' | 'first_contact' | 'evolved' | 'archived' | 'revived')
            event_id    INTEGER NOT NULL (FK to entity_events)
            timestamp   TEXT NOT NULL
            description TEXT
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS entity_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id       TEXT NOT NULL,
                    timestamp       TEXT NOT NULL,
                    event_type      TEXT NOT NULL,
                    content         TEXT NOT NULL DEFAULT '',
                    metadata        TEXT DEFAULT '{}',
                    source_event_id TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_ee_entity
                    ON entity_events(entity_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_ee_type
                    ON entity_events(entity_id, event_type);

                CREATE VIRTUAL TABLE IF NOT EXISTS entity_events_fts USING fts5(
                    content,
                    content='entity_events',
                    content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS ee_ai AFTER INSERT ON entity_events BEGIN
                    INSERT INTO entity_events_fts(rowid, content)
                    VALUES (new.id, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS ee_ad AFTER DELETE ON entity_events BEGIN
                    INSERT INTO entity_events_fts(entity_events_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
                END;

                CREATE TABLE IF NOT EXISTS entity_milestones (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id   TEXT NOT NULL,
                    milestone   TEXT NOT NULL,
                    event_id    INTEGER NOT NULL,
                    timestamp   TEXT NOT NULL,
                    description TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_em_entity
                    ON entity_milestones(entity_id);
            """)
            conn.commit()

    def append(self, entity_id: str, event_type: str,
               content: str = "", metadata: dict | None = None,
               source_event_id: str = "") -> dict:
        """Append an event to an entity's timeline. Returns the event."""
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("""
                    INSERT INTO entity_events
                        (entity_id, timestamp, event_type, content, metadata, source_event_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (entity_id, now, event_type, content, meta_json, source_event_id))
                event_id = cur.lastrowid
                conn.commit()
                return {
                    "id": event_id,
                    "entity_id": entity_id,
                    "timestamp": now,
                    "event_type": event_type,
                    "content": content,
                    "metadata": metadata or {},
                    "source_event_id": source_event_id,
                }
            finally:
                conn.close()

    def append_milestone(self, entity_id: str, milestone: str,
                         event_id: int, description: str = "") -> bool:
        """Mark a lifecycle milestone for an entity, anchored to a specific event."""
        valid = {"created", "first_contact", "evolved", "archived", "revived"}
        if milestone not in valid:
            raise ValueError(f"Invalid milestone '{milestone}'. Valid: {sorted(valid)}")
        with self._lock:
            conn = self._connect()
            try:
                event = conn.execute(
                    "SELECT timestamp FROM entity_events WHERE id = ?",
                    (event_id,)
                ).fetchone()
                if not event:
                    return False
                conn.execute("""
                    INSERT INTO entity_milestones
                        (entity_id, milestone, event_id, timestamp, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (entity_id, milestone, event_id, event["timestamp"], description))
                conn.commit()
                return True
            finally:
                conn.close()

    def query(self, entity_id: str, event_type: str | None = None,
              from_ts: str | None = None, to_ts: str | None = None,
              limit: int = 50, offset: int = 0) -> list[dict]:
        """Query events from an entity's timeline, most recent first."""
        with self._lock:
            conn = self._connect()
            try:
                sql = "SELECT * FROM entity_events WHERE entity_id = ?"
                params = [entity_id]
                if event_type:
                    sql += " AND event_type = ?"
                    params.append(event_type)
                if from_ts:
                    sql += " AND timestamp >= ?"
                    params.append(from_ts)
                if to_ts:
                    sql += " AND timestamp <= ?"
                    params.append(to_ts)
                sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def query_chronological(self, entity_id: str, event_type: str | None = None,
                            limit: int = 50) -> list[dict]:
        """Same as query but oldest first (for reading the story)."""
        with self._lock:
            conn = self._connect()
            try:
                sql = "SELECT * FROM entity_events WHERE entity_id = ?"
                params = [entity_id]
                if event_type:
                    sql += " AND event_type = ?"
                    params.append(event_type)
                sql += " ORDER BY timestamp ASC LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_epochs(self, entity_id: str) -> list[dict]:
        """Return timeline grouped into meaningful chunks via milestones + time gaps."""
        with self._lock:
            conn = self._connect()
            try:
                milestones = conn.execute("""
                    SELECT * FROM entity_milestones
                    WHERE entity_id = ?
                    ORDER BY timestamp ASC
                """, (entity_id,)).fetchall()

                events = conn.execute("""
                    SELECT timestamp FROM entity_events
                    WHERE entity_id = ?
                    ORDER BY timestamp ASC
                """, (entity_id,)).fetchall()
                conn.close()

                if not events:
                    return []

                epochs = []
                for i, m in enumerate(milestones):
                    desc = m["description"] or m["milestone"]
                    epochs.append({
                        "milestone": m["milestone"],
                        "description": desc,
                        "timestamp": m["timestamp"],
                        "event_id": m["event_id"],
                        "index": i,
                    })

                return epochs
            finally:
                conn.close()

    def get_surrounding(self, entity_id: str, event_id: int,
                        window: int = 5) -> list[dict]:
        """Get N events before and after a specific event (for context)."""
        with self._lock:
            conn = self._connect()
            try:
                target = conn.execute(
                    "SELECT timestamp FROM entity_events WHERE id = ? AND entity_id = ?",
                    (event_id, entity_id)
                ).fetchone()
                if not target:
                    return []
                before = conn.execute("""
                    SELECT * FROM entity_events
                    WHERE entity_id = ? AND id < ?
                    ORDER BY id DESC LIMIT ?
                """, (entity_id, event_id, window)).fetchall()
                around = conn.execute("""
                    SELECT * FROM entity_events
                    WHERE entity_id = ? AND id >= ?
                    ORDER BY id ASC LIMIT ?
                """, (entity_id, event_id, window + 1)).fetchall()
                result = list(before)[::-1] + list(around)
                return [dict(r) for r in result]
            finally:
                conn.close()

    def search(self, entity_id: str, query: str, limit: int = 20) -> list[dict]:
        """FTS5 search within a single entity's timeline."""
        import re
        cleaned = re.sub(r'[^\w\s]', ' ', query)
        words = [w for w in cleaned.split() if len(w) >= 2]
        if not words:
            return []
        fts_query = " OR ".join(words) if len(words) > 1 else words[0]
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("""
                    SELECT e.*, snippet(entity_events_fts, 0, '>>>', '<<<', '...', 32) as snippet
                    FROM entity_events_fts f
                    JOIN entity_events e ON e.id = f.rowid
                    WHERE entity_events_fts MATCH ? AND e.entity_id = ?
                    ORDER BY rank LIMIT ?
                """, (fts_query, entity_id, limit)).fetchall()
                return [dict(r) for r in rows]
            except Exception as e:
                logger.warning("Entity timeline FTS search failed: %s", e)
                return []
            finally:
                conn.close()

    def count_events(self, entity_id: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM entity_events WHERE entity_id = ?",
                    (entity_id,)
                ).fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def count_entities(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(DISTINCT entity_id) as c FROM entity_events"
                ).fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def delete_entity_events(self, entity_id: str) -> int:
        """Remove all events for an entity. Returns count deleted."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM entity_milestones WHERE entity_id = ?",
                             (entity_id,))
                cur = conn.execute("DELETE FROM entity_events WHERE entity_id = ?",
                                   (entity_id,))
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()
