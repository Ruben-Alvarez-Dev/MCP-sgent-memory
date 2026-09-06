# Proposal: M2-storage — memory.db unificado + demolición de Qdrant

## Intent
Unificar el almacenamiento disperso (Qdrant HTTP + conversations.db + JSONL) en
un único `memory.db` (SQLite, stdlib puro), mover TODO el filtrado de scope al
motor (SQL WHERE con binding, jamás post-filtro Python), prohibir zero-vectors
persistidos, y demoler Qdrant y sus 4 módulos cliente. Re-auditoría G-ISOLATION
completa con los adversariales diferidos de M1 (A3/A5/A6/A10/A14/A15).

## Contexto que justifica
La BD real tiene ~2 puntos (un solo usuario). Qdrant es un daemon HTTP con un
puerto, logs de 110KB y 4 módulos cliente (uno muerto: ISO-08). El vector denso
de 1024 dims se puede puntuar por fuerza bruta en stdlib sobre candidatos ya
filtrados por SQL — sin numpy, sin sqlite-vec, sin puertos nuevos (regla
openspec: no daemons/puertos sin aprobación).

## Capabilities
- Modified: `storage` (STO-01..05 reemplazados: SQLite único, engine-level filter,
  NULL-vectors obligatorio, JSONL queda como fallback de ingesta, FS bajo jail).
- Modified: `isolation` (ISO-05 enforcement al motor; ISO-06 writes mixtos
  eliminados; ISO-07 jail FS; ISO-08 código muerto borrado).
- Modified: `retrieval` (RET-01 backend cambia; RET-06 pasa a M3 sin cambios).

## Tenants/scopes afectados e impacto de aislamiento
Todos los scopes. Impacto: estrictamente reductor — enforcement sube de
post-filtro Python a WHERE con binding; se eliminan writes cross-scope de
consolidación; el FS de vault/decisions queda bajo jail. Ningún ensanchamiento.

## Rollback plan
Revert del commit: los módulos Qdrant borrados vuelven (git), `data/memory.db`
se descarta (regenerable desde events.jsonl + re-embed), `conversation_db.py`
recupera su path propio. Sin pérdida de datos: L0 JSONL es la fuente de verdad
de ingesta (STO-03) y vault/decisions son ficheros.

## Fuera de alcance (con dueño)
- Sparse read path (RET-05) → M3. L5 raising embed (RET-06/KNOWN-BUG-002) → M3.
- Ranking LLM (RET-04/KNOWN-BUG-003) → M3. Identidad real (ISO-01) → M4.
- global/merged con provenance (ISO-06 resto) → M5. A11/A12/A16 → M5.
