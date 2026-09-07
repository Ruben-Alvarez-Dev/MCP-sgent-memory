# Specs — storage (deltas)

## STO-09 — Edición de payload re-sincroniza FTS (delta de STO-07)

**Given** `_update_payload_one` modifica el campo `content` de un punto,
**When** el update se confirma,
**Then** `_sync_fts_upsert` se ejecuta en la misma transacción con el payload
resultante (reemplazo DELETE+INSERT del rowid).
Test: `test_update_payload_resyncs_fts_same_transaction`

## STO-10 — Purga de grafo al eliminar punto

**Given** un punto con filas asociadas en `entities`/`relations`,
**When** se elimina el punto,
**Then** sus filas de grafo se purgan en la misma transacción (o se marca
`orphan=true` con purge_orphans posterior documentado — decisión: purge en
línea, el grafo no conserva nodos sin punto fuente).
Test: `test_delete_purges_entity_graph_rows`

## STO-11 — `integrity_check` como invariante operativa

**Given** cualquier escritura del motor quirúrgico,
**When** la transacción termina,
**Then** `PRAGMA integrity_check` + verificación bidireccional points↔fts del
subconjunto afectado pasan; en fallo, rollback automático y restore desde
backup (SURG-06).
Test: `test_integrity_gate_aborts_and_restores`
