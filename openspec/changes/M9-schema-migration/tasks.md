# Tareas M9-Schema-Migration

## T1: Remover columna vector del schema
- [x] Actualizar `_ensure_schema()` en memory_db.py
- [x] Agregar migración ALTER TABLE si columna existe (boot-time, idempotente, SQLite ≥3.35; fallback tolerante)
- [x] Eliminar `_pack_vector`/`_unpack_vector`/`hash_vector`/`_cosine`/helpers sparse (`_score_candidates`, `_search_sync`, `_sparse_cosine`, `_validate_sparse_query`, `_parse_sparse_json`)

## T2: Rewriting tests skippeados
- [x] `test_consolidation.py` — reescrito a API FTS5-only, verde
- [x] `test__M2__consolidation_noop.py` — fixture adaptado, verde
- [x] `test__M5__trunk.py` (3 tests) — upsert/search signature + a16 des-saltado
- [x] `test__M6__full_adversarial.py` (2 tests) — des-saltados (consolidation security)
- [x] `test_sparse_fusion.py` — ELIMINADO (la fusión sparse murió con la columna vector)
- [x] `test_trunk.py` (6) — des-saltados y adaptados; `test_memory_db.py` — STO-05 sustituido por tests M9 (schema sin vector, determinismo FTS5, migración); ISO05 A3 reescrito con spy de filtro en motor; e2e des-saltados; ServerWiring fixture reparado
- Hallazgo y fix: `upsert_batch` no sincronizaba FTS5 (corpora batch invisibles) — corregido en motor
- Hallazgo y fix: `search()` nuevo vuelve a exigir filtro (ISO-05 fail-closed) antes del short-circuit de query vacía

## T3: Eval fixture restructuring
- [x] fixture_corpus.py: chunk hash_vector → chunk FTS5 two-phase; upsert_batch sin vector
- [x] Los 4 chunks embedding.py ya eliminados en M8 (34 docs; ids establecidos eval-1..34)
- [x] judgments.yaml: restauradas 2 entradas rotas por M8 (sidecar-8890, dream-cooldown) + remap honesto de ids por shift (−4 tras eval-7) + 3 queries de embeddings re-juzgadas al análogo real (FTS5) con nota
- [x] Eval FTS5-only medido: R@5 0.5375 / MRR 0.4557 — supera el récord M5 (0.463)

## T4: README update
- [x] Sección Architecture/Retrieval → FTS5-first + diagrama pipeline
- [x] Referencias vector/hash-vector/sparse actualizadas (Qdrant/llama ya eran "legacy only")
- [x] Métrica del eval M9 en README

## T5: GATE
- [x] Ejecutar suite completa (403 passed / 0 failed / 6 skipped legacy v3; 151 adversarial)
- [x] Firmar GATE_M9
- [x] Commit final
