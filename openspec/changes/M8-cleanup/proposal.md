# M8-Cleanup Final

## Problem
Restos de embeddings aún existen en el código:
- `src/shared/embedding.py` y `embedding_cache.py` aún presentes (depreciados)
- Columna `vector` aún existe en schema (aunque ignorada)
- 14 tests skippeados que necesitan reescritura
- README no refleja arquitectura FTS5-first

## Why Now
M6 y M7 ya eliminaron todas las dependencias funcionales.
Solo queda cleanup formal y tests.

## Success Criteria
- [ ] `embedding.py` eliminado
- [ ] `embedding_cache.py` eliminado
- [ ] Schema migration: columna `vector` removida
- [ ] 14 tests skippeados reescritos para FTS5-only
- [ ] README actualizado
- [ ] 423 tests passing, 0 skipped

## Risks
- Migración de schema requiere backup/restore
- Tests skippeados pueden requerir cambios significativos
