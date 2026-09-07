# Tasks — surgical-memory-ops (serializadas en grupos orgánicos)

> Regla de serie: el grupo N no abre PR hasta que el grupo N-1 tenga sus tests
> en verde. Sin saltos. Sin "ya lo afino después".

## Grupo A — Fundamentos del motor (invariantes primero)
- [ ] A.1 Confirmar schema real de `entities`/`relations` (claves hacia points) y documentarlo en design.md — criterio: sentencias DELETE de cascade escritas contra columnas reales
- [ ] A.2 `shared/surgical.py`: `SurgicalEngine` con `verify()` completo (SURG-07: fts↔points bidireccional, grafo sin colgantes, integrity_check) — criterio: detecta las 4 corrupciones inyectadas artificialmente
- [ ] A.3 Backup bundles JSONL + `undo(op_id)` (SURG-06/14) — criterio: undo tras delete restaura fila+FTS exactos; bundle corrupto → error explícito
- [ ] A.4 Integrity gate transaccional (STO-11): abort+rollback+restore en fallo — criterio: test fuerza fallo de verify y el estado previo se recupera
- [ ] A.5 Suite del grupo A (`tests/unit/test_surgical_engine.py`) — criterio: ≥8 tests verdes

## Grupo B — Operaciones unitarias (sobre A)
- [ ] B.1 `delete_single` con cascade de grafo (STO-10) + purga FTS — criterio: SURG-03 verde
- [ ] B.2 `edit_payload` con re-sync FTS (STO-09) — criterio: SURG-04 verde; también en `_update_payload_one` del MCP path
- [ ] B.3 `redact(mask)` (SURG-05) — criterio: tokens originales fuera del índice, trazabilidad en backup+L0
- [ ] B.4 `move_scope` (ISO-18/SURG-10) — criterio: WHERE con scope origen; adversarial de cruce de scope rojo
- [ ] B.5 `reindex(ids|all)` + `purge_orphans` (SURG-08/09) — criterio: reparan drift inyectado y never tocan points válidos
- [ ] B.6 Suite del grupo B — criterio: ≥10 tests verdes, 0 regresión en suite completa

## Grupo C — Operaciones masivas (sobre B)
- [ ] C.1 `plan(filter)` → plan_id + ids + sha256 + counts (SURG-01) — criterio: hash estable ante re-plan del mismo estado
- [ ] C.2 `execute(plan_id, confirm)` con drift-check en transacción — criterio: SURG-01/02/11 verdes; drift>0 aborta
- [ ] C.3 Presupuestos: MAX_BULK + ack reforzado (SURG-13) — criterio: 501 filas sin ack → rechazo con contador
- [ ] C.4 Auditoría L0 por operación (SURG-12) — criterio: evento con op_id/hash/ids sin contenido
- [ ] C.5 Suite del grupo C — criterio: ≥8 tests verdes incl. concurrencia (SURG-11)

## Grupo D — Superficie (sobre C)
- [ ] D.1 REST `/api/surgical/plan|execute|undo|verify|orphans` (webui) — criterio: contract tests del webui en verde
- [ ] D.2 Panel quirúrgico UI: dry-run visual (tabla ids + hash + execute bloqueado sin confirm) — criterio: flujo manual plan→dry→execute→verify sin consola
- [ ] D.3 CLI `scripts/surgical.py` (mismas ops para humanos sin UI) — criterio: paridad de ops con REST
- [ ] D.4 Explorador de memorias (webui F1) pasa a usar delete unitario del motor — criterio: purga de grafo visible en verify

## Grupo E — Verificación y gate (sobre D)
- [ ] E.1 Adversarial quirúrgico: inyección de filtros, cruce de scopes, TOCTOU con escrituras MCP concurrentes, bundles hostiles — criterio: ≥10 adversariales rojo→verde
- [ ] E.2 Re-firma G-ISOLATION con la batería ampliada — criterio: 151+ tests adversariales en verde
- [ ] E.3 lifecycle.sh: retención 90d de bundles — criterio: dry-run lista bundles viejos sin borrarlos
- [ ] E.4 GATE: evidencia completa (benchmarks de masa, matrices de invariantes) y firma GO/NO-GO
