"""Entity Registry — CRUD + lifecycle for timeline entities.

Each entity has a timeline of events (see entity_timeline.py).
Entities connect via bidirectional relations (see relation_manager.py).

The registry is the "phone book" — it knows who exists, their state,
and where their timeline lives.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EntityNode:
    entity_id: str
    name: str
    kind: str
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "summary": self.summary,
        }


VALID_STATUSES = {"active", "dormant", "archived", "dead", "candidate_for_cleanup"}
VALID_KINDS = {"project", "user", "agent", "document", "concept", "task", "system", "external"}


class EntityRegistry:
    """Thread-safe entity registry backed by SQLite."""

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
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id   TEXT PRIMARY KEY,
                    name        TEXT NOT NULL UNIQUE,
                    kind        TEXT NOT NULL DEFAULT 'concept',
                    status      TEXT NOT NULL DEFAULT 'active',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    metadata    TEXT DEFAULT '{}',
                    summary     TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_entities_kind
                    ON entities(kind);
                CREATE INDEX IF NOT EXISTS idx_entities_status
                    ON entities(status);
                CREATE INDEX IF NOT EXISTS idx_entities_name
                    ON entities(name);
                CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                    name, summary,
                    content='entities',
                    content_rowid='rowid'
                );
                CREATE TRIGGER IF NOT EXISTS ent_ai AFTER INSERT ON entities BEGIN
                    INSERT INTO entities_fts(rowid, name, summary)
                    VALUES (new.rowid, new.name, new.summary);
                END;
                CREATE TRIGGER IF NOT EXISTS ent_ad AFTER DELETE ON entities BEGIN
                    INSERT INTO entities_fts(entities_fts, rowid, name, summary)
                    VALUES('delete', old.rowid, old.name, old.summary);
                END;
                CREATE TRIGGER IF NOT EXISTS ent_au AFTER UPDATE ON entities BEGIN
                    INSERT INTO entities_fts(entities_fts, rowid, name, summary)
                    VALUES('delete', old.rowid, old.name, old.summary);
                    INSERT INTO entities_fts(rowid, name, summary)
                    VALUES (new.rowid, new.name, new.summary);
                END;
            """)
            conn.commit()

    def register(self, name: str, kind: str = "concept",
                 metadata: dict | None = None,
                 summary: str = "") -> EntityNode:
        if kind not in VALID_KINDS:
            raise ValueError(f"Invalid kind '{kind}'. Valid: {sorted(VALID_KINDS)}")
        now = datetime.now(timezone.utc).isoformat()
        entity_id = str(uuid.uuid4())
        meta_json = json.dumps(metadata or {})
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute("SELECT entity_id FROM entities WHERE name = ?",
                                        (name,)).fetchone()
                if existing:
                    conn.close()
                    raise ValueError(f"Entity '{name}' already exists (id={existing['entity_id']})")
                conn.execute("""
                    INSERT INTO entities (entity_id, name, kind, status, created_at, updated_at, metadata, summary)
                    VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
                """, (entity_id, name, kind, now, now, meta_json, summary))
                conn.commit()
            except sqlite3.IntegrityError as e:
                conn.close()
                raise ValueError(f"Entity '{name}' already exists (integrity error)")
            conn.close()
        logger.info("Entity registered: %s (%s) as %s", entity_id, name, kind)
        return self.get(entity_id)

    def get(self, entity_id: str) -> Optional[EntityNode]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM entities WHERE entity_id = ?",
                                   (entity_id,)).fetchone()
                return self._row_to_entity(row) if row else None
            finally:
                conn.close()

    def get_by_name(self, name: str) -> Optional[EntityNode]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM entities WHERE name = ?",
                                   (name,)).fetchone()
                return self._row_to_entity(row) if row else None
            finally:
                conn.close()

    def update_status(self, entity_id: str, new_status: str) -> bool:
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{new_status}'. Valid: {sorted(VALID_STATUSES)}")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("""
                    UPDATE entities SET status = ?, updated_at = ?
                    WHERE entity_id = ?
                """, (new_status, now, entity_id))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def update_metadata(self, entity_id: str, metadata: dict) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata)
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("""
                    UPDATE entities SET metadata = ?, updated_at = ?
                    WHERE entity_id = ?
                """, (meta_json, now, entity_id))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def update_summary(self, entity_id: str, summary: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("""
                    UPDATE entities SET summary = ?, updated_at = ?
                    WHERE entity_id = ?
                """, (summary, now, entity_id))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def list_by_kind(self, kind: str, status: str | None = None) -> list[EntityNode]:
        with self._lock:
            conn = self._connect()
            try:
                sql = "SELECT * FROM entities WHERE kind = ?"
                params = [kind]
                if status:
                    sql += " AND status = ?"
                    params.append(status)
                sql += " ORDER BY updated_at DESC"
                rows = conn.execute(sql, params).fetchall()
                return [self._row_to_entity(r) for r in rows]
            finally:
                conn.close()

    def search(self, query: str, limit: int = 20) -> list[EntityNode]:
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
                    SELECT e.* FROM entities_fts f
                    JOIN entities e ON e.rowid = f.rowid
                    WHERE entities_fts MATCH ?
                    ORDER BY rank LIMIT ?
                """, (fts_query, limit)).fetchall()
                return [self._row_to_entity(r) for r in rows]
            except Exception as e:
                logger.warning("Entity FTS search failed: %s", e)
                return []
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT COUNT(*) as c FROM entities").fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def list_recent(self, limit: int = 20) -> list[EntityNode]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("""
                    SELECT * FROM entities
                    ORDER BY updated_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [self._row_to_entity(r) for r in rows]
            finally:
                conn.close()

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> EntityNode:
        return EntityNode(
            entity_id=row["entity_id"],
            name=row["name"],
            kind=row["kind"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            summary=row["summary"] or "",
        )
