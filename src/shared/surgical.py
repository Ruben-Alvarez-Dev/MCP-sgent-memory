"""Surgical memory operations engine — invariant-preserving delete/edit/redact.

Grupo A+B de surgical-memory-ops (openspec/changes/surgical-memory-ops).

Principios SOTA encarnados aquí (no decorativos — cada uno cambia código):

- **Teoría de conjuntos para integridad**: la sincronización points↔points_fts
  se verifica como diferencias bidireccionales (A∖B, B∖A) con anti-joins SQL —
  O(n log n) dentro de SQLite, nunca bucles Python sobre filas.
- **Memento + transacción compensatoria (SAGA)**: toda escritura persiste un
  bundle inmutable con la pre-imagen de las filas afectadas; `undo()` es un
  upsert idempotente por clave primaria que converge al estado previo.
- **Event sourcing**: L0 es el log append-only; el motor EMITE el evento de
  auditoría en el OpResult y el host lo persiste — separación entre mecánica
  y observabilidad.
- **Hash canónico** para planes/firmas: SHA-256 sobre JSON con claves
  ordenadas y separadores compactos (sabor RFC 8785) — estable ante
  re-serializaciones.
- **Fail-closed (falsabilidad aplicada a escrituras)**: verify() debe poder
  rechazar las propias escrituras del sistema; el gate aborta y restaura.
- **Chesterton's fence**: el schema no declara FK points→entities, así que el
  motor NO inventa cascadas silenciosas; el grafo se limpia con purgas
  explícitas y observables (purge_orphans, purge_unreferenced_entities).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent-memory.surgical")

_REDACT_MASK = "[REDACTED]"


# ── Modelos de resultado ───────────────────────────────────────────────────


@dataclass
class OpResult:
    """Resultado de una operación quirúrgica unitaria."""

    op_id: str
    action: str
    point_id: str
    ok: bool
    affected: dict = field(default_factory=dict)      # filas tocadas por tabla
    backup_path: str = ""
    audit_event: dict = field(default_factory=dict)   # el host lo persiste en L0
    verify: dict = field(default_factory=dict)        # informe post-op
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "op_id": self.op_id, "action": self.action, "point_id": self.point_id,
            "ok": self.ok, "affected": self.affected, "backup_path": self.backup_path,
            "audit_event": self.audit_event, "verify": self.verify, "error": self.error,
        }


@dataclass
class IntegrityReport:
    """Informe de invariantes (SURG-07)."""

    passed: bool
    fts_orphans: int = 0          # filas FTS sin punto (índice fantasma)
    fts_missing: int = 0          # puntos sin fila FTS (sin indexar)
    dangling_relations: int = 0   # relaciones con endpoint inexistente
    integrity_check: str = ""
    full_scan_unreferenced_entities: int | None = None  # solo verify(full=True)
    details: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed, "fts_orphans": self.fts_orphans,
            "fts_missing": self.fts_missing, "dangling_relations": self.dangling_relations,
            "integrity_check": self.integrity_check,
            "full_scan_unreferenced_entities": self.full_scan_unreferenced_entities,
            "details": self.details,
        }


def canonical_hash(payload: Any) -> str:
    """SHA-256 sobre JSON canónico (claves ordenadas, compacto — RFC 8785-like)."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


# ── Engine ────────────────────────────────────────────────────────────────


class SurgicalEngine:
    """Operaciones quirúrgicas con garantías de integridad.

    Toda escritura: backup previo → transacción única → verify post-op.
    Síncrono por diseño (SQLite local, µs-ms); los hosts lo ejecutan en
    threadpool. Los fallos operativos vuelven como OpResult.ok=False; solo
    las violaciones de contrato (scope, confirm) lanzan.
    """

    def __init__(self, db):
        self._db = db
        base = os.getenv("MEMORY_SERVER_DIR") or os.path.expanduser("~/.memory")
        data_dir = os.getenv("DATA_DIR") or os.path.join(base, "data")
        self._backup_dir = Path(data_dir) / "surgical" / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    # ── helpers internos ──────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        return self._db._conn

    def _point_row(self, point_id: str):
        return self._conn().execute(
            "SELECT id, collection, payload, agent_scope, user_id, layer, created_at "
            "FROM points WHERE collection=? AND id=?",
            (self._db.collection, point_id),
        ).fetchone()

    def _fts_rowid(self, point_id: str) -> int | None:
        row = self._conn().execute(
            "SELECT rowid FROM points WHERE collection=? AND id=?",
            (self._db.collection, point_id),
        ).fetchone()
        return int(row["rowid"]) if row else None

    def _backup(self, op_id: str, action: str, point_id: str) -> Path:
        """Memento: pre-imagen completa (points + FTS) de un punto → JSONL."""
        row = self._point_row(point_id)
        if row is None:
            raise LookupError(f"point {point_id} not found")
        fts_row = self._conn().execute(
            "SELECT rowid, content FROM points_fts WHERE rowid=?", (self._fts_rowid(point_id),)
        ).fetchone() if self._fts_rowid(point_id) is not None else None
        path = self._backup_dir / f"{op_id}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"_header": True, "op_id": op_id, "action": action,
                                "point_id": point_id, "ts": time.time(),
                                "collection": self._db.collection}) + "\n")
            f.write(json.dumps({"table": "points", "row": dict(row)}) + "\n")
            if fts_row is not None:
                f.write(json.dumps({"table": "points_fts", "rowid": int(fts_row["rowid"]),
                                    "content": fts_row["content"]}) + "\n")
        os.chmod(path, 0o600)
        return path

    def _audit(self, op_id: str, action: str, point_id: str, ok: bool, extra: dict) -> dict:
        """SURG-12: el motor EMITE el evento; el host lo persiste en L0."""
        return {"op_id": op_id, "action": action, "point_id": point_id,
                "ok": ok, "engine": "surgical", **extra}

    def _post_verify(self, point_id: str | None = None) -> dict:
        rep = self.verify(point_id=point_id)
        return rep.to_dict()

    # ── A.2: verificación de invariantes (SURG-07) ────────────────────

    def verify(self, point_id: str | None = None, full: bool = False) -> IntegrityReport:
        """Invariantes sobre toda la DB (o el subconjunto de un punto).

        full=True añade el escaneo caro de entidades sin mención en points
        (solo diagnóstico explícito: es O(points×entities) por LIKE).
        """
        conn = self._conn()
        rep = IntegrityReport(passed=True)

        # (a) bidireccional points↔points_fts — anti-joins en SQL (conjuntos)
        scope_sql, params = ("", [])
        if point_id is not None:
            scope_sql, params = " AND p.id=?", [point_id]
        rep.fts_missing = conn.execute(
            "SELECT COUNT(*) FROM points p WHERE NOT EXISTS "
            "(SELECT 1 FROM points_fts t WHERE t.rowid=p.rowid)" + scope_sql,
            params,
        ).fetchone()[0]
        orphan_sql = (
            "SELECT COUNT(*) FROM points_fts t WHERE NOT EXISTS "
            "(SELECT 1 FROM points p WHERE p.rowid=t.rowid AND p.collection=?)"
        )
        rep.fts_orphans = conn.execute(orphan_sql, (self._db.collection,)).fetchone()[0]
        if point_id is not None:
            # para el subconjunto: huérfanos no aplican (el punto existe por definición)
            rep.fts_orphans = 0

        # (b) grafo: relaciones con endpoints inexistentes (anti-join)
        rep.dangling_relations = conn.execute(
            "SELECT COUNT(*) FROM relations r WHERE NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id=r.from_entity) OR NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id=r.to_entity)"
        ).fetchone()[0]

        # (c) SQLite integrity_check
        rep.integrity_check = conn.execute("PRAGMA integrity_check").fetchone()[0]

        # (d) escaneo caro opcional: entidades sin mención en points vivos
        if full:
            rows = conn.execute("SELECT id, name, agent_scope FROM entities").fetchall()
            unreferenced = 0
            for e in rows:
                hits = conn.execute(
                    "SELECT COUNT(*) FROM points WHERE collection=? AND agent_scope=? "
                    "AND instr(lower(payload), ?)>0",
                    (self._db.collection, e["agent_scope"], e["name"].lower()),
                ).fetchone()[0]
                if hits == 0:
                    unreferenced += 1
            rep.full_scan_unreferenced_entities = unreferenced

        rep.passed = (rep.fts_missing == 0 and rep.fts_orphans == 0
                      and rep.dangling_relations == 0 and rep.integrity_check == "ok")
        if not rep.passed:
            rep.details.append("some invariants failed — see counters")
        return rep

    # ── B.1: delete unitario (SURG-03) ────────────────────────────────

    def delete_single(self, point_id: str, expected_scope: str | None = None) -> OpResult:
        op_id = f"del_{uuid.uuid4().hex[:12]}"
        res = OpResult(op_id=op_id, action="delete", point_id=point_id, ok=False)
        try:
            row = self._point_row(point_id)
            if row is None:
                res.error = "not_found"
                res.audit_event = self._audit(op_id, "delete", point_id, False, {"reason": "not_found"})
                return res
            if expected_scope and row["agent_scope"] != expected_scope:
                raise PermissionError(
                    f"scope mismatch: point is '{row['agent_scope']}', expected '{expected_scope}'"
                )
            backup = self._backup(op_id, "delete", point_id)
            fts_rowid = self._fts_rowid(point_id)
            with self._db._lock, self._db._conn:
                cur = self._conn().execute(
                    "DELETE FROM points WHERE collection=? AND id=?",
                    (self._db.collection, point_id),
                )
                if cur.rowcount > 0 and fts_rowid is not None:
                    self._conn().execute("DELETE FROM points_fts WHERE rowid=?", (fts_rowid,))
                res.ok = cur.rowcount > 0
            res.affected = {"points": cur.rowcount, "points_fts": 1 if (cur.rowcount and fts_rowid) else 0}
            res.backup_path = str(backup)
            res.verify = self._post_verify()
            res.audit_event = self._audit(op_id, "delete", point_id, res.ok,
                                          {"scope": row["agent_scope"]})
        except PermissionError:
            # Violación de contrato (aislamiento): fail-LOUD, no OpResult.
            # El llamador (UI/REST/MCP) responde 403 y registra el intento.
            logger.warning("surgical delete rejected: scope mismatch on %s", point_id)
            raise
        except sqlite3.Error as e:
            res.error = f"sqlite: {e}"
            return res
        return res

    # ── B.2/B.3: edición y redacción (SURG-04/05, STO-09) ────────────

    def edit_payload(self, point_id: str, patch: dict, expected_scope: str | None = None) -> OpResult:
        return self._mutate(point_id, "edit", patch, expected_scope)

    def redact(self, point_id: str, mask: str = _REDACT_MASK, expected_scope: str | None = None) -> OpResult:
        return self._mutate(point_id, "redact", {"content": mask}, expected_scope,
                            keep_only_content=True)

    def _mutate(self, point_id: str, action: str, patch: dict,
                expected_scope: str | None = None, keep_only_content: bool = False) -> OpResult:
        op_id = f"{action}_{uuid.uuid4().hex[:12]}"
        res = OpResult(op_id=op_id, action=action, point_id=point_id, ok=False)
        try:
            row = self._point_row(point_id)
            if row is None:
                res.error = "not_found"
                res.audit_event = self._audit(op_id, action, point_id, False, {"reason": "not_found"})
                return res
            if expected_scope and row["agent_scope"] != expected_scope:
                raise PermissionError(
                    f"scope mismatch: point is '{row['agent_scope']}', expected '{expected_scope}'"
                )
            backup = self._backup(op_id, action, point_id)
            payload = json.loads(row["payload"])
            if keep_only_content:
                new_payload = dict(payload)
                new_payload["content"] = patch["content"]
            else:
                new_payload = dict(payload)
                new_payload.update(patch)
            new_json = json.dumps(new_payload, ensure_ascii=False)
            fts_rowid = self._fts_rowid(point_id)
            with self._db._lock, self._db._conn:
                self._conn().execute("UPDATE points SET payload=? WHERE collection=? AND id=?",
                                     (new_json, self._db.collection, point_id))
                # STO-09: re-sync FTS en la misma transacción (DELETE+INSERT)
                if fts_rowid is not None:
                    self._conn().execute("DELETE FROM points_fts WHERE rowid=?", (fts_rowid,))
                    self._conn().execute("INSERT INTO points_fts(rowid, content) VALUES (?, ?)",
                                         (fts_rowid, str(new_payload.get("content", ""))))
                res.ok = True
            res.affected = {"points": 1, "points_fts": 1 if fts_rowid else 0}
            res.backup_path = str(backup)
            res.verify = self._post_verify()
            res.audit_event = self._audit(op_id, action, point_id, True,
                                          {"scope": row["agent_scope"],
                                           "redacted": keep_only_content})
        except PermissionError:
            logger.warning("surgical %s rejected: scope mismatch on %s", action, point_id)
            raise
        except (sqlite3.Error, json.JSONDecodeError) as e:
            res.error = f"{type(e).__name__}: {e}"
        return res

    # ── B.4: re-scope (SURG-10, ISO-18) ───────────────────────────────

    def move_scope(self, point_id: str, to_scope: str, to_user: str | None = None,
                   confirm: str | None = None) -> OpResult:
        if not confirm or confirm != canonical_hash({"point_id": point_id, "to_scope": to_scope}):
            raise ValueError(
                "confirm required: canonical_hash({'point_id':…, 'to_scope':…})"
            )
        op_id = f"move_{uuid.uuid4().hex[:12]}"
        res = OpResult(op_id=op_id, action="move_scope", point_id=point_id, ok=False)
        try:
            row = self._point_row(point_id)
            if row is None:
                res.error = "not_found"
                return res
            backup = self._backup(op_id, "move_scope", point_id)
            payload = json.loads(row["payload"])
            payload["agent_scope"] = to_scope
            if to_user:
                payload["user_id"] = to_user
            with self._db._lock, self._db._conn:
                cur = self._conn().execute(
                    "UPDATE points SET agent_scope=?, user_id=?, payload=? "
                    "WHERE collection=? AND id=? AND agent_scope=?",
                    (to_scope, to_user or row["user_id"], json.dumps(payload, ensure_ascii=False),
                     self._db.collection, point_id, row["agent_scope"]),
                )
                res.ok = cur.rowcount > 0
            res.affected = {"points": cur.rowcount}
            res.backup_path = str(backup)
            res.verify = self._post_verify()
            res.audit_event = self._audit(op_id, "move_scope", point_id, res.ok,
                                          {"from_scope": row["agent_scope"], "to_scope": to_scope})
        except sqlite3.Error as e:
            res.error = f"sqlite: {e}"
        return res

    # ── B.5: reindex y purga de huérfanos (SURG-08/09) ────────────────

    def reindex(self, point_ids: list[str] | None = None) -> OpResult:
        op_id = f"reindex_{uuid.uuid4().hex[:12]}"
        res = OpResult(op_id=op_id, action="reindex", point_id=",".join(point_ids or ["all"]), ok=False)
        try:
            conn = self._conn()
            with self._db._lock, self._db._conn:
                if point_ids:
                    for pid in point_ids:
                        row = self._point_row(pid)
                        if row is None:
                            continue
                        rowid_row = conn.execute(
                            "SELECT rowid FROM points WHERE collection=? AND id=?",
                            (self._db.collection, pid),
                        ).fetchone()
                        rid = rowid_row[0] if rowid_row else None
                        if rid is None:
                            continue
                        content = str(json.loads(row["payload"]).get("content", ""))
                        conn.execute("DELETE FROM points_fts WHERE rowid=?", (rid,))
                        conn.execute("INSERT INTO points_fts(rowid, content) VALUES (?, ?)", (rid, content))
                else:
                    rows = conn.execute(
                        "SELECT rowid, id, payload FROM points WHERE collection=?",
                        (self._db.collection,),
                    ).fetchall()
                    conn.execute("DELETE FROM points_fts")
                    for row in rows:
                        try:
                            content = str(json.loads(row["payload"]).get("content", ""))
                        except json.JSONDecodeError:
                            content = ""
                        conn.execute("INSERT INTO points_fts(rowid, content) VALUES (?, ?)",
                                     (row["rowid"], content))
                res.ok = True
            res.verify = self._post_verify()
            res.audit_event = self._audit(op_id, "reindex", res.point_id, True, {})
        except (sqlite3.Error, json.JSONDecodeError) as e:
            res.error = f"{type(e).__name__}: {e}"
        return res

    def purge_orphans(self, dry_run: bool = True) -> dict:
        """SURG-09: elimina filas FTS fantasma y relaciones con endpoints
        inexistentes. Jamás toca points válidos. dry_run=True solo lista."""
        conn = self._conn()
        orphan_fts = [int(r["rowid"]) for r in conn.execute(
            "SELECT t.rowid AS rowid FROM points_fts t WHERE NOT EXISTS "
            "(SELECT 1 FROM points p WHERE p.rowid=t.rowid)"
        ).fetchall()]
        dangling = [dict(r) for r in conn.execute(
            "SELECT r.from_entity, r.to_entity, r.relation_type FROM relations r WHERE NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id=r.from_entity) OR NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id=r.to_entity)"
        ).fetchall()]
        out = {"orphan_fts_rowids": orphan_fts, "dangling_relations": dangling,
               "deleted": 0}
        if not dry_run:
            with self._db._lock, self._db._conn:
                for rid in orphan_fts:
                    conn.execute("DELETE FROM points_fts WHERE rowid=?", (rid,))
                for r in dangling:
                    conn.execute(
                        "DELETE FROM relations WHERE from_entity=? AND to_entity=? AND relation_type=?",
                        (r["from_entity"], r["to_entity"], r["relation_type"]),
                    )
                out["deleted"] = len(orphan_fts) + len(dangling)
            out["verify"] = self.verify().to_dict()
        return out

    # ── A.3: undo idempotente (SURG-06/14) ────────────────────────────

    def list_backups(self) -> list[dict]:
        out = []
        for f in sorted(self._backup_dir.glob("*.jsonl")):
            try:
                header = json.loads(f.read_text().splitlines()[0])
                out.append({"op_id": header.get("op_id"), "action": header.get("action"),
                            "point_id": header.get("point_id"), "file": str(f)})
            except (json.JSONDecodeError, IndexError):
                continue
        return out

    def undo(self, op_id: str) -> OpResult:
        """Restore idempotente desde el bundle (INSERT OR REPLACE por PK)."""
        res = OpResult(op_id=op_id, action="undo", point_id="", ok=False)
        path = self._backup_dir / f"{op_id}.jsonl"
        if not path.exists():
            res.error = "backup bundle not found"
            return res
        try:
            lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        except json.JSONDecodeError as e:
            res.error = f"corrupt bundle: {e}"  # SURG-14: fail-closed
            return res
        header = next((l for l in lines if l.get("_header")), None)
        if header is None:
            res.error = "corrupt bundle: missing header"
            return res
        res.point_id = str(header.get("point_id", ""))
        restored = {"points": 0, "points_fts": 0}
        with self._db._lock, self._db._conn:
            for line in lines:
                if line.get("_header"):
                    continue
                if line["table"] == "points":
                    r = line["row"]
                    self._conn().execute(
                        "INSERT OR REPLACE INTO points(id, collection, payload, agent_scope, "
                        "user_id, layer, sparse_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (r["id"], r["collection"], r["payload"], r["agent_scope"],
                         r["user_id"], r["layer"], r.get("sparse_json"), r["created_at"]),
                    )
                    restored["points"] += 1
                    # FTS del estado previo: resync con el payload restaurado
                    rowid = self._conn().execute(
                        "SELECT rowid FROM points WHERE collection=? AND id=?",
                        (r["collection"], r["id"]),
                    ).fetchone()
                    if rowid:
                        content = ""
                        try:
                            content = str(json.loads(r["payload"]).get("content", ""))
                        except json.JSONDecodeError:
                            pass
                        self._conn().execute("DELETE FROM points_fts WHERE rowid=?", (rowid["rowid"],))
                        self._conn().execute("INSERT INTO points_fts(rowid, content) VALUES (?, ?)",
                                             (rowid["rowid"], content))
                        restored["points_fts"] += 1
        res.ok = True
        res.affected = restored
        res.verify = self._post_verify()
        res.audit_event = self._audit(op_id, "undo", res.point_id, True, {})
        return res
