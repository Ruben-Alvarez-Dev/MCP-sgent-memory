# Tareas M9-Schema-Migration

## T1: Remover columna vector del schema
- [ ] Actualizar `_ensure_schema()` en memory_db.py
- [ ] Agregar migración ALTER TABLE si columna existe
- [ ] Eliminar `_pack_vector`/`_unpack_vector` si aún existen

## T2: Rewriting tests skippeados
- [ ] `test_consolidation.py` (5 tests) - pipeline activo
- [ ] `test__M2__consolidation_noop.py` (5 tests) - comportamiento nuevo
- [ ] `test__M5__trunk.py` (1 test) - upsert signature
- [ ] `test__M6__full_adversarial.py` (2 tests) - scope isolation
- [ ] `test_sparse_fusion.py` - eliminar o skip permanentemente

## T3: Eval fixture restructuring
- [ ] Actualizar fixture_corpus.py para 40 docs FTS5-only
- [ ] Reemplazar chunks embedding.py con contenido relevante
- [ ] Actualizar judgments.yaml si es necesario

## T4: README update
- [ ] Sección Architecture → FTS5-first
- [ ] Remover referencias Qdrant/llama-server
- [ ] Agregar diagrama retrieval pipeline

## T5: GATE
- [ ] Ejecutar suite completa
- [ ] Firmar GATE_M9
- [ ] Commit final
