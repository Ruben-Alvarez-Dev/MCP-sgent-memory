"""Unified single-file memory store (M2-storage).

Replaces Qdrant HTTP daemon with SQLite (stdlib only). One file, `memory.db`,
hosts dense memory points, conversations and facts. All scope/user filtering is
enforced ENGINE-LEVEL (SQL WHERE with bound parameters) — Python post-filtering
of fetched rows is forbidden by ISO-05.

Interface parity with the old QdrantClient so MCP servers migrate by changing
the constructor + import and DELETING their post-filters.

Hard guarantees (openspec/changes/M2-storage, amended M9-schema-migration):
- STO-05 (M9): zero-vector/embedding fallback machinery REMOVED — there is no
  vector column at all. Retrieval is FTS5-only (bm25); the schema migration
  drops the dead `vector` column from pre-M9 databases at boot.
- ISO-11: filter keys validated ^[a-z_][a-z0-9_]*$, values always bound params.
- ISO-12: writes without agent_scope default to payload["agent_scope"]="shared".
- Fail-closed: search/scroll REQUIRE a filter (ScopeRequiredError otherwise).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from .entity import extract_entities
from .scope import ScopeError, normalize_scope

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 4
_FILTER_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_RESERVED_PAYLOAD_KEYS = frozenset({"id", "vector", "sparse_vectors", "payload"})
_PAYLOAD_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class ScopeRequiredError(ValueError):
    """Raised when a read path is invoked without an explicit engine filter."""


# ISO-11: only these payload fields are engine-filterable. Everything else
# must go through explicit APIs — prevents filter-key injection by design.
# ISO-16: the trunk scope "merged" is write-gated (human approval +
# provenance required). "global" stays reserved-unusable forever.
_MERGED_SCOPES = {"merged"}

_ENGINE_FILTER_COLUMNS = {
    "agent_scope": "agent_scope",
    "user_id": "user_id",
    "layer": "layer",  # system-controlled (server-written), never caller input
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


class MemoryDB:
    """Async facade over a per-collection slice of the shared memory.db file."""

    def __init__(
        self,
        db_path: str | None = None,
        collection: str = "L0_L4_memory",
        embedding_dim: int = 1024,
    ):
        """`embedding_dim` accepted for interface parity (M9: ignored — no vectors)."""
        self.db_path = db_path or default_db_path()
        self.collection = collection
        self.embedding_dim = embedding_dim
        self._lock = threading.RLock()
        self._write_lock = asyncio.Lock()
        self._conn = self._connect()
        # M9: migrate at boot — creates schema if missing and drops the dead
        # vector column from pre-M9 databases (idempotent, fail-safe).
        self._ensure_schema()

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
                  payload TEXT NOT NULL,
                  agent_scope TEXT NOT NULL DEFAULT 'shared',
                  user_id TEXT,
                  layer INTEGER,
                  sparse_json TEXT,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY(collection, id)
                )
                """
            )
            # M9: drop the dead vector column left by pre-M9 databases.
            # No-op when absent; tolerated on SQLite builds without DROP COLUMN.
            try:
                self._conn.execute("ALTER TABLE points DROP COLUMN vector")
            except sqlite3.OperationalError:
                pass
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_points_scope
                ON points(collection, agent_scope, user_id, layer)
                """
            )
            # STO-07: FTS5 full-text search on points content (M6)
            # No content_rowid — we sync manually via _sync_fts_upsert using point_id.
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS points_fts USING fts5(
                  content
                )
                """
            )
            # FTS5: sync is handled in Python (not triggers) to tolerate corrupt payload JSON.
            # Triggers would fail on json_extract of malformed payloads. Python-level sync
            # catches the error and inserts empty content as fallback.
            # STO-08: Entities table
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entities(
                  id TEXT NOT NULL PRIMARY KEY,
                  name TEXT NOT NULL,
                  type TEXT NOT NULL CHECK(type IN (
                    'class','function','module','concept','decision','pattern','constant'
                  )),
                  agent_scope TEXT NOT NULL,
                  layer INTEGER NOT NULL,
                  first_seen TEXT NOT NULL,
                  last_seen TEXT NOT NULL,
                  mention_count INTEGER DEFAULT 1
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_scope ON entities(agent_scope)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)"
            )
            # STO-09: Relations table
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relations(
                  from_entity TEXT NOT NULL,
                  to_entity TEXT NOT NULL,
                  relation_type TEXT NOT NULL CHECK(relation_type IN (
                    'depends_on','implements','extends','uses','decides','fixes','part_of'
                  )),
                  agent_scope TEXT NOT NULL,
                  strength REAL DEFAULT 1.0,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY (from_entity, to_entity, relation_type, agent_scope)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_relations_scope ON relations(agent_scope)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity, agent_scope)"
            )
            # STO-10: Synonyms table (seeded at bootstrap)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS synonyms(
                  term TEXT PRIMARY KEY,
                  synonyms TEXT NOT NULL
                )
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
        except Exception:  # noqa: BLE001 — health() IS the "any failure -> False" boundary
            return False

    async def close(self) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self._conn.close)

    def with_collection(self, collection: str) -> MemoryDB:
        """Create a new client targeting a different collection (parity)."""
        return MemoryDB(self.db_path, collection, self.embedding_dim)

    # ── Filter translation (ISO-11) ────────────────────────────

    @staticmethod
    def _translate_filter(filter_: dict | None) -> tuple[str, list[Any]]:
        """Legacy-compatible filter dict ({"must":[{"key":k,...}]}) -> safe SQL.

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
                # ValueError (not TypeError): filter contract violation is a
                # caller-input error, same family as ScopeRequiredError.
                raise ValueError("filter condition must be a dict")  # noqa: TRY004
            key = cond.get("key")
            match = cond.get("match")
            value = match.get("value") if isinstance(match, dict) else None
            any_values = match.get("any") if isinstance(match, dict) else None
            if not isinstance(key, str) or key not in _ENGINE_FILTER_COLUMNS:
                raise ValueError(f"filter key not engine-filterable: {key!r}")
            col = _ENGINE_FILTER_COLUMNS[key]
            if any_values is not None:
                # Qdrant-parity match.any -> IN clause (own+shared merges)
                if (
                    not isinstance(any_values, list)
                    or not any_values
                    or any(v is None or isinstance(v, (dict, list)) for v in any_values)
                ):
                    raise ValueError(f"filter any-values for '{key}' must be non-empty scalars")
                placeholders = ", ".join("?" for _ in any_values)
                clauses.append(f"{col} IN ({placeholders})")
                params.extend(any_values)
                continue
            if value is None or isinstance(value, (dict, list)):
                raise ValueError(f"Filter value for '{key}' must be scalar")
            clauses.append(f"{col} = ?")
            params.append(value)
        if not clauses:
            raise ScopeRequiredError("Empty filter — refuse unfiltered scan")
        return " AND ".join(clauses), params

    # ── Point operations ───────────────────────────────────────

    def _prepare_row(self, point_id: str, payload, sparse, allow_reserved_scope: bool = False):
        if point_id is None or not isinstance(point_id, str) or not point_id.strip():
            raise ValueError(f"Invalid point id: {point_id!r}")
        _validate_payload_keys(payload, point_id)
        payload = dict(payload)
        if "agent_scope" not in payload:  # ISO-12: no global-implicit default
            payload["agent_scope"] = "shared"
            logger.info("upsert %s: missing agent_scope -> defaulted to 'shared'", point_id)
        # M5-audit M1: case/whitespace variants ("MERGED", " merged") must not
        # bypass the trunk gate. NOTE: normalize_scope REJECTS reserved names
        # (merged included) — so the trunk check runs on the stripped/lowered
        # raw value first, and only non-trunk scopes get full canonicalization.
        if str(payload["agent_scope"]).strip().lower() in _MERGED_SCOPES:
            payload["agent_scope"] = str(payload["agent_scope"]).strip().lower()
            if not allow_reserved_scope:
                raise ScopeError(
                    f"scope {payload['agent_scope']!r} is the human-approved trunk: "
                    "upsert requires allow_reserved_scope=True (A11)"
                )
        else:
            payload["agent_scope"] = normalize_scope(str(payload["agent_scope"]))
        if payload["agent_scope"] in _MERGED_SCOPES:  # ISO-16 trunk gate
            if not allow_reserved_scope:
                raise ScopeError(
                    f"scope {payload['agent_scope']!r} is the human-approved trunk: "
                    "upsert requires allow_reserved_scope=True (A11)"
                )
            if not payload.get("approved_by") or not isinstance(payload.get("approved_by"), str):
                raise ScopeError("trunk writes require non-empty payload['approved_by'] (A12)")
            prov = payload.get("provenance")
            if not isinstance(prov, list) or not prov or not all(
                isinstance(p, dict) and p.get("from_scope") and p.get("point_id") for p in prov
            ):
                raise ScopeError(
                    "trunk writes require non-empty payload['provenance'] "
                    "=[{from_scope, point_id}, ...] (A12)"
                )
        payload["schema_version"] = payload.get("schema_version", "1.0")
        # M6: extract entities from content for entity graph
        content_text = payload.get("content", "")
        entity_list = []
        if content_text:
            entities = extract_entities(content_text)
            entity_list = [e["name"] for e in entities]
            payload["entities"] = entity_list
            # Store entities in entities table (M6: STO-08)
            layer_val = payload.get("layer", 1)
            scope_val = payload.get("agent_scope", "shared")
            for e in entities:
                self._upsert_entity(e["name"], e["type"], scope_val, layer_val)
        now = datetime.now(UTC).isoformat()
        sparse_json = json.dumps(sparse) if sparse else None
        layer = payload.get("layer")
        if layer is not None and not isinstance(layer, int):
            try:
                layer = int(layer)
            except (TypeError, ValueError):
                layer = None
        return point_id, json.dumps(payload), sparse_json, now, \
            payload["agent_scope"], payload.get("user_id"), layer

    def _upsert_one(self, point_id, payload, sparse, allow_reserved_scope=False) -> None:
        pid, payload_json, sparse_json, now, scope, user, layer = self._prepare_row(
            point_id, payload, sparse, allow_reserved_scope
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO points(id, collection, payload, agent_scope, user_id, layer, sparse_json, created_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(collection, id) DO UPDATE SET
                  payload=excluded.payload,
                  agent_scope=excluded.agent_scope, user_id=excluded.user_id,
                  layer=excluded.layer,
                  sparse_json=excluded.sparse_json, created_at=excluded.created_at
                """,
                (pid, self.collection, payload_json, scope, user, layer, sparse_json, now),
            )
            # M6: sync FTS5 (tolerant of corrupt payload JSON)
            self._sync_fts_upsert(pid, payload_json)

    async def upsert(
        self,
        point_id: str,
        payload: dict[str, Any] | None = None,
        sparse: dict | None = None,
        wait: bool = True,
        allow_reserved_scope: bool = False,
    ) -> None:
        """Insert/update one point (M9: vector-less schema, FTS5 retrieval).

        ISO-16: writing into the trunk scope "merged" requires
        allow_reserved_scope=True AND payload approved_by + provenance.
        """
        if payload is None:
            raise ValueError("payload is required")
        async with self._write_lock:
            await asyncio.to_thread(
                self._upsert_one, point_id, payload, sparse, allow_reserved_scope
            )

    async def upsert_batch(
        self, points: list[dict[str, Any]], wait: bool = True, allow_reserved_scope: bool = False
    ) -> None:
        rows = []
        for p in points:
            pid = p.get("id", "?")
            rows.append(
                self._prepare_row(
                    pid, p.get("payload", {}), p.get("sparse_vectors"),
                    allow_reserved_scope,
                )
            )
        def _write():
            with self._lock, self._conn:
                self._conn.executemany(
                    """
                    INSERT INTO points(id, collection, payload, agent_scope, user_id, layer, sparse_json, created_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(collection, id) DO UPDATE SET
                      payload=excluded.payload,
                      agent_scope=excluded.agent_scope, user_id=excluded.user_id,
                      layer=excluded.layer,
                      sparse_json=excluded.sparse_json, created_at=excluded.created_at
                    """,
                    [
                        (pid, self.collection, pj, scope, user, layer, sj, now)
                        for pid, pj, sj, now, scope, user, layer in rows
                    ],
                )
                # M9: batch writes must sync FTS5 too (was single-upsert only —
                # batch-inserted corpora were invisible to FTS5 retrieval).
                for pid, pj, _sj, _now, _scope, _user, _layer in rows:
                    self._sync_fts_upsert(pid, pj)
        async with self._write_lock:
            await asyncio.to_thread(_write)

    def _get_one(self, point_id: str, filter_) -> dict | None:
        # M5-audit C1: get is fail-closed like search — the engine filter is
        # REQUIRED, so a trunk-approval flow can never read foreign-scope
        # points by bare id.
        where, fparams = self._translate_filter(filter_)
        with self._lock:  # M3: serialize — shared conn is not concurrency-safe
            row = self._conn.execute(
            f"SELECT id, payload FROM points WHERE collection=? AND id=? AND {where}",
            (self.collection, point_id, *fparams),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            logger.warning("get %s: corrupt payload JSON", point_id)
            return None
        return {"id": row["id"], "payload": payload}

    async def get(self, point_id: str, filter: dict | None = None) -> dict | None:
        """Fetch one point by id, restricted by an ENGINE filter.

        Fail-closed by design (M5-audit C1): a bare-id fetch could read a
        foreign tenant's point. Pass the same scope filter you would pass to
        search; foreign rows read as not-found.
        """
        return await asyncio.to_thread(self._get_one, point_id, filter)

    def _delete_one(self, point_id: str, filter_: dict | None) -> bool:
        sql = "DELETE FROM points WHERE collection=? AND id=?"
        params: list[Any] = [self.collection, point_id]
        if filter_ is not None:  # atomic ownership-enforced delete (anti-TOCTOU)
            where, fparams = self._translate_filter(filter_)
            sql += f" AND {where}"
            params.extend(fparams)
        with self._lock, self._conn:
            # E2E audit 2026-09-07 (P1): purge points_fts together with the
            # point — deleted content must not linger in the FTS index
            # (retention/privacy). Capture the rowid BEFORE the row is gone;
            # purge only if the delete actually landed (filter mismatch must
            # leave a live point fully indexed).
            fts_row = self._conn.execute(
                "SELECT rowid FROM points WHERE collection=? AND id=?",
                (self.collection, point_id),
            ).fetchone()
            cur = self._conn.execute(sql, params)
            deleted = cur.rowcount > 0
            if deleted and fts_row is not None:
                try:
                    self._conn.execute(
                        "DELETE FROM points_fts WHERE rowid=?", (int(fts_row["rowid"]),)
                    )
                except sqlite3.OperationalError as e:
                    logger.debug("FTS5 delete sync failed for %s: %s", point_id, e)
            return deleted

    def _update_payload_one(self, point_id: str, patch: dict) -> bool:
        """Atomic payload merge — preserves the stored vector (unlike upsert)."""
        _validate_payload_keys(patch, point_id)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT payload, agent_scope, user_id, layer FROM points WHERE collection=? AND id=?",
                (self.collection, point_id),
            ).fetchone()
            if not row:
                return False
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                logger.warning("update_payload %s: corrupt existing payload", point_id)
                return False
            payload.update(patch)
            scope = normalize_scope(str(payload.get("agent_scope") or row["agent_scope"] or "shared"))
            # M5-audit H1: the trunk gate applies to PATCHES too — update_payload
            # must never mint rows in "merged" (approval goes through
            # approve_promotion, which builds real provenance).
            if scope in _MERGED_SCOPES:
                raise ScopeError(
                    "update_payload cannot place rows in the trunk scope "
                    "(use approve_promotion, ISO-16)"
                )
            user = payload.get("user_id", row["user_id"])
            layer = payload.get("layer", row["layer"])
            if layer is not None and not isinstance(layer, int):
                try:
                    layer = int(layer)
                except (TypeError, ValueError):
                    layer = None
            self._conn.execute(
                "UPDATE points SET payload=?, agent_scope=?, user_id=?, layer=? WHERE collection=? AND id=?",
                (json.dumps(payload), scope, user, layer, self.collection, point_id),
            )
            return True

    async def update_payload(self, point_id: str, patch: dict[str, Any]) -> bool:
        """Merge `patch` into the stored payload WITHOUT touching the vector.

        Engine columns (agent_scope/user_id/layer) are re-extracted so the
        enforcement index stays consistent with the merged payload.
        """
        async with self._write_lock:
            return await asyncio.to_thread(self._update_payload_one, point_id, patch)

    async def delete(
        self,
        point_id: str,
        wait: bool = True,
        filter: dict | None = None,
    ) -> bool:
        """Delete one point. With `filter`, the delete is ATOMIC (id+scope must
        both match in a single statement) — callers enforcing ownership MUST
        pass it; check-then-act in Python is a TOCTOU and is forbidden."""
        async with self._write_lock:
            return await asyncio.to_thread(self._delete_one, point_id, filter)

    async def count(self) -> int:
        def _count():
            try:
                with self._lock:
                    row = self._conn.execute(
                        "SELECT COUNT(*) AS c FROM points WHERE collection=?", (self.collection,)
                    ).fetchone()
            except sqlite3.OperationalError:
                return 0  # virgin DB (no table yet) — empty, not an error
            return row["c"]
        return await asyncio.to_thread(_count)

    # ── Search (engine-level enforcement, ISO-05; M9: FTS5-only) ──

    def _scan_sync(self, filter_, limit) -> list[dict]:
        """Fallback scan when FTS5 is unavailable (M9: replaced dense _search_sync).

        Returns SQL-filtered rows with score 0.0 and score_source="scan" —
        no ranking, deterministic order (created_at desc, id asc).
        """
        where, params = self._translate_filter(filter_)
        sql = (
            "SELECT id, payload, agent_scope, layer, created_at FROM points "
            f"WHERE collection=? AND {where} "
            "ORDER BY created_at DESC, id ASC LIMIT ?"
        )
        with self._lock:  # M3: serialize — shared conn is not concurrency-safe
            rows = self._conn.execute(sql, (self.collection, *params, int(limit))).fetchall()
        out = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                logger.warning("scan: skipped corrupt payload for id=%s", row["id"])
                continue
            out.append({
                "id": row["id"],
                "payload": payload,
                "score": 0.0,
                "score_source": "scan",
                "agent_scope": row["agent_scope"],
                "layer": row["layer"],
                "created_at": row["created_at"],
            })
        return out

    async def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0,
        filter: dict | None = None,
    ) -> list[dict]:
        """FTS5 full-text search restricted by ENGINE filter (M9: FTS5-only).

        M9 removed the dense/hash/sparse scoring paths along with the vector
        column: `query` is the user-facing text, bm25-ranked via FTS5
        (score = -rank, higher = better). `score_threshold` applies to the
        FTS5 score only when > 0. Fails closed without a filter.
        """
        self._translate_filter(filter)  # ISO-05: fail-closed without a filter
        if not isinstance(query, str) or not query.strip():
            return []
        built_query = _build_fts5_query(query)
        hits = await asyncio.to_thread(self._search_fts_sync, built_query, limit, filter)
        if score_threshold and score_threshold > 0.0:
            hits = [h for h in hits if h.get("score", 0.0) >= score_threshold]
        return hits[:limit]


    def _sync_fts_upsert(self, point_id: str, payload_json: str) -> None:
        """Sync a point's content into FTS5. Tolerant of corrupt payload JSON."""
        try:
            content = json.loads(payload_json).get("content", "")
        except (json.JSONDecodeError, TypeError):
            content = ""
        # FTS5 requires integer rowid — get it from the points table
        try:
            row = self._conn.execute(
                "SELECT rowid FROM points WHERE collection=? AND id=?",
                (self.collection, point_id),
            ).fetchone()
            if not row:
                return
            fts_rowid = int(row["rowid"])
        except (sqlite3.OperationalError, ValueError, TypeError):
            return
        try:
            # FTS5 virtual tables don't support ON CONFLICT.
            # In WAL mode, INSERT OR REPLACE can cause visibility issues in joins,
            # so we use DELETE+INSERT instead (verified working in WAL).
            self._conn.execute("DELETE FROM points_fts WHERE rowid=?", (fts_rowid,))
            self._conn.execute(
                "INSERT INTO points_fts(rowid, content) VALUES (?, ?)",
                (fts_rowid, content),
            )
        except sqlite3.OperationalError as e:
            logger.debug("FTS5 sync failed for %s: %s", point_id, e)

    def _delete_fts(self, point_id: str) -> None:
        """Remove a point from FTS5. Tolerant of errors."""
        try:
            row = self._conn.execute(
                "SELECT rowid FROM points WHERE collection=? AND id=?",
                (self.collection, point_id),
            ).fetchone()
            if row:
                self._conn.execute(
                    "DELETE FROM points_fts WHERE rowid=?", (int(row["rowid"]),),
                )
        except (sqlite3.OperationalError, ValueError):
            pass

    def _scroll_sync(self, filter_, limit) -> list[dict]:
        where, params = self._translate_filter(filter_)
        with self._lock:  # M3: serialize — shared conn is not concurrency-safe
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
        filter: dict | None = None,
        limit: int = 50,
        with_payload: bool = True,
    ) -> list[dict]:
        """Deterministic listing restricted by ENGINE filter. Fails closed."""
        return await asyncio.to_thread(self._scroll_sync, filter, limit)

    # ── FTS5 Search (M6: RET-01 modified) ─────────────────────

    def _search_fts_sync(
        self,
        fts_query: str,
        limit: int,
        filter_: dict | None,
    ) -> list[dict]:
        """FTS5 full-text search with engine-level scope filter.

        Two-phase approach to avoid WAL-mode FTS5 join issues:
        1. Query FTS5 for matching rowids + ranks
        2. Fetch full point data via IN clause (avoids cross-table join)

        Falls back to points scan if FTS5 is unavailable.
        """
        where, params = self._translate_filter(filter_) if filter_ else ([], [])
        # Phase 1: Get matching rowids from FTS5
        fts_sql = (
            "SELECT fts.rowid AS fts_rowid, fts.rank"
            " FROM points_fts AS fts"
            " WHERE points_fts MATCH ?"
            " LIMIT ?"
        )
        try:
            with self._lock:
                fts_rows = self._conn.execute(fts_sql, (fts_query, int(limit) * 2)).fetchall()
        except sqlite3.OperationalError as e:
            logger.warning("FTS5 search failed, falling back to points scan: %s", e)
            return self._scan_sync(filter_, limit)

        if not fts_rows:
            return []

        # Phase 2: Fetch full point data via rowid IN clause
        # This avoids WAL-mode join issues between FTS5 and points tables
        rowids = [int(r["fts_rowid"]) for r in fts_rows]
        placeholders = ", ".join("?" for _ in rowids)
        data_sql = (
            "SELECT rowid, id, payload, agent_scope, layer, created_at"
            " FROM points"
            f" WHERE rowid IN ({placeholders})"
            f" AND collection = ?"
            f" AND {where}"
        )
        try:
            data_rows = self._conn.execute(data_sql, [*rowids, self.collection, *params]).fetchall()
        except sqlite3.OperationalError:
            return []

        # Build rank lookup
        rank_map = {int(r["fts_rowid"]): r["rank"] for r in fts_rows}

        results = []
        for row in data_rows:
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                logger.warning("fts_search: skipped corrupt payload for id=%s", row["id"])
                continue
            results.append({
                "id": row["id"],
                "payload": payload,
                "score": -rank_map.get(row["rowid"], 0.0),  # FTS5 rank: lower = better
                "score_source": "fts5",
                "agent_scope": row["agent_scope"],
                "layer": row["layer"],
                "created_at": row["created_at"],
            })
        return results

    async def search_fts(
        self,
        fts_query: str,
        limit: int = 10,
        filter: dict | None = None,
    ) -> list[dict]:
        """FTS5 full-text search restricted by ENGINE filter.

        Replaces dense cosine search as the primary retrieval path (M6).
        ISO-05: fails closed without an explicit filter.
        """
        self._translate_filter(filter)  # ISO-05: fail-closed without a filter
        built_query = _build_fts5_query(fts_query)
        return await asyncio.to_thread(self._search_fts_sync, built_query, limit, filter)

    # ── Entity operations (M6: STO-08) ────────────────────────

    def _upsert_entity(self, entity_name: str, entity_type: str, agent_scope: str, layer: int) -> None:
        """Upsert an entity into the entities table."""
        entity_id = f"{agent_scope}:{entity_name.lower()}"
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT id, mention_count, last_seen FROM entities WHERE id=?",
                (entity_id,),
            ).fetchone()
            if existing:
                self._conn.execute(
                    "UPDATE entities SET mention_count=mention_count+1, last_seen=? WHERE id=?",
                    (now, entity_id),
                )
            else:
                self._conn.execute(
                    "INSERT INTO entities(id, name, type, agent_scope, layer, first_seen, last_seen, mention_count)"
                    " VALUES(?,?,?,?,?,?,?,1)",
                    (entity_id, entity_name, entity_type, agent_scope, layer, now, now),
                )

    def get_entities(
        self,
        agent_scope: str,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get entities scoped to agent_scope + shared. ISO-18 enforced."""
        sql = "SELECT * FROM entities WHERE agent_scope IN (?, 'shared')"
        params: list[Any] = [agent_scope]
        if entity_type:
            sql += " AND type = ?"
            params.append(entity_type)
        sql += " ORDER BY mention_count DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Relation operations (M6: STO-09) ──────────────────────

    def upsert_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        agent_scope: str,
        strength: float = 1.0,
    ) -> None:
        """Upsert a relation between entities. ISO-18 enforced."""
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO relations(from_entity, to_entity, relation_type, agent_scope, strength, created_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(from_entity, to_entity, relation_type, agent_scope)
                DO UPDATE SET strength=strength+0.1, created_at=?
                """,
                (from_entity, to_entity, relation_type, agent_scope, strength, now, now),
            )

    def get_relations(
        self,
        agent_scope: str,
        entity_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get relations scoped to agent_scope + shared. ISO-18 enforced."""
        sql = "SELECT * FROM relations WHERE agent_scope IN (?, 'shared')"
        params: list[Any] = [agent_scope]
        if entity_name:
            sql += " AND (from_entity = ? OR to_entity = ?)"
            params.extend([entity_name, entity_name])
        sql += " ORDER BY strength DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Co-occurrence consolidation (M6: MEM-02, MEM-03) ──────

    def find_co_occurring_entities(
        self,
        agent_scope: str,
        min_cooccurrence: int = 3,
    ) -> list[tuple[str, str, str, float]]:
        """Find entity pairs that co-occur in >= min_cooccurrence points.

        Returns [(from_entity, to_entity, relation_type, strength)] for
        entities that appear together frequently enough to warrant a relation.
        """
        # Get all entities for the scope
        entities = self.get_entities(agent_scope, limit=200)
        if len(entities) < 2:
            return []

        # Build co-occurrence: find points that contain pairs of entities
        entity_ids = {e["id"]: e["name"] for e in entities}
        # Query: points in this scope with their extracted entities
        sql = """
            SELECT p.id, json_extract(p.payload, '$.entities') as entities
            FROM points p
            WHERE p.collection = ?
              AND p.agent_scope IN (?, 'shared')
              AND json_array_length(json_extract(p.payload, '$.entities')) > 0
        """
        with self._lock:
            rows = self._conn.execute(sql, (self.collection, agent_scope)).fetchall()

        # Count co-occurrences
        cooccurrence: dict[tuple[str, str], int] = {}
        for row in rows:
            try:
                entity_list = json.loads(row["entities"]) if row["entities"] else []
            except (json.JSONDecodeError, TypeError):
                continue
            for i, e1 in enumerate(entity_list):
                for e2 in entity_list[i+1:]:
                    pair = tuple(sorted([e1, e2]))
                    cooccurrence[pair] = cooccurrence.get(pair, 0) + 1

        # Filter by minimum co-occurrence and determine relation type
        results = []
        for (e1, e2), count in cooccurrence.items():
            if count >= min_cooccurrence:
                strength = min(1.0, count / 10.0)
                # Determine relation type based on entity types
                t1 = entity_ids.get(e1, "")
                t2 = entity_ids.get(e2, "")
                if t1 and t2:
                    if t1.get("type") == "class" and t2.get("type") == "concept":
                        rel_type = "uses"
                    elif t1.get("type") == "class" and t2.get("type") == "class":
                        rel_type = "depends_on"
                    else:
                        rel_type = "uses"
                else:
                    rel_type = "uses"
                results.append((e1, e2, rel_type, strength))

        return sorted(results, key=lambda x: -x[3])


def _build_fts5_query(query: str, synonym_expand: bool = True) -> str:
    """Build an FTS5-compatible query string from a user query.

    Extracts individual tokens (CamelCase, UPPER_SNAKE, lowercase words)
    and returns them OR-joined. FTS5 matches documents containing ANY token;
    bm25 ranking surfaces docs matching MORE tokens first (M9: implicit AND
    collapsed recall to ~0 on natural multi-term queries).

    For synonym-aware search, expand before calling this function.
    """
    # Extract tokens exactly like FTS5's default unicode61 tokenizer does:
    # maximal runs of alphanumerics (underscore is a SEPARATOR for unicode61,
    # so UPPER_SNAKE splits into words — same behavior on the query side and
    # the index side keeps them consistent). Digits must be accepted after the
    # first letter (E2EPROTOCOLSMOKE, OAuth2, ISO14, FTS5) — the old
    # letters-only branch produced fragments ("eprotocolsmoke", "oa"+"uth2")
    # that never matched the index (E2E audit 2026-09-07 roundtrip smoke).
    # Minimum 3 chars keeps noise words out (unchanged from the M6 builder).
    tokens = re.findall(r'[a-zA-Záéíóúñü][a-zA-Z0-9áéíóúñü]{2,}', query)
    if not tokens:
        return query
    # FTS5 is case-insensitive; lowercase for matching. OR-join keeps recall
    # (bm25 ranks multi-token matches higher); single tokens unchanged.
    return ' OR '.join(t.lower() for t in tokens)

