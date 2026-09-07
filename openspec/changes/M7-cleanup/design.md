# Design: M7-cleanup

## 1. Eliminar columna vector

### 1.1 Migración SQL
```sql
ALTER TABLE points DROP COLUMN vector;
```

### 1.2 Cambios en memory_db.py
- Eliminar `_pack_vector()`, `_unpack_vector()`
- Eliminar parameter `vector` de `_prepare_row()`
- Eliminar parámetro `vector` de `upsert()`, `upsert_batch()`
- `_score_candidates()`: eliminar lógica de cosine similarity
- `_search_sync()`: eliminar parámetro `vector`

### 1.3 Impacto en servidores
- Todos los calls a `db.upsert()` deben eliminar argumento `vector`
- `safe_embed()` references eliminadas
- `async_embed()` references eliminadas

## 2. Borrar embedding modules

### 2.1 Archivos a eliminar
- `src/shared/embedding.py` (25KB)
- `src/shared/embedding_cache.py` (2.6KB)

### 2.2 Imports a eliminar
- `from shared.embedding import safe_embed` → eliminar
- `from shared.embedding import async_embed` → eliminar
- `from shared.embedding import bm25_tokenize` → eliminar (FTS5 reemplaza)
- `from shared.embedding import get_embedding` → eliminar
- `from shared.embedding import hash_vector` → eliminar

## 3. Config cleanup

### 3.1 Eliminar campos de Config
- `embedding_backend: str`
- `embedding_dim: int`
- `embedding_model: str`
- `llama_server_url: str`
- `embedding_cache_size: int`
- `llm_model: str`

### 3.2 Eliminar validaciones
- `valid_embed_backends` check
- `embedding_dim` standard check
- `embedding_cache_size` check
- `llama_server_url` check

## 4. Tests reescritura

### 4.1 Enfoque FTS5
Todos los tests que usaban `_hash()` o `_vec()` para embeddings
deben usarse `search_fts()` en su lugar.

### 4.2 Pattern
```python
# Antes (M5):
await db.upsert("id", _vec(0.9), {"content": "text", ...})
results = await db.search(_vec(0.9), limit=10, ...)

# Después (M7):
await db.upsert("id", None, {"content": "text", ...})
results = await db.search_fts("text", limit=10, filter=...)
```

## 5. Eval-40 corpus real

### 5.1 Fuente
Usar documentos reales del repositorio:
- README.md
- docs/*.md
- openspec/**/*.md
- src/**/*.py (extract entities)

### 5.2 Métricas objetivo
- R@5 ≥ 0.65 (vs 0.425 M5 degraded)
- MRR ≥ 0.60 (vs 0.476 M5 degraded)
- Zero-recall ≤ 10 (vs 18 M5)
