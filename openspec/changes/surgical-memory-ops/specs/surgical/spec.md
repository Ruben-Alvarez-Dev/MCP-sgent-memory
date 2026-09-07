# Specs — surgical (capacidad nueva)

Convención: `engine filter` = el filtro vive en la sentencia SQL, nunca en
post-filtro Python. Toda operación quirúrgica es atómica (una transacción).

## SURG-01 — Ciclo plan → dry-run → execute → verify → audit

**Given** un filtro de selección masiva (scope + criterio),
**When** el motor planifica,
**Then** devuelve un `plan_id` con la lista exacta de ids afectados, tamaño
estimado y hash SHA-256 del conjunto; **Given** ese `plan_id`,
**When** se ejecuta con `confirm=<hash>`,
**Then** solo se modifican los ids del plan re-verificados como existentes en
la MISMA transacción (anti-TOCTOU); el drift (ids desaparecidos desde el plan)
se reporta y aborta si supera el 0% por defecto.
Test: `test_surgical_plan_execute_roundtrip`

## SURG-02 — Dry-run sin efectos

**Given** cualquier operación masiva,
**When** se llama con `dry_run=True`,
**Then** no hay escritura en points/fts/entities/relations ni en L0 (solo el
plan persistido), y la respuesta contiene la misma lista de ids que la
ejecución posterior.
Test: `test_surgical_dry_run_side_effect_free`

## SURG-03 — Delete unitario con verificación

**Given** un `point_id` existente,
**When** se elimina quirúrgicamente,
**Then** desaparece de `points` Y de `points_fts` (0 huérfanos) y sus
entities/relations asociadas se purgan (STO-10) en la misma transacción.
Test: `test_surgical_delete_single_invariants`

## SURG-04 — Edición de payload con re-sync FTS (delta STO-09)

**Given** un punto cuyo contenido se edita,
**When** la edición se confirma,
**Then** `points_fts` contiene EXACTAMENTE los tokens del contenido nuevo
(bidireccional: sin tokens viejos, sin faltantes) en la misma transacción.
Test: `test_surgical_edit_resyncs_fts`

## SURG-05 — Redacción (redact) con trazabilidad

**Given** un punto con contenido sensible,
**When** se redacta (replace del campo content por máscara),
**Then** el índice FTS se re-sincroniza con la máscara, el original SOLO
sobrevive en el backup de la operación y en L0 auditoría (metadato, no texto).
Test: `test_surgical_redact_removes_from_index_keeps_trace`

## SURG-06 — Backup previo universal y undo

**Given** cualquier operación de escritura quirúrgica,
**When** se ejecuta,
**Then** antes del commit se persiste un bundle JSONL
(`data/surgical/backups/<op_id>.jsonl`: filas completas de points, fts,
entities, relations afectadas) y `surgical.undo(op_id)` restaura el estado
previo exacto (re-crear filas + re-sincronizar FTS) de forma idempotente.
Test: `test_surgical_undo_restores_exact_state`

## SURG-07 — Verificación de invariantes post-op (delta STO-11)

**Given** cualquier operación completada,
**When** `surgical.verify()` analiza la DB,
**Then** comprueba: (a) bidireccional points↔points_fts, (b) entities/
relations sin referencias a ids inexistentes, (c) `PRAGMA integrity_check=ok`,
(d) contadores points== esperados del plan. Cualquier fallo → la operación se
marca `needs_attention` y la UI lo muestra en rojo.
Test: `test_surgical_verify_detects_each_corruption`

## SURG-08 — Reindexación FTS

**Given** drift entre points y points_fts,
**When** `reindex(ids|all)`,
**Then** el índice se reconstruye desde el payload actual (fuente de verdad:
points) y verify() pasa.
Test: `test_surgical_reindex_repairs_drift`

## SURG-09 — Purga de huérfanos

**Given** filas en entities/relations/points_fts que referencian ids
inexistentes,
**When** `purge_orphans(dry_run)`,
**Then** se listan y se eliminan solo esas filas; nunca toca points válidos.
Test: `test_surgical_purge_orphans_safe`

## SURG-10 — Re-scope controlado (delta ISO-18)

**Given** un punto y un scope/user destino,
**When** `move_scope(id, to_scope, to_user)`,
**Then** el cambio es engine-level (UPDATE con WHERE id+scope originales,
anti-TOCTOU), exige confirm=hash, y genera registro L0 con origen y destino.
Test: `test_surgical_move_scope_enforces_origin`

## SURG-11 — Bloqueo exclusivo por operación

**Given** dos operaciones quirúrgicas simultáneas,
**When** se solapan en el mismo id,
**Then** la segunda espera (MemoryDB._write_lock) y re-valida el plan; jamás
intercalan semitransacciones.
Test: `test_surgical_serializes_concurrent_ops`

## SURG-12 — Auditoría L0 por operación

**Given** cualquier operación ejecutada,
**When** termina,
**Then** L0 recibe un evento `system` con op_id, tipo, filtro-hash, ids
afectados y resultado de verify (sin contenido de memorias).
Test: `test_surgical_audit_trail_complete`

## SURG-13 — Presupuestos de destrucción

**Given** un plan masivo que afecta a más de `MAX_BULK` (default 500, env
`SURGICAL_MAX_BULK`) filas,
**When** se solicita ejecutar,
**Then** exige confirmación reforzada (`confirm` + `acknowledge=REALLY`); la
UI lo hace imposible de pulsar por accidente.
Test: `test_surgical_bulk_requires_enhanced_confirm`

## SURG-14 — Undo con límites declarados

**Given** un op_id con backup,
**When** el bundle falta o está corrupto,
**Then** undo falla con error explícito (nunca restaura a medias) y verify()
sigue siendo la fuente de verdad del estado.
Test: `test_surgical_undo_fails_closed_on_corrupt_backup`
