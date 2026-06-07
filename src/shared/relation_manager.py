"""Relationship Manager — bidirectional edges between entities.

Each relation is anchored to a specific event on each entity's timeline,
creating a "contact point" that lets you jump from one entity's story
to another at the exact moment they intersected.

Entity A ───[event a42]──── contact ────[event b17]─── Entity B
                │                                           │
          "assigned to"                              "got assigned"
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

VALID_RELATION_TYPES = {
    "assignment", "dependency", "reference", "communication",
    "ownership", "membership", "creation", "modification",
    "deployment", "observation", "partnership",
}


@dataclass
class RelationEdge:
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    source_event_id: int
    target_event_id: int
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "label": self.label,
        }


class RelationManager:
    """Thread-safe relation store backed by SQLite.

    Each relation is a directed edge from source → target,
    anchored to an event on each entity's timeline.
    Queries are symmetric: get_relations(X) returns both
    edges where X is source AND where X is target.
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
                CREATE TABLE IF NOT EXISTS relations (
                    relation_id     TEXT PRIMARY KEY,
                    source_id       TEXT NOT NULL,
                    target_id       TEXT NOT NULL,
                    relation_type   TEXT NOT NULL,
                    source_event_id INTEGER NOT NULL,
                    target_event_id INTEGER NOT NULL,
                    metadata        TEXT DEFAULT '{}',
                    created_at      TEXT NOT NULL,
                    label           TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_rel_source
                    ON relations(source_id);
                CREATE INDEX IF NOT EXISTS idx_rel_target
                    ON relations(target_id);
                CREATE INDEX IF NOT EXISTS idx_rel_type
                    ON relations(relation_type);
                CREATE INDEX IF NOT EXISTS idx_rel_both
                    ON relations(source_id, target_id);
            """)
            conn.commit()

    def connect(self, source_id: str, target_id: str,
                relation_type: str, source_event_id: int,
                target_event_id: int,
                metadata: dict | None = None,
                label: str = "") -> RelationEdge:
        """Create a bidirectional contact point between two entities."""
        if relation_type not in VALID_RELATION_TYPES:
            raise ValueError(
                f"Invalid relation type '{relation_type}'. "
                f"Valid: {sorted(VALID_RELATION_TYPES)}"
            )
        now = datetime.now(timezone.utc).isoformat()
        relation_id = str(uuid.uuid4())
        meta_json = json.dumps(metadata or {})
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    INSERT INTO relations
                        (relation_id, source_id, target_id, relation_type,
                         source_event_id, target_event_id, metadata, created_at, label)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (relation_id, source_id, target_id, relation_type,
                      source_event_id, target_event_id, meta_json, now, label))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                raise ValueError(
                    f"Relation between {source_id} and {target_id} "
                    f"already exists"
                )
            conn.close()
        logger.info(
            "Relation %s: %s ―%s→ %s (events %d→%d)",
            relation_id[:8], source_id, relation_type, target_id,
            source_event_id, target_event_id,
        )
        return self.get(relation_id)

    def connect_symmetric(self, entity_a: str, entity_b: str,
                          relation_type: str,
                          event_a: int, event_b: int,
                          label_a: str = "", label_b: str = "",
                          metadata: dict | None = None) -> tuple[RelationEdge, RelationEdge]:
        """Create a bidirectional relation (A→B and B→A) in one call."""
        ab = self.connect(entity_a, entity_b, relation_type,
                          event_a, event_b, metadata, label_a)
        ba = self.connect(entity_b, entity_a, relation_type,
                          event_b, event_a, metadata, label_b)
        return (ab, ba)

    def get(self, relation_id: str) -> Optional[RelationEdge]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM relations WHERE relation_id = ?",
                    (relation_id,)
                ).fetchone()
                return self._row_to_edge(row) if row else None
            finally:
                conn.close()

    def get_relations(self, entity_id: str) -> list[RelationEdge]:
        """All relations involving this entity (as source OR target)."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("""
                    SELECT * FROM relations
                    WHERE source_id = ? OR target_id = ?
                    ORDER BY created_at DESC
                """, (entity_id, entity_id)).fetchall()
                return [self._row_to_edge(r) for r in rows]
            finally:
                conn.close()

    def get_relations_of_type(self, entity_id: str,
                              relation_type: str) -> list[RelationEdge]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("""
                    SELECT * FROM relations
                    WHERE (source_id = ? OR target_id = ?)
                    AND relation_type = ?
                    ORDER BY created_at DESC
                """, (entity_id, entity_id, relation_type)).fetchall()
                return [self._row_to_edge(r) for r in rows]
            finally:
                conn.close()

    def get_contact_point(self, entity_a: str, entity_b: str
                          ) -> Optional[tuple[RelationEdge, RelationEdge]]:
        """Get the bidirectional edges connecting two entities, if any."""
        with self._lock:
            conn = self._connect()
            try:
                ab = conn.execute("""
                    SELECT * FROM relations
                    WHERE source_id = ? AND target_id = ?
                    LIMIT 1
                """, (entity_a, entity_b)).fetchone()
                ba = conn.execute("""
                    SELECT * FROM relations
                    WHERE source_id = ? AND target_id = ?
                    LIMIT 1
                """, (entity_b, entity_a)).fetchone()
                edges = []
                if ab:
                    edges.append(self._row_to_edge(ab))
                if ba:
                    edges.append(self._row_to_edge(ba))
                return tuple(edges) if edges else None
            finally:
                conn.close()

    def traverse(self, entity_id: str, relation_type: str | None = None,
                 max_depth: int = 2) -> list[dict]:
        """BFS traversal from an entity through relations.

        Returns list of {depth, entity_id, relation_type, source_event_id, target_event_id}.
        """
        visited = {entity_id}
        queue = [(entity_id, 0)]
        results = []

        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            edges = self.get_relations_of_type(current, relation_type) if relation_type else self.get_relations(current)
            for edge in edges:
                neighbor = edge.target_id if edge.source_id == current else edge.source_id
                if neighbor not in visited:
                    visited.add(neighbor)
                    results.append({
                        "depth": depth + 1,
                        "from": current,
                        "to": neighbor,
                        "relation_type": edge.relation_type,
                        "source_event_id": edge.source_event_id,
                        "target_event_id": edge.target_event_id,
                        "label": edge.label,
                    })
                    queue.append((neighbor, depth + 1))

        return results

    def count(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT COUNT(*) as c FROM relations").fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def delete_relation(self, relation_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM relations WHERE relation_id = ?",
                    (relation_id,)
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def delete_entity_relations(self, entity_id: str) -> int:
        """Delete all relations involving an entity."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM relations WHERE source_id = ? OR target_id = ?",
                    (entity_id, entity_id)
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> RelationEdge:
        return RelationEdge(
            relation_id=row["relation_id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=row["relation_type"],
            source_event_id=row["source_event_id"],
            target_event_id=row["target_event_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            label=row["label"] or "",
        )
