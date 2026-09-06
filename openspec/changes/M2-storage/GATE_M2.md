# GATE_M2 — storage: memory.db unificado + demolición de Qdrant

Estado: PASS (GO)
Fecha: 2026-09-06
Firma QA: arquitecto (246 passed / 1 failed-KNOWN-003 / 6 skipped + 69 adversarial verificados)
Firma Owner (arquitecto): arquitecto

## Checks automáticos
- [x] `pytest tests/adversarial -q` → **69 passed** (46 M1 + 19 ISO-05/A3+A10 + 4 ISO-06), 0 servicios
- [x] `pytest tests/ -q` → **246 passed, 1 failed (KNOWN-BUG-003 preexistente, owner M3), 6 skipped (legacy v3)** — baseline M0 (167) ampliada, sin regresiones
- [x] `pytest tests/app -q` → **3 passed** — suite app reescrita sobre memory.db, **KNOWN-BUG-001 CERRADO** (sin puertos, sin :8081/:8091)
- [x] `ruff check` ficheros NUEVOS (`memory_db.py`, `test_memory_db.py`, `test_memory_db_e2e.py`, `migrate_to_memory_db.py`) → **limpio**; F821 en tocados → 0
- [x] Ruff preexistente intacto (stat documentado: BLE001×28, I001×23, F401×18… deuda heredada, sin violaciones NUEVAS)
- [x] `grep -rn qdrant src/ --include=*.py` → **0 llamadas vivas** (solo: params posicionales `target_qdrant` por compat de firma, nombre legacy `qdrant_collection`, comentarios, y 1 string inerte de exclusión de dirs en code_map:637)
- [x] Demolición física: `qdrant_client/qdrant_factory/scoped_qdrant/hybrid_qdrant/index_repo/main_http/backpack.py` BORRADOS; `bin/qdrant`, `src/shared/qdrant/`, `data/qdrant/`, `qdrant.log`, `etc/qdrant.yaml`, `start-qdrant.sh` BORRADOS; scripts shell podados (grep residual 0)
- [x] STO-05 verificado: zero-vector jamás persistido (test), hash-vector determinista y estable
- [x] ISO-05 engine-level verificado con spy: filas foráneas jamás cargadas a scoring (A3)
- [x] ISO-06: promociones = no-ops WARN; cero filas scope_id mixto tras pipeline completo (test adversarial)
- [x] STO-06: migración events.jsonl idempotente (2 runs → mismo count, sin duplicados), sin leer Qdrant

## Checklist humana
- [x] **Contrato M1 ampliado, no roto**: `a:b` pasa de inválido a válido por namespace 5 niveles; test M1 actualizado con nota de contrato (no silenciado)
- [x] Hallazgos adversariales integrados: TOCTOU en delete → `delete(id, filter)` atómico; inyección de nombre de colección en `_retrieve_hybrid` → `normalize_scope` en entrada + filtro engine (hallazgo NUEVO del análisis, cerrado)
- [x] Semántica own+shared unificada: retrieval, L2 y L5 ahora filtran `agent_scope IN (own, shared)` por motor — fin de las colecciones por sufijo `_scope` (más superficie imposible de enumerar mal)
- [x] `update_payload`/`_set_payload_sync` preservan el vector (verificación v1.4 ya no lo destruye)
- [x] Deviación registrada: columnas reales `agent_scope/user_id/layer` + allowlist ISO-11 en vez de `json_extract` (índice con json_extract falla con payload corrupto — hallazgo TDD, design.md §Decisiones 1b)
- [x] Diferidos con dueño: sparse read path RET-05 → M3 · L5 raising embed RET-06/KNOWN-BUG-002 → M3 · ranking RET-04/KNOWN-BUG-003 → M3 · identidad ISO-01 → M4 · global/merged con provenance ISO-06-resto/A11/A12/A16 → M5 · sqlite-vec si >50k puntos (health reportará scan_ms) → futuro
- [x] Rollback verificado: revert de commits + `scripts/migrate_to_memory_db.py` reconstruye desde events.jsonl
- [x] Re-auditoría G-ISOLATION: ISO-01 (M4) · ISO-02 intacto · ISO-03/04 (M1) · **ISO-05 enforced** · **ISO-06 enforced (no-op)** · **ISO-07 jail** · **ISO-08 demolido** · ISO-09/10 (M1+M2 5 niveles) · **ISO-11 ADDED** · **ISO-12 ADDED**

## Decisión
- [x] GO → se abre M3-retrieval (sparse read path, degradación L5, juicios eval-40, cierre KNOWN-BUG-002/003)
- [ ] NO-GO: —
