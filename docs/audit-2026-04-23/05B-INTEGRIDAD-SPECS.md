# Grupo B — Integridad de Datos

## Especificaciones

### SPEC-B1: Rechazar vectores vacíos en QdrantClient.upsert()

**ID auditoría**: DAT-C1
**Severidad**: CRITICAL
**Módulo**: `src/shared/qdrant_client.py`

**Problema**:
3 módulos (autodream, mem0, conversation-store) definen `_embed()` con `except Exception: return []`.
El vector vacío `[]` se pasa a `qdrant.upsert()` que lo almacena sin validación.
Un vector vacío contamina búsquedas por siempre (no hay purga).

**Spec de fix**:
```python
async def upsert(self, point_id, vector, payload, sparse=None, wait=True):
    # Guard: rechazar vectores vacíos
    if not vector or len(vector) != self.embedding_dim:
        raise ValueError(
            f"Invalid vector: got {len(vector) if vector else 0} dims, expected {self.embedding_dim}"
        )
    # ... resto igual
```

**Criterio de aceptación**:
- [ ] `upsert(id, [], payload)` → raises ValueError
- [ ] `upsert(id, [0.0]*1024, payload)` → OK (zeros válidos)
- [ ] `upsert(id, [0.1]*512, payload)` → raises ValueError (dim mismatch)
- [ ] Logging del error: "Rejected empty/invalid vector for point {point_id}"

---

### SPEC-B2: Eliminar _embed() wrappers duplicados, usar async_embed con fallback consistente

**ID auditoría**: REL-H1, QUA-H2 (cross-cutting)
**Severidad**: HIGH
**Módulos**: autodream, mem0, conversation-store

**Problema**: 3 módulos definen `_embed()` idéntico:
```python
async def _embed(t):
    try: return await async_embed(t)
    except Exception: return []
```

Todos retornan `[]` silenciosamente → SPEC-B1 no se puede aplicar porque el llamador
nunca sabe que falló.

**Spec de fix**:
1. Eliminar los 3 `_embed()` locales
2. Usar `async_embed()` directamente desde `shared.embedding`
3. Añadir fallback con logging en un punto central:

```python
# En shared/embedding.py, añadir:
async def safe_embed(text: str) -> list[float]:
    """Embed con fallback a zero-vector y log de warning."""
    try:
        vec = await async_embed(text)
        if vec and len(vec) > 0:
            return vec
    except Exception as e:
        logging.warning(f"Embedding failed, using zero-vector: {e}")
    return [0.0] * EMBEDDING_DIM
```

4. Todos los módulos usan `safe_embed()` → nunca retornan `[]`

**Criterio de aceptación**:
- [ ] 0 `_embed()` locales en módulos
- [ ] Todos usan `safe_embed()` de shared
- [ ] Fallback a zero-vector con logging WARNING
- [ ] SPEC-B1 rechazaría zero-vectors en upsert → doble protección

---

### SPEC-B3: Añadir schema_version a payloads de Qdrant

**ID auditoría**: DAT-H2
**Severidad**: MEDIUM
**Módulo**: `src/shared/models/__init__.py` + `src/shared/qdrant_client.py`

**Problema**: Los payloads almacenados en Qdrant no tienen versión. Si MemoryItem cambia campos,
los datos existentes son incompatibles.

**Spec de fix**:
```python
# En MemoryItem:
schema_version: str = Field(default="1.0")

# En qdrant_client.upsert():
payload["schema_version"] = payload.get("schema_version", "1.0")
```

**Criterio de aceptación**:
- [ ] Todo punto nuevo tiene `schema_version: "1.0"` en payload
- [ ] Lectura tolera puntos sin schema_version (asume "0.9" legacy)

---

### SPEC-B4: Purga periódica de puntos Qdrant

**ID auditoría**: DAT-C2
**Severidad**: CRITICAL
**Módulo**: nuevo script `scripts/purge-qdrant.py` + lifecycle.sh

**Problema**: lifecycle.sh limpia archivos pero no puntos en Qdrant. Datos crecen indefinidamente.

**Spec de fix**:
Añadir a lifecycle.sh:
```bash
# 7. Qdrant point purge
log "🗄️  Qdrant Point Purge"
"$PYTHON" -c "
import json, urllib.request
# Delete L1 working memories older than 30 days
# Delete L0 raw duplicates
# Keep L3+ forever
" 2>/dev/null
```

Política propuesta:
| Layer | TTL | Política |
|---|---|---|
| L0 (raw events) | 90 días | JSONL rotation + delete de puntos |
| L1 (working) | 30 días | Delete puntos con `created_at` antiguo |
| L2 (episodic) | 180 días | Consolidar a L3 antes de borrar |
| L3 (semantic) | ∞ | Nunca borrar |
| L4 (consolidated) | ∞ | Nunca borrar |

**Criterio de aceptación**:
- [ ] lifecycle.sh incluye sección de Qdrant purge
- [ ] Dry-run mode (`--dry-run`) lista qué se borraría
- [ ] No toca L3/L4 nunca
- [ ] Log de cuántos puntos se purgaron
