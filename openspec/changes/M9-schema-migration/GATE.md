# M9-Schema-Migration — Gate

**Date:** 2026-09-07
**Status:** ✅ PASS (GO)

## Summary
- M9 completado: columna `vector` eliminada del schema con migración boot-time idempotente (`ALTER TABLE points DROP COLUMN`, tolerante a SQLite sin soporte)
- Maquinaria vectorial eliminada del motor: `hash_vector`, `_cosine`, `_pack_vector`, `_unpack_vector`, `_score_candidates`, `_search_sync`, helpers sparse
- `search()` redefinida: FTS5-only (bm25, OR-semantics), fail-closed ISO-05 verificado (exige filtro antes de cualquier short-circuit)
- Suite final: **403 passed / 0 failed / 6 skipped** (2 legacy v3 documentados + variantes), **151 adversarial**, ruff limpio en ficheros tocados (preexistentes documentados)

## Bugs latentes descubiertos y corregidos durante M9
1. **L2/L3/L5 `await None`** (regresión M7): `vector = await None` lanzaba TypeError en runtime → L2 nunca guardaba conversaciones en memory.db, L3 search_memory fallaba, L5 degradaba a sim=0.0. Corregido: query text es la señal de recuperación.
2. **`upsert_batch` sin sync FTS5** (M6): los corpora insertados por batch eran invisibles a la recuperación FTS5. Corregido en `_write`.
3. **`_build_fts5_query` AND implícito**: colapsaba el recall a ~0 en queries naturales multi-término. Corregido: OR-join con ranking bm25.
4. **Acrónimos con dígitos** (hallazgo M5 formalizado): regex de tokens ahora captura `FTS5`.
5. **Drift del eval por M8**: judgments.yaml con entradas zombis (sin `q:`/`relevant`) y 3 queries apuntando a chunks de embedding eliminados. Restaurado/remapeado honestamente con notas.

## Eval FTS5-only (evidencia fresca)
- **Recall@5 = 0.5375 · MRR = 0.4557** (40 queries, 15 zero-recall)
- Supera el récord M5 (R@5 0.463 con canal hash-dense) SIN embeddings
- Evidencia: `evidence/eval-40-results-m9.yaml`

## Restricciones duras verificadas
- [x] Cero modelos de generación en código (no reintroducidos)
- [x] Scope siempre filtro duro de motor, nunca señal de ranking (ISO-05 spy-test con filtro en WHERE)
- [x] Fail-closed reads (ScopeRequiredError sin filtro) — verificado post-refactor
- [x] FTS5 two-phase search preservado (rowid IN clause, WAL-safe)

## Skips restantes (documentados, permanentes)
- `tests/core/test_v3_spec_features.py` (2): V3 superseded by Fusion Code Maps / proximity ranking no implementado

## Decisión
**GO** — el programa memory-zero queda: M0–M9 completo, cero dependencias de embedding end-to-end (código, schema y eval).
