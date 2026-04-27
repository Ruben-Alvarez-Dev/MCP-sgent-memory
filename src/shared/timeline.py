"""Timeline backbone — three storage strategies (A, B, C).

Timeline = ordered sequence of events across all agents.
The "columna vertebral" of the multi-agent system.

Option A: SQLite table (simple, queryable, FTS5)
Option B: Qdrant + SQLite (semantic search + ordering)
Option C: JSONL append-only (existing raw_events.jsonl)

All three share the same interface for easy swapping.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TimelineBackend(ABC):
    """Abstract interface for timeline storage."""

    @abstractmethod
    def append(self, event_type: str, agent_id: str, content: str,
               metadata: dict | None = None) -> dict:
        """Append an event to the timeline."""
        ...

    @abstractmethod
    def query(self, agent_id: str | None = None, event_type: str | None = None,
              limit: int = 50) -> list[dict]:
        """Query events from the timeline."""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text or semantic search across events."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total number of events."""
        ...


# ════════════════════════════════════════════════════════════════
# Option A: SQLite + FTS5
# ════════════════════════════════════════════════════════════════


class SQLiteTimeline(TimelineBackend):
    """Timeline stored in SQLite with FTS5 full-text search.

    Schema:
        timeline:
            id          INTEGER PRIMARY KEY AUTOINCREMENT
            timestamp   TEXT NOT NULL (ISO 8601)
            event_type  TEXT NOT NULL
            agent_id    TEXT NOT NULL
            content     TEXT NOT NULL
            metadata    TEXT (JSON)

        timeline_fts: FTS5 virtual table over content
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS timeline (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                agent_id    TEXT NOT NULL DEFAULT 'system',
                content     TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_timeline_ts
                ON timeline(timestamp);
            CREATE INDEX IF NOT EXISTS idx_timeline_agent
                ON timeline(agent_id);
            CREATE INDEX IF NOT EXISTS idx_timeline_type
                ON timeline(event_type);

            CREATE VIRTUAL TABLE IF NOT EXISTS timeline_fts USING fts5(
                content,
                content='timeline',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS tl_ai AFTER INSERT ON timeline BEGIN
                INSERT INTO timeline_fts(rowid, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS tl_ad AFTER DELETE ON timeline BEGIN
                INSERT INTO timeline_fts(timeline_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
            END;
        """)
        conn.commit()
        conn.close()

    def append(self, event_type: str, agent_id: str = "system",
               content: str = "", metadata: dict | None = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("""
                    INSERT INTO timeline (timestamp, event_type, agent_id, content, metadata)
                    VALUES (?, ?, ?, ?, ?)
                """, (now, event_type, agent_id, content, meta_json))
                conn.commit()
                return {"id": cur.lastrowid, "timestamp": now, "status": "appended"}
            finally:
                conn.close()

    def query(self, agent_id: str | None = None, event_type: str | None = None,
              limit: int = 50) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                sql = "SELECT * FROM timeline WHERE 1=1"
                params = []
                if agent_id:
                    sql += " AND agent_id = ?"
                    params.append(agent_id)
                if event_type:
                    sql += " AND event_type = ?"
                    params.append(event_type)
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def search(self, query: str, limit: int = 20) -> list[dict]:
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
                    SELECT t.*, snippet(timeline_fts, 0, '>>>', '<<<', '...', 32) as snippet
                    FROM timeline_fts f
                    JOIN timeline t ON t.id = f.rowid
                    WHERE timeline_fts MATCH ?
                    ORDER BY rank LIMIT ?
                """, (fts_query, limit)).fetchall()
                return [dict(r) for r in rows]
            except Exception as e:
                logger.warning("Timeline FTS search failed: %s", e)
                return []
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT COUNT(*) as c FROM timeline").fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()


# ════════════════════════════════════════════════════════════════
# Option B: Qdrant + SQLite (semantic search + ordering)
# ════════════════════════════════════════════════════════════════


class HybridTimeline(TimelineBackend):
    """Timeline with Qdrant for semantic search + SQLite for ordering.

    SQLite stores the ordered timeline (timestamp, metadata).
    Qdrant stores vectors for semantic search.
    Both linked by event ID.
    """

    def __init__(self, db_path: str, qdrant_url: str, embedding_dim: int = 1024):
        self._sqlite = SQLiteTimeline(db_path)
        self._qdrant_url = qdrant_url
        self._embedding_dim = embedding_dim
        self._collection = "timeline"

    async def _get_qdrant(self):
        from shared.qdrant_client import QdrantClient
        client = QdrantClient(self._qdrant_url, self._collection, self._embedding_dim)
        await client.ensure_collection(sparse=False)
        return client

    async def _embed(self, text: str) -> list[float]:
        from shared.embedding import safe_embed
        return await safe_embed(text)

    def append(self, event_type: str, agent_id: str = "system",
               content: str = "", metadata: dict | None = None) -> dict:
        # SQLite append (sync)
        result = self._sqlite.append(event_type, agent_id, content, metadata)
        # Qdrant append (needs async wrapper)
        # For sync interface, we skip Qdrant — caller should use async version
        return result

    async def append_async(self, event_type: str, agent_id: str = "system",
                           content: str = "", metadata: dict | None = None) -> dict:
        """Append with both SQLite and Qdrant."""
        result = self._sqlite.append(event_type, agent_id, content, metadata)
        event_id = str(result["id"])
        try:
            qdrant = await self._get_qdrant()
            vec = await self._embed(content)
            await qdrant.upsert(event_id, vec, {
                "event_id": event_id,
                "event_type": event_type,
                "agent_id": agent_id,
                "timestamp": result["timestamp"],
            })
        except Exception as e:
            logger.warning("Qdrant timeline append failed: %s", e)
        return result

    def query(self, agent_id: str | None = None, event_type: str | None = None,
              limit: int = 50) -> list[dict]:
        return self._sqlite.query(agent_id, event_type, limit)

    def search(self, query: str, limit: int = 20) -> list[dict]:
        # Fallback to FTS5 (semantic search needs async)
        return self._sqlite.search(query, limit)

    async def search_semantic(self, query: str, limit: int = 20) -> list[dict]:
        """Semantic search via Qdrant."""
        try:
            qdrant = await self._get_qdrant()
            vec = await self._embed(query)
            results = await qdrant.search(vec, limit=limit, score_threshold=0.3)
            return [r.get("payload", {}) for r in results]
        except Exception as e:
            logger.warning("Qdrant timeline search failed: %s", e)
            return self._sqlite.search(query, limit)

    def count(self) -> int:
        return self._sqlite.count()


# ════════════════════════════════════════════════════════════════
# Option C: JSONL append-only
# ════════════════════════════════════════════════════════════════


class JSONLTimeline(TimelineBackend):
    """Timeline stored as append-only JSONL file.

    Uses existing raw_events.jsonl or a dedicated timeline.jsonl.
    Simple, durable, but not efficiently queryable.
    """

    def __init__(self, jsonl_path: str):
        self._path = jsonl_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(jsonl_path) or ".", exist_ok=True)

    def append(self, event_type: str, agent_id: str = "system",
               content: str = "", metadata: dict | None = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        event = {
            "timestamp": now,
            "event_type": event_type,
            "agent_id": agent_id,
            "content": content,
            "metadata": metadata or {},
        }
        with self._lock:
            with open(self._path, "a") as f:
                f.write(json.dumps(event) + "\n")
        return {"timestamp": now, "status": "appended"}

    def query(self, agent_id: str | None = None, event_type: str | None = None,
              limit: int = 50) -> list[dict]:
        events = self._read_all()
        if agent_id:
            events = [e for e in events if e.get("agent_id") == agent_id]
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        return events[-limit:]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        query_lower = query.lower()
        events = self._read_all()
        matches = [e for e in events if query_lower in e.get("content", "").lower()]
        return matches[-limit:]

    def count(self) -> int:
        if not os.path.exists(self._path):
            return 0
        with self._lock:
            with open(self._path) as f:
                return sum(1 for _ in f)

    def _read_all(self) -> list[dict]:
        if not os.path.exists(self._path):
            return []
        with self._lock:
            events = []
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            return events


# ════════════════════════════════════════════════════════════════
# Factory
# ════════════════════════════════════════════════════════════════


def create_timeline(backend: str = "sqlite", **kwargs) -> TimelineBackend:
    """Create a timeline backend.

    Args:
        backend: "sqlite" (A), "hybrid" (B), or "jsonl" (C)
        **kwargs: Backend-specific args (db_path, qdrant_url, jsonl_path)
    """
    if backend == "sqlite":
        db_path = kwargs.get("db_path", "data/timeline.db")
        return SQLiteTimeline(db_path)
    elif backend == "hybrid":
        db_path = kwargs.get("db_path", "data/timeline.db")
        qdrant_url = kwargs.get("qdrant_url", "http://127.0.0.1:6333")
        return HybridTimeline(db_path, qdrant_url)
    elif backend == "jsonl":
        jsonl_path = kwargs.get("jsonl_path", "data/timeline.jsonl")
        return JSONLTimeline(jsonl_path)
    else:
        raise ValueError(f"Unknown timeline backend: {backend}")
