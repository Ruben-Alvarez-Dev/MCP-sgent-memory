# Design — surgical-memory-ops

## 1. Arquitectura orgánica (5 grupos serializados)

```
Grupo A — FUNDAMENTOS (nada encima sin esto)
  shared/surgical.py: SurgicalEngine
  ├─ invariantes + verify() + integrity gate
  ├─ backup bundles (JSONL) + undo()
  └─ locking (hereda MemoryDB._write_lock)
Grupo B — OPERACIONES UNITARIAS (sobre A)
  delete_single · edit_payload · redact · move_scope
  reindex(ids) · purge_orphans
Grupo C — OPERACIONES MASIVAS (sobre B)
  plan(filter) → plan_id + hash
  execute(plan_id, confirm) → drift-check + transacción
  presupuestos (SURGICAL_MAX_BULK) + ack reforzado
Grupo D — SUPERFICIE (sobre A+B+C)
  REST /api/surgical/* (webui) · CLI scripts/surgical.py
  pantallas UI: panel quirúrgico con dry-run visual
Grupo E — VERIFICACIÓN Y GATE (sobre todo)
  tests unit + contract + adversarial · GATE firmado
```

Dependencia estricta: cada grupo solo se construye sobre el anterior
verificado. Nada de UI antes de que el motor garantice invariantes.

## 2. Modelo de operación

```python
op = engine.plan(action, filter)          # → Plan(plan_id, ids, sha256, counts)
op.dry_run()                              # → sin efectos (SURG-02)
op.execute(confirm=hash)                  # → backup → transacción → verify → audit
engine.undo(op_id)                        # → restore idempotente (SURG-06/14)
engine.verify()                           # → informe de invariantes (SURG-07)
```

Acciones: `delete` · `edit_payload(patch|replace)` · `redact(mask)` ·
`move_scope(to_scope, to_user)` · `reindex` · `purge_orphans`.
Cada acción = un dataclass con `validate()` propio; el motor no acepta dicts
sueltos (fail-closed ante UI/CLI malformadas).

## 3. Integridad — implementación de los deltas

- **STO-09**: `_update_payload_one` llama a `_sync_fts_upsert(point_id, nuevo
  payload_json)` dentro de su `with self._lock, self._conn` (misma transacción).
- **STO-10**: `_delete_one` tras el DELETE de points y points_fts ejecuta
  `DELETE FROM entities WHERE point_id=?` y
  `DELETE FROM relations WHERE src_point_id=? OR dst_point_id=?` (columnas a
  confirmar contra el schema real en F0; si el grafo usa claves distintas, se
  documenta ahí mismo).
- **STO-11**: `verify()` del subconjunto: por cada id tocado, rowid en fts
  presente y MATCH del token índice; `PRAGMA integrity_check` al cerrar.
  Fallo → `conn.rollback()` + restore desde bundle + estado `needs_attention`.

## 4. Backups

`data/surgical/backups/<op_id>.jsonl` — una línea por fila afectada:
`{"table": "...", "row": {...}, "fts_content": "..."}` + línea cabecera con
op_id, acción, filtro-hash, ts. `undo()` re-lee y reconstruye (idempotente:
upsert por clave primaria). Retención: 90 días (mismo ciclo que lifecycle.sh,
F4 añade la regla). Los bundles NUNCA se sirven por la UI (descarga local por
CLI si se quiere inspeccionar).

## 5. Modos de fallo y adversarios

| Amenaza | Defensa |
|---|---|
| Drift plan↔ejecución (agente escribe entre medias) | re-verificación de ids en la transacción; drift>0 → abort por defecto (configurable) |
| Filtro mal construido borra de más | dry-run obligatorio previo para masivos; MAX_BULK + ack reforzado (SURG-13); sin `scope` explícito → rechazo |
| Crash a mitad de transacción | SQLite transaccional: rollback; backup deja el estado previo reconstruible |
| UI/exploit manda JSON hostil | dataclasses con validate(); SQL parametrizado; jamás interpolación |
| Undo corrupto | fail-closed (SURG-14); verify() como autoridad del estado |
| DoS por masivos repetidos | MAX_BULK + rate básico en la capa UI (webui F4) |
| Exfiltración vía bundles | bundles solo en disco local 0600, nunca endpoint de lectura |

## 6. Impacto en otros componentes

- Web UI: nueva sección "Quirúrgico" (dry-run visual: tabla de ids afectados +
  hash + botón execute deshabilitado sin confirm). No sustituye el borrado
  simple del explorador (ese sigue usando delete unitario directo).
- MCP: las tools existentes NO cambian de contrato; `delete_memory` gana la
  purga de grafo (STO-10) de forma transparente.
- lifecycle.sh: nueva regla de retención de bundles (90d) en F4.
