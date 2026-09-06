"""Unified single-file memory store (M2-storage).

Replaces Qdrant HTTP daemon with SQLite (stdlib only). One file, `memory.db`,
hosts dense memory points, conversations and facts. All scope/user filtering is
enforced ENGINE-LEVEL (SQL WHERE with bound parameters) — Python post-filtering
of fetched rows is forbidden by ISO-05.

Interface parity with the old QdrantClient so MCP servers migrate by changing
the constructor + import and DELETING their post-filters.

Hard guarantees (openspec/changes/M2-storage):
- STO-05: never persists zero-vectors; missing/failed embeddings -> vector=NULL
  + payload["embedded"]=false; scored at query time against a deterministic
  SHA-256 hash-vector marked score_source="hash".
- ISO-11: filter keys validated ^[a-z_][a-z0-9_]*$, values always bound params.
- ISO-12: writes without agent_scope default to payload["agent_scope"]="shared".
- Fail-closed: search/scroll REQUIRE a filter (ScopeRequiredError otherwise).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import struct
import threading
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 2
_FILTER_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_RESERVED_PAYLOAD_KEYS = frozenset({"id", "vector", "sparse_vectors", "payload"})
_PAYLOAD_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class ScopeRequiredError(ValueError):
    """Raised when a read path is invoked without an explicit engine filter."""


# ISO-11: only these payload fields are engine-filterable. Everything else
# must go through explicit APIs — prevents filter-key injection by design.
_ENGINE_FILTER_COLUMNS = {
    "agent_scope": "agent_scope",
    "user_id": "user_id",
}


def default_db_path() -> str:
    """Resolve data/memory.db honoring MEMORY_SERVER_DIR/DATA_DIR envs."""
    base = os.getenv("MEMORY_SERVER_DIR", os.path.expanduser("~/.memory"))
    data_dir = os.getenv("DATA_DIR", os.path.join(base, "data"))
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "memory.db")


def _validate_payload_keys(payload: dict[str, Any], point_id: str = "?") -> None:
    for key in payload:
        if key in _RESERVED_PAYLOAD_KEYS:
            raise ValueError(f"Payload key '{key}' is reserved (point {point_id})")
        if not _PAYLOAD_KEY_RE.match(key):
            raise ValueError(f"Invalid payload key '{key}' (point {point_id})")


def hash_vector(content: str, dim: int) -> list[float]:
    """Deterministic pseudo-vector from content (SHA-256 stream, normalized).

    Used ONLY at query time for rows whose embedding failed (vector IS NULL).
    Never persisted — replaces the poisoned zero-vector fallback (STO-05).
    """
    vec: list[float] = []
    counter = 0
    while len(vec) < dim:
        digest = hashlib.sha256(f"{content}#{counter}".encode()).digest()
        for i in range(0, len(digest) - 1, 2):
            if len(vec) >= dim:
                break
            val = int.from_bytes(digest[i : i + 2], "big") / 65535.0
            vec.append(val * 2.0 - 1.0)
        counter += 1
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class MemoryDB:
    """Async facade over a per-collection slice of the shared memory.db file."""

    def __init__(
        self,
        db_path: str | None = None,
        collection: str = "L0_L4_memory",
        embedding_dim: int = 1024,
    ):
        self.db_path = db_path or default_db_path()
        self.collection = collection
        self.embedding_dim = embedding_dim
        self._lock = threading.RLock()
        self._write_lock = asyncio.Lock()
        self._conn = self._connect()

    # ── Connection / schema ────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS points(
                  id TEXT NOT NULL,
                  collection TEXT NOT NULL,
                  vector BLOB,
                  payload TEXT NOT NULL,
                  agent_scope TEXT NOT NULL DEFAULT 'shared',
                  user_id TEXT,
                  sparse_json TEXT,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY(collection, id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_points_scope
                ON points(collection, agent_scope, user_id)
                """
            )
            self._conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")

    async def ensure_collection(self, sparse: bool = True) -> None:
        """Create backing table if missing. `sparse` kept for interface parity."""
        async with self._write_lock:
            await asyncio.to_thread(self._ensure_schema)

    async def health(self) -> bool:
        try:
            return await asyncio.to_thread(
                lambda: self._conn.execute("SELECT 1").fetchone() is not None
            )
        except Exception:
            return False

    async def close(self) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self._conn.close)

    def with_collection(self, collection: str) -> "MemoryDB":
        """Create a new client targeting a different collection (parity)."""
        return MemoryDB(self.db_path, collection, self.embedding_dim)

    # ── Filter translation (ISO-11) ────────────────────────────

    @staticmethod
    def _translate_filter(filter_: Optional[dict]) -> tuple[str, list[Any]]:
        """Qdrant-style {"must":[{"key":k,"match":{"value":v}}]} -> safe SQL.

        Keys MUST be engine columns (allowlist), values ALWAYS bound as
        parameters. Fail-closed on malformed filters (None values, exotic
        structures, unknown keys).
        """
        if not filter_:
            raise ScopeRequiredError(
                "MemoryDB requires an explicit filter on every read "
                "(fail-closed; use agent_scope/user_id conditions)"
            )
        clauses: list[str] = []
        params: list[Any] = []
        must = filter_.get("must")
        if not isinstance(must, list) or not must:
            raise ValueError("filter.must must be a non-empty list")
        for cond in must:
            if not isinstance(cond, dict):
                raise ValueError("filter condition must be a dict")
            key = cond.get("key")
            match = cond.get("match")
            value = match.get("value") if isinstance(match, dict) else None
            if not isinstance(key, str) or key not in _ENGINE_FILTER_COLUMNS:
                raise ValueError(f"filter key not engine-filterable: {key!r}")
            if value is None or isinstance(value, (dict, list)):
                raise ValueError(f"Filter value for '{key}' must be scalar")
            clauses.append(f"{_ENGINE_FILTER_COLUMNS[key]} = ?")
            params.append(value)
        if not clauses:
            raise ScopeRequiredError("Empty filter — refuse unfiltered scan")
        return " AND ".join(clauses), params

    # ── Point operations ───────────────────────────────────────

    @staticmethod
    def _pack_vector(vector: Optional[list[float]]) -> Optional[bytes]:
        if not vector:
            return None
        if all(v == 0.0 for v in vector):
            return None  # STO-05: zero-vectors are never persisted
        if len(vector) == 0:
            return None
        return struct.pack(f"{len(vector)}f", *vector)

    @staticmethod
    def _unpack_vector(blob: Optional[bytes]) -> Optional[list[float]]:
        if not blob:
            return None
        n = len(blob) // 4
        return list(struct.unpack(f"{n}f", blob))

    def _prepare_row(self, point_id: str, vector, payload, sparse):
        if point_id is None or not isinstance(point_id, str) or not point_id.strip():
            raise ValueError(f"Invalid point id: {point_id!r}")
        _validate_payload_keys(payload, point_id)
        payload = dict(payload)
        if "agent_scope" not in payload:  # ISO-12: no global-implicit default
            payload["agent_scope"] = "shared"
            logger.info("upsert %s: missing agent_scope -> defaulted to 'shared'", point_id)
        payload["schema_version"] = payload.get("schema_version", "1.0")
        blob = self._pack_vector(vector)
        if vector and len(vector) != self.embedding_dim:
            logger.warning(
                "upsert %s: dim mismatch (%d != %d) -> stored with vector=NULL",
                point_id, len(vector), self.embedding_dim,
            )
            blob = None
        embedded = blob is not None
        payload["embedded"] = embedded
        now = datetime.now(timezone.utc).isoformat()
        sparse_json = json.dumps(sparse) if sparse else None
        return point_id, blob, json.dumps(payload), sparse_json, now, \
            payload["agent_scope"], payload.get("user_id")

    def _upsert_one(self, point_id, vector, payload, sparse) -> None:
        pid, blob, payload_json, sparse_json, now, scope, user = self._prepare_row(
            point_id, vector, payload, sparse
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO points(id, collection, vector, payload, agent_scope, user_id, sparse_json, created_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(collection, id) DO UPDATE SET
                  vector=excluded.vector, payload=excluded.payload,
                  agent_scope=excluded.agent_scope, user_id=excluded.user_id,
                  sparse_json=excluded.sparse_json, created_at=excluded.created_at
                """,
                (pid, self.collection, blob, payload_json, scope, user, sparse_json, now),
            )

    async def upsert(
        self,
        point_id: str,
        vector: Optional[list[float]],
        payload: dict[str, Any],
        sparse: Optional[dict] = None,
        wait: bool = True,
    ) -> None:
        """Insert/update one point. vector=None/zero/dim-mismatch -> stored as NULL."""
        async with self._write_lock:
            await asyncio.to_thread(self._upsert_one, point_id, vector, payload, sparse)

    async def upsert_batch(self, points: list[dict[str, Any]], wait: bool = True) -> None:
        rows = []
        for p in points:
            pid = p.get("id", "?")
            rows.append(self._prepare_row(pid, p.get("vector"), p.get("payload", {}), p.get("sparse_vectors")))
        def _write():
            with self._lock, self._conn:
                self._conn.executemany(
                    """
                    INSERT INTO points(id, collection, vector, payload, agent_scope, user_id, sparse_json, created_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(collection, id) DO UPDATE SET
                      vector=excluded.vector, payload=excluded.payload,
                      agent_scope=excluded.agent_scope, user_id=excluded.user_id,
                      sparse_json=excluded.sparse_json, created_at=excluded.created_at
                    """,
                    [
                        (pid, self.collection, blob, pj, scope, user, sj, now)
                        for pid, blob, pj, sj, now, scope, user in rows
                    ],
                )
        async with self._write_lock:
            await asyncio.to_thread(_write)

    def _get_one(self, point_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT id, payload FROM points WHERE collection=? AND id=?",
            (self.collection, point_id),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            logger.warning("get %s: corrupt payload JSON", point_id)
            return None
        return {"id": row["id"], "payload": payload}

    async def get(self, point_id: str) -> Optional[dict]:
        return await asyncio.to_thread(self._get_one, point_id)

    def _delete_one(self, point_id: str, filter_: Optional[dict]) -> bool:
        sql = "DELETE FROM points WHERE collection=? AND id=?"
        params: list[Any] = [self.collection, point_id]
        if filter_ is not None:  # atomic ownership-enforced delete (anti-TOCTOU)
            where, fparams = self._translate_filter(filter_)
            sql += f" AND {where}"
            params.extend(fparams)
        with self._lock, self._conn:
            cur = self._conn.execute(sql, params)
            return cur.rowcount > 0

    async def delete(
        self,
        point_id: str,
        wait: bool = True,
        filter: Optional[dict] = None,
    ) -> bool:
        """Delete one point. With `filter`, the delete is ATOMIC (id+scope must
        both match in a single statement) — callers enforcing ownership MUST
        pass it; check-then-act in Python is a TOCTOU and is forbidden."""
        async with self._write_lock:
            return await asyncio.to_thread(self._delete_one, point_id, filter)

    async def count(self) -> int:
        def _count():
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM points WHERE collection=?", (self.collection,)
            ).fetchone()
            return row["c"]
        return await asyncio.to_thread(_count)

    # ── Search (engine-level enforcement, ISO-05) ──────────────

    def _score_candidates(self, rows, query_vec: Optional[list[float]]):
        """Score SQL-filtered candidate rows. Returns scored dicts."""
        scored = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                logger.warning("search: skipped corrupt payload for id=%s", row["id"])
                continue
            blob = row["vector"]
            if blob is not None:
                vec = self._unpack_vector(blob)
                source = "dense"
            else:
                content = str(payload.get("content") or payload.get("text") or payload)
                vec = hash_vector(content, self.embedding_dim)
                source = "hash"
            if query_vec is None:
                score = 0.0
            else:
                score = _cosine(query_vec, vec)
            scored.append(
                {"id": row["id"], "score": score, "payload": payload, "score_source": source}
            )
        return scored

    def _search_sync(self, vector, limit, score_threshold, filter_) -> list[dict]:
        where, params = self._translate_filter(filter_)
        sql = (
            "SELECT id, vector, payload FROM points "
            f"WHERE collection=? AND {where}"
        )
        rows = self._conn.execute(sql, (self.collection, *params)).fetchall()
        query_vec = self._unpack_vector(self._pack_vector(vector))
        scored = self._score_candidates(rows, query_vec)
        hits = [s for s in scored if s["score"] >= score_threshold]
        hits.sort(key=lambda s: s["score"], reverse=True)
        return hits[:limit]

    async def search(
        self,
        vector: Optional[list[float]],
        limit: int = 10,
        score_threshold: float = 0.3,
        filter: Optional[dict] = None,
    ) -> list[dict]:
        """Dense search restricted by ENGINE filter. Fails closed without one."""
        return await asyncio.to_thread(self._search_sync, vector, limit, score_threshold, filter)

    def _scroll_sync(self, filter_, limit) -> list[dict]:
        where, params = self._translate_filter(filter_)
        rows = self._conn.execute(
            f"SELECT id, payload FROM points WHERE collection=? AND {where} LIMIT ?",
            (self.collection, *params, int(limit)),
        ).fetchall()
        out = []
        for row in rows:
            try:
                out.append(json.loads(row["payload"]))
            except json.JSONDecodeError:
                logger.warning("scroll: skipped corrupt payload for id=%s", row["id"])
        return out

    async def scroll(
        self,
        filter: Optional[dict] = None,
        limit: int = 50,
        with_payload: bool = True,
    ) -> list[dict]:
        """Deterministic listing restricted by ENGINE filter. Fails closed."""
        return await asyncio.to_thread(self._scroll_sync, filter, limit)
