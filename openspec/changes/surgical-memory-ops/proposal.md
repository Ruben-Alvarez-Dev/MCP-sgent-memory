# Proposal: surgical-memory-ops

**Fecha:** 2026-09-07 · **Depende de:** webui-management (es su capa de motor)
**Tipo:** nueva capacidad (`surgical`) + deltas de `storage` + delta `ISO`

## Problema

La gestión manual de memorias hoy permite corromper el sistema de tres formas
verificadas en el código:

1. **Drift de índice**: `_update_payload_one` edita el payload sin re-sincronizar
   `points_fts` → la búsqueda indexa contenido obsoleto.
2. **Referencias colgantes**: borrar un punto no limpia `entities`/`relations`
   → grafo de entidades con nodos huérfanos que crece sin límite.
3. **Masivos a ciegas**: un DELETE por filtro puede tocar más filas de las
   previstas (drift entre vista previa y ejecución, TOCTOU con agentes
   escribiendo a la vez).

Un sistema de gestión que corrompe al corregir es peor que no existir.

## Objetivo

Motor quirúrgico (`shared/surgical.py`) con **garantías de integridad
verificables** para eliminar y manipular memorias de forma unitaria o masiva:
toda operación sigue el ciclo `plan → dry-run → execute → verify → audit`,
con backup previo y undo. La Web UI (webui-management) es su vehículo; el
motor también es invocable por CLI y tests.

## Capabilities

- **new** `surgical`: operaciones quirúrgicas atómicas con invariantes,
  backup/undo y verificación (SURG-01…SURG-14).
- **modified** `storage` (deltas STO-09/10/11): re-sync FTS en edición de
  payload; cascade/purga de entities-relations; `integrity_check` como
  invariante post-operación.
- **modified** `ISO` (delta ISO-18): toda operación quirúrgica masiva exige
  scope explícito y ejecuta su filtro a nivel engine (nunca post-filtro).

## Impacto de aislamiento

Las operaciones unitarias operan sobre un punto concreto (sin cruce). Las
masivas exigen `scope` explícito en el filtro y el `confirm-hash` del plan
(sin hash no hay ejecución). El undo restaura exactamente el estado previo
(mismo scope). G-ISOLATION se re-firma con la batería adversarial ampliada.

## Rollback

Motor autónomo en `shared/surgical.py` + endpoints `/api/surgical/*`: revert
del commit lo desactiva sin tocar el camino MCP. Cada operación deja backup
JSONL restaurable con `undo(op_id)` incluso tras revert (formato estable).
