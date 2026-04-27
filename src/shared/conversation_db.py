"""SQLite + FTS5 storage for conversation threads.

Raw conversations go to SQLite (exact retrieval, full-text search).
Vectors go to Qdrant (semantic search only).
Both linked by thread_id.

Schema:
    threads   — one row per conversation thread
    messages  — one row per message (role + content)
    messages_fts — FTS5 virtual table for full-text search
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_db_lock = threading.Lock()
_db_path: str = ""


def _get_db_path() -> str:
    global _db_path
    if not _db_path:
        base = os.getenv("MEMORY_SERVER_DIR", os.path.expanduser("~/.memory"))
        data_dir = os.getenv("DATA_DIR", os.path.join(base, "data"))
        os.makedirs(data_dir, exist_ok=True)
        _db_path = os.path.join(data_dir, "conversations.db")
    return _db_path


def set_db_path(path: str) -> None:
    """Override default DB path (for testing or config injection)."""
    global _db_path
    _db_path = path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(db_path: str) -> None:
    """Create tables and indexes if they don't exist."""
    conn = _connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS threads (
            thread_id   TEXT PRIMARY KEY,
            agent_scope TEXT DEFAULT 'shared',
            summary     TEXT DEFAULT '',
            message_count INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id   TEXT NOT NULL,
            seq         INTEGER NOT NULL DEFAULT 0,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_thread
            ON messages(thread_id, seq);

        CREATE INDEX IF NOT EXISTS idx_threads_scope
            ON threads(agent_scope);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            content='messages',
            content_rowid='id'
        );

        -- Triggers to keep FTS5 in sync
        CREATE TRIGGER IF NOT EXISTS msgs_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS msgs_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.id, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS msgs_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.id, old.content);
            INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
        END;
    """)
    conn.commit()
    conn.close()


def _ensure_db() -> str:
    """Get DB path, creating the DB and running migrations if needed."""
    path = _get_db_path()
    if not os.path.exists(path):
        _init_db(path)
    else:
        # Run migrations on existing DB (e.g. agent_scope column)
        _run_migrations(path)
    return path


def _run_migrations(db_path: str) -> None:
    """Apply schema migrations that may be missing from older DBs."""
    conn = _connect(db_path)
    try:
        # Migration: agent_scope column (added after initial schema)
        try:
            conn.execute("SELECT agent_scope FROM threads LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE threads ADD COLUMN agent_scope TEXT DEFAULT 'shared'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_threads_scope ON threads(agent_scope)")
            conn.commit()
    finally:
        conn.close()


# ── Public API ──────────────────────────────────────────────────


def save_thread(thread_id: str, messages: list[dict], summary: str = "", agent_scope: str = "shared") -> dict:
    """Save or update a conversation thread with all its messages.

    Args:
        thread_id: Unique thread identifier.
        messages: List of {"role": str, "content": str, ...} dicts.
        summary: Optional summary text for the thread.
        agent_scope: Scope for multi-agent isolation. Default "shared" (visible to all).

    Returns:
        {"thread_id": str, "message_count": int, "status": str, "agent_scope": str}
    """
    now = datetime.now(timezone.utc).isoformat()
    db_path = _ensure_db()

    with _db_lock:
        conn = _connect(db_path)
        try:
            # Upsert thread metadata
            existing = conn.execute(
                "SELECT thread_id FROM threads WHERE thread_id=?", (thread_id,)
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE threads
                    SET summary=?, message_count=?, agent_scope=?, updated_at=?
                    WHERE thread_id=?
                """, (summary, len(messages), agent_scope, now, thread_id))
                # Delete old messages (replace entirely)
                conn.execute("DELETE FROM messages WHERE thread_id=?", (thread_id,))
            else:
                conn.execute("""
                    INSERT INTO threads (thread_id, agent_scope, summary, message_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (thread_id, agent_scope, summary, len(messages), now, now))

            # Insert messages
            for seq, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                conn.execute("""
                    INSERT INTO messages (thread_id, seq, role, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (thread_id, seq, str(role), str(content), now))

            conn.commit()
            return {
                "thread_id": thread_id,
                "message_count": len(messages),
                "agent_scope": agent_scope,
                "status": "saved",
            }
        except Exception as e:
            conn.rollback()
            logger.error("save_thread failed: %s", e)
            raise
        finally:
            conn.close()


def get_thread(thread_id: str) -> Optional[dict]:
    """Retrieve a full conversation thread by ID.

    Returns:
        {"thread_id", "agent_scope", "summary", "created_at", "updated_at",
         "message_count", "messages": [{"role", "content", "seq"}, ...]}
        or None if not found.
    """
    db_path = _ensure_db()
    with _db_lock:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT * FROM threads WHERE thread_id=?", (thread_id,)
            ).fetchone()
            if not row:
                return None

            msgs = conn.execute("""
                SELECT seq, role, content, created_at
                FROM messages WHERE thread_id=?
                ORDER BY seq
            """, (thread_id,)).fetchall()

            return {
                "thread_id": row["thread_id"],
                "agent_scope": row["agent_scope"],
                "summary": row["summary"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"],
                "messages": [
                    {"seq": m["seq"], "role": m["role"], "content": m["content"]}
                    for m in msgs
                ],
            }
        finally:
            conn.close()


def _fts_escape(query: str) -> str:
    """Format a user query for FTS5 MATCH.

    FTS5 treats space-separated words as implicit AND (phrase).
    We convert to OR for broader recall: "sqlite fts5" → "sqlite OR fts5".
    Special chars are stripped to avoid FTS5 syntax errors.
    """
    # Strip FTS5 special operators
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    words = [w for w in cleaned.split() if len(w) >= 2]
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return " OR ".join(words)


def search_fts(query: str, limit: int = 20, agent_scope: str | None = None) -> list[dict]:
    """Full-text search across all message content.

    Args:
        query: Search query (FTS5 syntax).
        limit: Max results.
        agent_scope: If set, filter to this scope + "shared". None = all scopes.

    Returns list of {"thread_id", "summary", "snippet", "match_type"}.
    """
    fts_query = _fts_escape(query)
    if not fts_query:
        return []
    db_path = _ensure_db()
    with _db_lock:
        conn = _connect(db_path)
        try:
            if agent_scope:
                rows = conn.execute("""
                    SELECT
                        m.thread_id,
                        t.summary,
                        snippet(messages_fts, 0, '>>>', '<<<', '...', 32) as snippet,
                        rank
                    FROM messages_fts f
                    JOIN messages m ON m.id = f.rowid
                    JOIN threads t ON t.thread_id = m.thread_id
                    WHERE messages_fts MATCH ?
                      AND (t.agent_scope = ? OR t.agent_scope = 'shared')
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, agent_scope, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT
                        m.thread_id,
                        t.summary,
                        snippet(messages_fts, 0, '>>>', '<<<', '...', 32) as snippet,
                        rank
                    FROM messages_fts f
                    JOIN messages m ON m.id = f.rowid
                    JOIN threads t ON t.thread_id = m.thread_id
                    WHERE messages_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, limit)).fetchall()

            # Deduplicate by thread_id (keep best rank)
            seen = set()
            results = []
            for r in rows:
                if r["thread_id"] not in seen:
                    seen.add(r["thread_id"])
                    results.append({
                        "thread_id": r["thread_id"],
                        "summary": r["summary"],
                        "snippet": r["snippet"],
                        "match_type": "fts",
                    })
            return results
        except Exception as e:
            logger.warning("FTS search failed: %s", e)
            return []
        finally:
            conn.close()


def list_threads(limit: int = 20, agent_scope: str | None = None) -> list[dict]:
    """List recent threads ordered by updated_at desc.

    Args:
        limit: Max threads to return.
        agent_scope: If set, filter to this scope + "shared". None = all scopes.

    Returns list of {"thread_id", "agent_scope", "summary", "message_count",
                      "created_at", "updated_at"}.
    """
    db_path = _ensure_db()
    with _db_lock:
        conn = _connect(db_path)
        try:
            if agent_scope:
                rows = conn.execute("""
                    SELECT thread_id, agent_scope, summary, message_count, created_at, updated_at
                    FROM threads
                    WHERE agent_scope = ? OR agent_scope = 'shared'
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (agent_scope, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT thread_id, agent_scope, summary, message_count, created_at, updated_at
                    FROM threads
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()

            return [dict(r) for r in rows]
        finally:
            conn.close()


def thread_count() -> int:
    """Total number of stored threads."""
    db_path = _ensure_db()
    if not os.path.exists(db_path):
        return 0
    with _db_lock:
        conn = _connect(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) as c FROM threads").fetchone()
            return row["c"] if row else 0
        finally:
            conn.close()
