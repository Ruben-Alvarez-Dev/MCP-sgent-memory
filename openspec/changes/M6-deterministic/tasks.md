# Tasks: M6-deterministic — Cero embeddings, retrieval 100% lexical

## 1. Schema evolution (STO-07, STO-08, STO-09, STO-10) ✅ COMPLETADO
- [x] 1.1 FTS5 virtual table + sync triggers en `memory_db._ensure_schema`.
  Acept: tests/core/test_fts5_points.py. REQ: STO-07.
- [x] 1.2 Tablas `entities` y `relations` con indexes.
  Acept: tests/core/test_entities_table.py. REQ: STO-08, STO-09.
- [x] 1.3 Tabla `synonyms` seedada con diccionario técnico EN+ES.
  Acept: tests/core tests exist. REQ: STO-10.
- [x] 1.4 `_ensure_schema` idempotente. REQ: STO-07, STO-08.

## 2. Entity extraction determinista ✅ COMPLETADO
- [x] 2.1 `shared/entity.py`: `_extract_entities()` con regex + diccionario.
  Acept: tests/core/test_entity_extraction.py. REQ: STO-08.
- [x] 2.2 Integración en `_prepare_row` → upsert entities table. REQ: STO-08.
- [x] 2.3 Type inference: CamelCase→class, UPPER_SNAKE→module, lowercase→concept. REQ: STO-08.

## 3. Query expansion con synonym dictionary ✅ COMPLETADO
- [x] 3.1 `shared/synonym.py`: `_SYNONYM_MAP` EN+ES + `expand_query()`.
  Acept: tests/core/test_synonym_expansion.py. REQ: RET-07.
- [x] 3.2 `_build_fts5_query()` en memory_db.py. REQ: RET-07.
- [x] 3.3 Parameterized queries (no SQL injection). REQ: RET-07.

## 4. Retrieval pipeline FTS5-first ✅ COMPLETADO
- [x] 4.1 `_search_fts_sync()`: two-phase (FTS5 rowids + IN clause).
  Acept: tests/core/test_fts5_points.py. REQ: RET-01, RET-09.
- [x] 4.2 `search_fts()` public API con scope filter. REQ: RET-01.
- [x] 4.3 Entity boost placeholder. REQ: RET-08.
- [x] 4.4 Cero referencias a embedding en retrieval. REQ: RET-09.

## 5. Consolidación léxica (activar NO-OPs) ✅ COMPLETADO
- [x] 5.1 `shared/consolidation.py`: `_consolidate_l1_l2()`.
  Acept: tests/core/test_consolidation.py::test_l1_l2_creates_episodes. REQ: MEM-01.
- [x] 5.2 `_consolidate_l2_l3()`: entity extraction from episodes.
  Acept: tests/core/test_consolidation.py::test_l2_l3_extracts_entities. REQ: MEM-02.
- [x] 5.3 `_consolidate_l3_l4()`: co-occurrence clustering.
  Acept: tests/core/test_consolidation.py::test_l3_l4_creates_narratives. REQ: MEM-03.
- [x] 5.4 NO-OPs eliminados: `_promote_l2_l3`, `_promote_l3_l4`, `dream()`.
  Acept: tests/adversarial/test__M2__consolidation_noop.py actualizado. REQ: MEM-01, MEM-02, MEM-03.

## 6. Eliminar embedding.py + cleanup ⏳ PENDIENTE (Wave 3)
- [ ] 6.1 Borrar `src/shared/embedding.py` (700 líneas).
- [ ] 6.2 Borrar `src/shared/embedding_cache.py` (90 líneas).
- [ ] 6.3 Remover `hash_vector()` de `memory_db.py`.
- [ ] 6.4 Remover campos `embedding_*` y `llm_model` de `Config`.
- [ ] 6.5 Actualizar `config/.env.example`.
- [ ] 6.6 Actualizar `install/app-install.sh`.

## 7. Migración de datos ⏳ PENDIENTE (Wave 3)
- [ ] 7.1 Script `scripts/migrate_to_fts5.py`.
- [ ] 7.2 Migración idempotente.

## 8. Tests adversariales ISO-18 ⏳ PENDIENTE (Wave 3)
- [ ] 8.1 `test__M6__entity_isolation.py`.

## 9. Integración + verificación ⏳ PENDIENTE (Wave 3)
- [ ] 9.1 `pytest tests/ -q` → 400+ passed.
- [ ] 9.2 `pytest tests/adversarial -q` → 100+ passed.
- [ ] 9.3 Re-run eval-40 con FTS5.
- [ ] 9.4 `ruff check src/` → 0 violations.
- [ ] 9.5 Grep embedding imports = 0.
- [ ] 9.6 Health check sin embedding.

## 10. Docs + cierre ⏳ PENDIENTE (Wave 3)
- [ ] 10.1 README update.
- [ ] 10.2 OpenSpec specs update.
- [ ] 10.3 GATE_M6 sign-off.
