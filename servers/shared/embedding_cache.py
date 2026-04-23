"""Persistent embedding cache using SQLite.

Survives restarts. Transparently wraps the in-memory LRU cache.
"""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import threading
import logging

logger = logging.getLogger(__name__)

_db_lock = threading.Lock()
_db_path: str = ""


def _get_db_path() -> str:
    global _db_path
    if not _db_path:
        base = os.getenv("MEMORY_SERVER_DIR", os.path.expanduser("~/.memory"))
        _db_path = os.path.join(base, "embedding_cache.db")
    return _db_path


def _init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            key TEXT PRIMARY KEY,
            vector TEXT NOT NULL,
            created_at REAL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emb_key ON embeddings(key)")
    conn.commit()
    conn.close()


def cache_get(text: str) -> list[float] | None:
    """Look up a cached embedding by text hash."""
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        return None
    with _db_lock:
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT vector FROM embeddings WHERE key=?", (key,)).fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
        except Exception as e:
            logger.warning("Embedding cache read error: %s", e)
    return None


def cache_set(text: str, vector: list[float]) -> None:
    """Store an embedding in the persistent cache."""
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    db_path = _get_db_path()
    with _db_lock:
        try:
            if not os.path.exists(db_path):
                _init_db(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (key, vector) VALUES (?, ?)",
                (key, json.dumps(vector)),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Embedding cache write error: %s", e)


def cache_stats() -> dict:
    """Return cache statistics."""
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        return {"size": 0}
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        conn.close()
        return {"size": count, "path": db_path}
    except Exception:
        return {"size": 0}
