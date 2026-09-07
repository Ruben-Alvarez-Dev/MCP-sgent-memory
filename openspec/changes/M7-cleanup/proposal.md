# Proposal: M7-cleanup — cleanup final post-M6

## Intent
Completar la transición a retrieval 100% determinista:
1. Eliminar columna `vector` de points table (migración batch)
2. Borrar embedding.py + embedding_cache.py completamente
3. Reescribir 11 tests skipped para FTS5
4. Eval-40 con corpus real (no fixture)
5. Cleanup config (eliminar vars EMBEDDING_*)

## Capabilities
- Modified: `storage` (STO-11: vector column removal)
- Removed: `embedding.py`, `embedding_cache.py`
- Modified: `config` (eliminar EMBEDDING_* vars)
- Modified: `tests` (11 tests reescritos para FTS5)

## Rollback plan
Revert del commit. Schema drop column es reversible con ALTER TABLE ADD.
embedding.py se puede restaurar desde git.

## Fuera de alcance
- Cambios en arquitectura de capas L0-L5
- Nuevas capacidades de retrieval
- Cambios en identity/isolation
