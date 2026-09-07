"""Grupo A+B — surgical-memory-ops: invariantes, backup/undo, ops unitarias.

Cada test nombrado traza a un requisito SURG-xx / STO-xx de
openspec/changes/surgical-memory-ops/specs/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.memory_db import MemoryDB
from shared.surgical import SurgicalEngine, canonical_hash


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SERVER_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    mdb = MemoryDB(str(tmp_path / "memory.db"), "surgical_test", 1024)
    return mdb


@pytest.fixture()
def engine(db):
    return SurgicalEngine(db)


async def _seed(db, pid: str, content: str, scope: str = "shared", user: str | None = None):
    payload = {"memory_id": pid, "content": content, "agent_scope": scope, "layer": 1}
    if user:
        payload["user_id"] = user
    await db.upsert(pid, payload, sparse=None)


def _fts_count(conn, match: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM points_fts WHERE points_fts MATCH ?",
                        (match,)).fetchone()[0]


def _conn(db):
    return db._conn


# ── A.2: verify() (SURG-07) ────────────────────────────────────────────────


async def test_verify_clean_db_passes(db, engine):
    await _seed(db, "p1", "contenido limpio de prueba")
    rep = engine.verify()
    assert rep.passed and rep.fts_missing == 0 and rep.fts_orphans == 0


async def test_verify_detects_fts_orphans(db, engine):
    await _seed(db, "p1", "contenido")
    _conn(db).execute("INSERT INTO points_fts(rowid, content) VALUES (9999, 'fantasma')")
    rep = engine.verify()
    assert not rep.passed and rep.fts_orphans == 1


async def test_verify_detects_fts_missing(db, engine):
    await _seed(db, "p1", "contenido sin indexar")
    _conn(db).execute("DELETE FROM points_fts")
    rep = engine.verify()
    assert not rep.passed and rep.fts_missing == 1


async def test_verify_detects_dangling_relations(db, engine):
    c = _conn(db)
    c.execute("INSERT INTO entities(id, name, type, agent_scope, layer, first_seen, last_seen) "
              "VALUES ('sc:entA', 'entA', 'concept', 'sc', 1, 't', 't')")
    c.execute("INSERT INTO relations(from_entity, to_entity, relation_type, agent_scope, created_at) "
              "VALUES ('sc:entA', 'sc:entFANTASMA', 'uses', 'sc', 't')")
    rep = engine.verify()
    assert not rep.passed and rep.dangling_relations == 1


# ── B.1: delete unitario (SURG-03) ─────────────────────────────────────────


async def test_delete_single_syncs_points_and_fts(db, engine):
    await _seed(db, "p1", "unicum eliminable xyz")
    r = engine.delete_single("p1")
    assert r.ok
    c = _conn(db)
    assert c.execute("SELECT COUNT(*) FROM points WHERE id='p1'").fetchone()[0] == 0
    assert _fts_count(c, "unicum") == 0


async def test_delete_single_not_found_graceful(db, engine):
    r = engine.delete_single("no-existe")
    assert not r.ok and r.error == "not_found" and r.audit_event["reason"] == "not_found"


# ── B.2/B.3: edición y redacción (SURG-04/05, STO-09) ─────────────────────


async def test_edit_payload_resyncs_fts(db, engine):
    await _seed(db, "p1", "contenido original viejo")
    r = engine.edit_payload("p1", {"content": "contenido nuevo reemplazado"})
    assert r.ok
    c = _conn(db)
    assert _fts_count(c, "viejo") == 0, "el índice conservó el término antiguo"
    assert _fts_count(c, "reemplazado") == 1


async def test_update_payload_tool_resyncs_fts(db, engine):
    """STO-09 vía el camino MCP (update_payload), no solo el motor."""
    await _seed(db, "p1", "texto pre edicion zeta")
    ok = await db.update_payload("p1", {"content": "texto post edicion alfa"})
    assert ok
    c = _conn(db)
    assert _fts_count(c, "zeta") == 0
    assert _fts_count(c, "alfa") == 1


async def test_redact_removes_original_from_index_keeps_trace(db, engine, tmp_path):
    await _seed(db, "p1", "secreto nuclear muy sensible")
    r = engine.redact("p1")
    assert r.ok
    c = _conn(db)
    assert _fts_count(c, "nuclear") == 0
    payload = json.loads(c.execute("SELECT payload FROM points WHERE id='p1'").fetchone()[0])
    assert payload["content"] == "[REDACTED]"
    # trazabilidad: el original solo sobrevive en el bundle
    bundle_lines = Path(r.backup_path).read_text().splitlines()
    bundle = json.loads(bundle_lines[1])
    assert "secreto nuclear" in bundle["row"]["payload"]


# ── B.4: move_scope (SURG-10, ISO-18) ──────────────────────────────────────


async def test_move_scope_requires_confirm(db, engine):
    await _seed(db, "p1", "x")
    with pytest.raises(ValueError):
        engine.move_scope("p1", "private-scope")


async def test_move_scope_wrong_confirm_rejected(db, engine):
    await _seed(db, "p1", "x")
    with pytest.raises(ValueError):
        engine.move_scope("p1", "private-scope", confirm="hash-falso")


async def test_move_scope_updates_engine_columns(db, engine):
    await _seed(db, "p1", "x", scope="shared")
    ch = canonical_hash({"point_id": "p1", "to_scope": "private-scope"})
    r = engine.move_scope("p1", "private-scope", to_user="agente-1", confirm=ch)
    assert r.ok
    row = engine._point_row("p1")
    assert row["agent_scope"] == "private-scope" and row["user_id"] == "agente-1"
    payload = json.loads(row["payload"])
    assert payload["agent_scope"] == "private-scope"


# ── Aislamiento (delta ISO-18) ─────────────────────────────────────────────


async def test_expected_scope_mismatch_rejected(db, engine):
    await _seed(db, "p1", "de otro agente", scope="private-scope")
    with pytest.raises(PermissionError):
        engine.delete_single("p1", expected_scope="shared")


# ── A.3: backup + undo (SURG-06/14) ────────────────────────────────────────


async def test_backup_bundle_created_on_delete(db, engine):
    await _seed(db, "p1", "contenido con backup pendiente")
    r = engine.delete_single("p1")
    assert r.backup_path and list(engine.list_backups())


async def test_undo_restores_exact_state(db, engine):
    await _seed(db, "p1", "contenido restaurable unico")
    r = engine.delete_single("p1")
    assert r.ok
    u = engine.undo(r.op_id)
    assert u.ok
    c = _conn(db)
    row = c.execute("SELECT payload FROM points WHERE id='p1'").fetchone()
    assert row and "restaurable" in row[0]
    assert _fts_count(c, "restaurable") == 1  # índice también restaurado


async def test_undo_idempotent(db, engine):
    await _seed(db, "p1", "idempotencia de undo q7")
    r = engine.delete_single("p1")
    engine.undo(r.op_id)
    u2 = engine.undo(r.op_id)  # segunda vez: INSERT OR REPLACE, sin duplicado
    assert u2.ok
    c = _conn(db)
    assert c.execute("SELECT COUNT(*) FROM points WHERE id='p1'").fetchone()[0] == 1


async def test_undo_corrupt_bundle_fails_closed(db, engine):
    await _seed(db, "p1", "x")
    r = engine.delete_single("p1")
    path = engine._backup_dir / f"{r.op_id}.jsonl"
    path.write_text("{json roto")
    u = engine.undo(r.op_id)
    assert not u.ok and "corrupt bundle" in u.error


# ── B.5: reindex y purga (SURG-08/09) ──────────────────────────────────────


async def test_reindex_repairs_missing_fts(db, engine):
    await _seed(db, "p1", "contenido a reindexar omega")
    _conn(db).execute("DELETE FROM points_fts")
    r = engine.reindex(["p1"])
    assert r.ok and _fts_count(_conn(db), "omega") == 1


async def test_purge_orphans_dry_run_then_delete(db, engine):
    await _seed(db, "p1", "real")
    c = _conn(db)
    c.execute("INSERT INTO points_fts(rowid, content) VALUES (9999, 'fantasma')")
    c.execute("INSERT INTO entities(id, name, type, agent_scope, layer, first_seen, last_seen) "
              "VALUES ('sc:sola', 'sola', 'concept', 'sc', 1, 't', 't')")
    c.execute("INSERT INTO relations(from_entity, to_entity, relation_type, agent_scope, created_at) "
              "VALUES ('sc:sola', 'sc:ghost', 'uses', 'sc', 't')")
    dry = engine.purge_orphans(dry_run=True)
    assert dry["deleted"] == 0 and len(dry["orphan_fts_rowids"]) == 1 and len(dry["dangling_relations"]) == 1
    real = engine.purge_orphans(dry_run=False)
    assert real["deleted"] == 2 and real["verify"]["passed"]
    assert c.execute("SELECT COUNT(*) FROM points WHERE id='p1'").fetchone()[0] == 1


# ── SURG-12: auditoría ─────────────────────────────────────────────────────


async def test_audit_event_shape(db, engine):
    await _seed(db, "p1", "auditado")
    r = engine.delete_single("p1")
    ev = r.audit_event
    assert ev["ok"] is True and ev["action"] == "delete" and ev["op_id"] == r.op_id
    assert "content" not in json.dumps(ev)  # sin contenido en auditoría
