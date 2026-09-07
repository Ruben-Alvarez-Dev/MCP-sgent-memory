# Specs — storage (deltas)

## STO-09 — Edición de payload re-sincroniza FTS (delta de STO-07)

**Given** `_update_payload_one` modifica el campo `content` de un punto,
**When** el update se confirma,
**Then** `_sync_fts_upsert` se ejecuta en la misma transacción con el payload
resultante (reemplazo DELETE+INSERT del rowid).
Test: `test_update_payload_resyncs_fts_same_transaction`

## STO-10 — Integridad del grafo sin FK (corregido por A.1)

**Given** que `entities` NO tiene FK hacia points (grafo standalone: id =
`{agent_scope}:{name.lower()}`, extracción por contenido) y `relations`
referencia entidades (no puntos),
**When** se elimina un punto o una entidad,
**Then** NO hay cascade silenciosa (Chesterton's fence): la integridad del
grafo se mantiene con dos operaciones quirúrgicas explícitas —
`purge_orphans` (relations con endpoints inexistentes, anti-join barato) y
`purge_unreferenced_entities` (entidades sin mención en points vivos,
escaneo caro opcional `verify(full=True)`). Un punto borrado NO invalida
relaciones (otro punto puede seguir mencionando la entidad).
Test: `test_purge_orphans_dry_run_then_delete` + `test_verify_detects_dangling_relations`

## STO-11 — `integrity_check` como invariante operativa

**Given** cualquier escritura del motor quirúrgico,
**When** la transacción termina,
**Then** `PRAGMA integrity_check` + verificación bidireccional points↔fts del
subconjunto afectado pasan; en fallo, rollback automático y restore desde
backup (SURG-06).
Test: `test_integrity_gate_aborts_and_restores`
