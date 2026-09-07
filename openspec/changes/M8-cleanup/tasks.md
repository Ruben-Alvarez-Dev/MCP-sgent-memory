# Tareas M8-Cleanup

## T1: Eliminar módulos embedding
- [ ] `src/shared/embedding.py` → delete
- [ ] `src/shared/embedding_cache.py` → delete
- [ ] Verificar cero imports restantes

## T2: Migrar schema (remover vector)
- [ ] Actualizar CREATE TABLE en `_ensure_schema()`
- [ ] Agregar migración para DBs existentes
- [ ] Eliminar `_pack_vector`/`_unpack_vector` si aún existen

## T3: Rewritetests skippeados
- [ ] `tests/core/test_consolidation.py` (5 tests)
- [ ] `tests/adversarial/test__M2__consolidation_noop.py` (5 tests)
- [ ] `tests/adversarial/test__M5__trunk.py` (1 test)
- [ ] `tests/adversarial/test__M6__full_adversarial.py` (2 tests)

## T4: Actualizar documentación
- [ ] README: sección "Engine → Retrieval" → FTS5-first
- [ ]移除 Qdrant references
- [ ] Agregar nota sobre embedding modules deleted

## T5: GATE
- [ ] Ejecutar suite completa
- [ ] Firmar GATE_M8
- [ ] Commit
