# Tasks: M7-cleanup

## 1. Eliminar columna vector (STO-11)
- [ ] 1.1 Migración: ALTER TABLE points DROP COLUMN vector
- [ ] 1.2 Actualizar _pack_vector, _unpack_vector, _score_candidates
- [ ] 1.3 Tests: verify no vector column exists
- [ ] 1.4 Verificar que search_fts funciona sin vector

## 2. Borrar embedding.py (RET-09 completo)
- [ ] 2.1 Borrar src/shared/embedding.py
- [ ] 2.2 Borrar src/shared/embedding_cache.py
- [ ] 2.3 Eliminar imports restantes de embedding
- [ ] 2.4 grep: zero refs a shared.embedding

## 3. Cleanup config
- [ ] 3.1 Remover embedding_backend, embedding_dim, embedding_model de Config
- [ ] 3.2 Remover validación EMBEDDING_BACKEND
- [ ] 3.3 Actualizar config/.env.example

## 4. Reescribir tests skipped
- [ ] 4.1 test_facts_crud_with_engine_isolation → FTS5 version
- [ ] 4.2 test_scoped_retrieval_merges_own_and_shared_only → FTS5 version
- [ ] 4.3 test_search_memory_passes_engine_filter → FTS5 version
- [ ] 4.4 test_get_all_memories_scoped → FTS5 version
- [ ] 4.5 test_delete_memory_scoped → FTS5 version
- [ ] 4.6-4.11: Otros tests skipped

## 5. Eval-40 con corpus real
- [ ] 5.1 Crear corpus real del repositorio
- [ ] 5.2 Ejecutar eval-40 con FTS5
- [ ] 5.3 Medir R@5, MRR, zero-recall
- [ ] 5.4 Comparar vs M5 baseline

## 6. Integración + verificación
- [ ] 6.1 pytest tests/ -q → 420+ passed
- [ ] 6.2 pytest tests/adversarial -q → 150+ passed
- [ ] 6.3 ruff check src/ → 0 new violations
- [ ] 6.4 git diff --stat para verificar scope

## 7. Docs + cierre
- [ ] 7.1 Actualizar README (arquitectura M7)
- [ ] 7.2 Firmar GATE_M7
