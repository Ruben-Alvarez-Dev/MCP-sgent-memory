# Auditoría de aislamiento — L3_facts y Retrieval Router (ISO-05 / L-F1)

Lectura completa de ambos ficheros + clientes Qdrant + specs openspec + tests. Sin ediciones, sin git.

## Tabla 1 — `src/L3_facts/server/main.py` (colección única Qdrant `L3_facts`)

| path | función | backend | filtro hoy | enforcement necesario |
|---|---|---|---|---|
| :21–31 (upsert :29–30) | `add_memory` (W) | Qdrant | **Nada** — `user_id` pasa por `sanitize_user_id` (sanitizer que **remapea**, no rechaza) y se graba como payload | **Raw-before-sanitize**: `normalize_scope(user_id)` ANTES del sanitizer (paridad con `push_reminder` en L5, que sí lo hace); scope explícito obligatorio (patrón ISO-12) |
| :34–43 (search :41, post-filtro :42) | `search_memory` (R) | Qdrant | ❌ **Post-filtro Python (L-F1)** — `qdrant.search()` se llama **sin** `filter`; el filtrado por `user_id` ocurre tras recuperar resultados | Pasar `{"must":[{"key":"user_id","match":{"value":user_id}}]}` al `filter` del engine (la firma de `QdrantClient.search` ya lo soporta, qdrant_client.py:259–276) y **eliminar** la línea 42. Plan M2: `MemoryDB.search` con `WHERE user_id=?` bound param |
| :46–49 (scroll :48) | `get_all_memories` (R) | Qdrant | ✅ **Engine-level** — el filter `must/user_id` se envía dentro del body de `/points/scroll` | Ya cumple; falta validar `user_id` crudo antes de construir el filtro (hoy ni se sanitiza: valor vacío/remapeado produce lecturas de bucket no previsto) |
| :52–60 (get :54, check :55, delete :56) | `delete_memory` (D) | Qdrant | ⚠️ **Check-then-act en Python (TOCTOU)** — `get()` sin filtro, comparación de payload en Python, luego delete por ID | Delete atómico en el engine: Qdrant soporta `POST /points/delete` con `filter` (id + user_id juntos), o en M2 `DELETE ... WHERE id=? AND user_id=?` |
| :63–67 (count :66) | `status` (R agregado) | Qdrant | **Nada** — `count()` cuenta la colección entera (todos los usuarios) | Count con filter por scope si se quiere cerrar el oráculo de cardinalidad cross-user |
| :69–74 | `register_tools` | — | Rebind global de `qdrant`/`config` (ignora `target_qdrant` y crea uno nuevo) | N/A — pero es el punto por donde el unified server mete este módulo en el hot path; hereda todos los gaps anteriores |

## Tabla 2 — `src/shared/retrieval/__init__.py`

| path | función | backend | filtro hoy | enforcement necesario |
|---|---|---|---|---|
| :171–190 | `retrieve` (orquestador) | — | Propaga `agent_scope` autodeclarado, **sin validación** (`validate_request_context` en L5 solo valida query/intent) | `normalize_scope(agent_scope)` fail-closed en la entrada |
| :193–224 | `_retrieve_parallel` (fan-out) | Qdrant + FS | Propaga `agent_scope` a todos los subpaths | Cubierto por los subpaths |
| :230–280 (target_coll :246, filter :247–251, search :258) | `_retrieve_hybrid` (R denso) — L0/L1/L2/L3/L4/L5 | Qdrant | ⚠️ **Engine-level por nombre de colección**: scope ≠ shared → colección `{base}_{scope}` (:246). El `filter` que llega al engine es **solo `layer`** (:247–251), nunca scope. La garantía depende 100 % de que cada colección-sufijo contenga solo datos de ese scope | (a) `normalize_scope` antes de construir `target_coll` — hoy un `agent_id` malicioso se incrusta **en la URL HTTP** del nombre de colección (inyección de nombre de colección); (b) mapa cerrado/allowlist de colecciones accesibles (hoy `_get_scoped_client` :49 cachea y crea clientes para cualquier scope); (c) decidir semántica own+shared merge |
| :282–308 (iter :291) | `_retrieve_L3_decisions` (R) | **Ficheros** (.md) | ✅ **Engine-level (jail FS)** — `iter_namespaced_files` (scope.py:110–132): `normalize_scope` fail-closed + árbol shared excluyendo `_scopes/` + directorio propio. ISO-04 cerrado en M1 | Residual: endurecer con `resolve()`+symlink-check (`scope_jail_path`, ya planificado como ISO-07 en M2) |
| :311–486 | `_rank_and_fuse`, `_pack_context`, etc. | — (sin I/O de store) | N/A | N/A |

## `scoped_qdrant.py` / `hybrid_qdrant.py` — tests y hot path

- **Tests propios**: sí — `tests/core/test_agent_scope_qdrant.py` (7 tests). Pero **4 de 6 tests de cliente llevan `@requires_qdrant`** (skip si no hay Qdrant en :6333 → no CI-puros); solo `test_parse_agent_level` y `test_level_map` corren sin servicio.
- **¿Los usa el hot path?** **No** (ISO-08, confirmado): grep en `src/` muestra import únicamente desde el propio test. El hot path real (`L5_routing/server/main.py:95` → `retrieve()`) construye el scoping inline (`_retrieve_hybrid` :246 y `qdrant.with_collection(...)` en L5:116,154). **Decoración pura**: tests verdes que prueban clientes que nadie usa.
- Cobertura de L3_facts en tests: casi nula (solo `status` en test_mcp_modules.py:81). **No existe test adversarial cross-user de `search_memory`** — L-F1 está abierto y sin red de pruebas.

## Riesgos

1. **L-F1 abierto (MEDIUM, ya inventariado)** — el post-filtro de `search_memory` (:42) no es enforcement: con `limit=5`, si los 5 mejores son de otro usuario devuelves 0 resultados aunque el tuyo exista (fallos de disponibilidad), y scores/latencia/timing filtran presencia de datos ajenos (oráculo). `min_score` se evalúa sobre datos ajenos antes de filtrar.
2. **Inyección de nombre de colección (nuevo, HIGH)** — `agent_scope` llega crudo desde `request_context` (que no valida `agent_id`) y se concatena al nombre de colección que viaja en la URL HTTP (:246, :49; ídem L5:116). Un scope malformado (`../`, `shared`, query-params) redirige la lectura a otra colección o manipula la petición. Es exactamente el patrón traversal-via-remap/scope-falsificado del skill (Phase 5).
3. **TOCTOU en `delete_memory`** — la comprobación Python (:55) y el delete (:56) no son atómicos.
4. **Oráculo de cardinalidad** — `status()` expone el conteo global de la colección.
5. **Bugs de corrección en el código decorativo** — `ScopedQdrantClient.search` descarta puntos sin `thread_id`; `HybridQdrantClient.scroll` post-filtra `agent_scope` **en Python** (decoración dentro del propio cliente aislador, y con `limit` aplicado *antes* de filtrar: mismo bypass de paginación que L-F1).
6. **L-ID0 (CRITICAL estructural)** — sin capa de identidad: todos los scopes son autodeclarados. Hasta M4, cualquier enforcement (incluido el engine-level pedido) es *advisory*.
7. **Riesgo de transición M2** — el delta spec de M2 borra Qdrant completo (incluidos estos clientes y sus tests) y sustituye por `MemoryDB` SQLite. Los tests `@requires_qdrant` morirán con él; el cierre de ISO-05 queda entonces condicionado a que `tests/adversarial/test__ISO05__engine_filter.py` (planeado, casos A3/A10) exista antes del cutover — si no, se reabre el hueco silenciosamente.

**Conclusión por celda**: engine-level ✅ en `get_all_memories` y `_retrieve_L3_decisions`; post-filtro ❌ en `search_memory` (L-F1); check-then-act ⚠️ en `delete_memory`; nada en `status` y en la validación de scope de `_retrieve_hybrid`; y dos clientes "aisladores" con tests verdes que el hot path nunca importa (ISO-08).
