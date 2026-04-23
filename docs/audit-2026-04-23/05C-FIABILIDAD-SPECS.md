# Grupo C — Fiabilidad & Resiliencia

## Especificaciones

### SPEC-C1: Retry con exponential backoff en QdrantClient

**ID auditoría**: REL-C1
**Severidad**: CRITICAL
**Módulo**: `src/shared/qdrant_client.py`

**Problema**: 0 retry logic. Timeout HTTP o connection refused = operación perdida silenciosamente.

**Spec de fix**:
```python
import asyncio

async def _retry_async(fn, max_retries=3, base_delay=0.5):
    """Retry con exponential backoff."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return await fn()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exc = e
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Attempt {attempt+1}/{max_retries} failed: {e}, retrying in {delay}s")
            await asyncio.sleep(delay)
    raise last_exc
```

Aplicar a: `upsert()`, `search()`, `scroll()`, `ensure_collection()`

**Criterio de aceptación**:
- [ ] upsert/search/scroll reintentan 3 veces con backoff 0.5s → 1s → 2s
- [ ] Solo reintenta en ConnectError y TimeoutException
- [ ] No reintenta en 4xx (bad request = error del caller)
- [ ] Log de cada retry

---

### SPEC-C2: Try/except en _store_memory()

**ID auditoría**: REL-C2
**Severidad**: CRITICAL
**Módulo**: `src/automem/server/main.py`

**Problema**:
```python
async def _store_memory(item):
    await qdrant.ensure_collection()
    vector = ... 
    await qdrant.upsert(...)  # Sin try/except
```

Si Qdrant cae, la tool crashea sin feedback. El LLM no sabe por qué.

**Spec de fix**:
```python
async def _store_memory(item: MemoryItem) -> bool:
    """Store memory. Returns True if stored, False if failed."""
    try:
        await qdrant.ensure_collection()
        vector = item.embedding if item.embedding else await async_embed(item.content)
        if not vector or len(vector) != qdrant.embedding_dim:
            vector = await async_embed(item.content)  # retry embed
        sparse = bm25_tokenize(item.content)
        await qdrant.upsert(item.memory_id, vector, item.model_dump(mode="json"), sparse=sparse)
        return True
    except Exception as e:
        logger.error(f"Failed to store memory {item.memory_id}: {e}")
        # Still write to JSONL as fallback
        _append_raw_jsonl(RawEvent(..., attributes={"error": str(e), "content": item.content[:200]}))
        return False
```

**Criterio de aceptación**:
- [ ] Si Qdrant cae, memorize() retorna status="storage_failed" en vez de crash
- [ ] Se escribe en JSONL como fallback (no se pierde el dato)
- [ ] Log del error con memory_id

---

### SPEC-C3: Eliminar bare except y except Exception genéricos

**ID auditoría**: REL-H3, REL-H4
**Severidad**: HIGH
**Módulos**: todos

**Problema**: 5 bare `except:` y 42 `except Exception:` genéricos.

**Spec de fix por tipo**:

| Patrón actual | Fix |
|---|---|
| `except:` → | `except (ConnectionError, TimeoutError, ValueError) as e:` |
| `except Exception:` en embed | `except (ConnectionError, OSError, RuntimeError) as e:` |
| `except Exception:` en search | `except (httpx.HTTPError, httpx.TimeoutException) as e:` |
| `except:` en retrieval | Capturar específicamente las excepciones de httpx y embedding |

**Criterio de aceptación**:
- [ ] 0 bare `except:` en todo el código
- [ ] Cada `except` captura excepciones específicas
- [ ] Logging del error capturado (no silencioso)

---

### SPEC-C4: Connection pool para httpx

**ID auditoría**: PER-H2 (cross-cutting con fiabilidad)
**Severidad**: HIGH
**Módulo**: `src/shared/qdrant_client.py`

**Problema**: Cada operación crea y destruye un `httpx.AsyncClient`. Overhead TCP + sin reutilización de conexiones.

**Spec de fix**:
```python
class QdrantClient:
    def __init__(self, ...):
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
```

**Criterio de aceptación**:
- [ ] 1 AsyncClient reutilizado por colección
- [ ] Connection pooling: max 10 connections, 5 keepalive
- [ ] Close explícito al shutdown
