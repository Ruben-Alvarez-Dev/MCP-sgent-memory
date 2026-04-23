# Grupo D — Rendimiento

## Especificaciones

### SPEC-D1: Embedding cache persistente a disco

**ID auditoría**: PER-H1
**Severidad**: HIGH
**Módulo**: `src/shared/embedding.py`

**Problema**: LRU cache se pierde al reiniciar. Cada reinicio = 0 hits, todo miss.
1 embedding = 1191ms. Con 50 memorias al arrancar = ~1 minuto perdido.

**Spec de fix**:
```python
import sqlite3, hashlib

EMBEDDING_CACHE_DB = os.getenv("EMBEDDING_CACHE_DB", 
    os.path.join(os.getenv("MEMORY_SERVER_DIR", ""), "data", "embedding_cache.db"))

def _get_cached_embedding_db(text: str) -> list[float] | None:
    """Check SQLite disk cache."""
    key = hashlib.sha256(text.encode()).hexdigest()
    conn = sqlite3.connect(EMBEDDING_CACHE_DB)
    row = conn.execute("SELECT vector FROM embeddings WHERE key=?", (key,)).fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def _set_cached_embedding_db(text: str, vector: list[float]):
    """Store to SQLite disk cache."""
    key = hashlib.sha256(text.encode()).hexdigest()
    conn = sqlite3.connect(EMBEDDING_CACHE_DB)
    conn.execute("INSERT OR REPLACE INTO embeddings (key, vector) VALUES (?, ?)", 
                 (key, json.dumps(vector)))
    conn.commit()
    conn.close()
```

**Criterio de aceptación**:
- [ ] Cache sobrevive reinicios
- [ ] Hit rate >80% tras primera sesión
- [ ] SQLite WAL mode para concurrencia
- [ ] Auto-vacuum cuando >100K entries

---

### SPEC-D2: Batch embedding para consolidación

**ID auditoría**: PER-H1
**Severidad**: MEDIUM
**Módulo**: `src/autodream/server/main.py`

**Problema**: autodream embedea textos uno a uno. 50 episódicas = 50 calls × 1191ms = ~60 segundos.

**Spec de fix**:
llama-server soporta batch embeddings. Enviar múltiples textos en una sola call:
```python
# En vez de:
for item in items:
    vector = await async_embed(item.content)

# Hacer:
texts = [item.content for item in items]
vectors = await async_embed_batch(texts)  # 1 call HTTP
```

**Criterio de aceptación**:
- [ ] `async_embed_batch(texts: list[str]) -> list[list[float]]`
- [ ] Reducción de 50 calls a 1 call → ~60s → ~3s
- [ ] Fallback a individual si batch falla

---

### SPEC-D3: Embedding truncation coherente con sanitize

**ID auditoría**: DAT-H1
**Severidad**: MEDIUM
**Módulo**: `src/shared/embedding.py` vs `src/shared/sanitize.py`

**Problema**: sanitize acepta 100K chars, embedding trunca a 2000. El texto que se almacena no es el que se embebe.

**Spec de fix**:
- Opción A: Embedding usa el texto completo (lento pero correcto)
- Opción B: sanitize trunca a un límite razonable antes de pasar a embedding (ej: 4000 chars ≈ 1000 tokens)
- Opción C: Se embeddean los primeros 4000 chars, se almacena el texto completo

Recomendación: Opción C. Embedding truncado para velocidad, texto completo para storage.

**Criterio de aceptación**:
- [ ] Documentar qué se embebe vs qué se almacena
- [ ] Mismo texto → mismo embedding (determinístico)
