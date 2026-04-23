# Grupo E — Calidad de Código

## Especificaciones

### SPEC-E1: Tests unitarios mínimos

**ID auditoría**: QUA-H1
**Severidad**: HIGH
**Nuevo directorio**: `tests/`

**Spec**: Crear suite de tests que cubra los paths críticos:

```
tests/
├── test_sanitize.py          # Input validation
├── test_qdrant_client.py     # DB operations (mocked)
├── test_embedding.py         # Embedding pipeline
├── test_mem0.py              # Semantic memory (mocked)
├── test_automem.py           # Memory ingestion (mocked)
├── test_engram.py            # File operations
├── test_conversation.py      # Thread storage (mocked)
├── test_autodream.py         # Consolidation logic
├── test_config.py            # Config validation
└── conftest.py               # Shared fixtures
```

**Prioridad de tests** (orden de escritura):

1. `test_sanitize.py` — paths de validación, edge cases, Unicode, path traversal
2. `test_engram.py` — get_decision path confinement, vault_write, delete_decision
3. `test_config.py` — validate() con configs válidas e inválidas
4. `test_qdrant_client.py` — upsert con vector vacío, dim mismatch, retry logic
5. `test_embedding.py` — cache hit/miss, truncation, fallback
6. `test_automem.py` — memorize con Qdrant caído, event ingestion
7. `test_mem0.py` — UUID generation, search, add/delete
8. `test_conversation.py` — save/search/get thread
9. `test_autodream.py` — L1→L2, L2→L3 promotion, embedding fallback

**Criterio de aceptación**:
- [ ] `pytest tests/ -v` pasa con >80% coverage de módulos server
- [ ] CI-ready (no depende de servicios externos, usa mocks)
- [ ] Cada spec de este TEMP tiene al menos 1 test que lo verifica

---

### SPEC-E2: Eliminar duplicación de _embed()

**ID auditoría**: QUA-H2
**Severidad**: HIGH
**Cubierto en**: SPEC-B2 (Grupo B)

Ver `05B-INTEGRIDAD-SPECS.md` SPEC-B2. Mismo fix.

---

### SPEC-E3: QdrantClient compartido (no inline)

**ID auditoría**: QUA-H3
**Severidad**: MEDIUM
**Módulos**: todos los server/main.py

**Problema**: 6 módulos instancian su propio `QdrantClient(...)` inline:
```python
# Cada módulo repite:
qdrant = QdrantClient("http://127.0.0.1:6333", "automem", 1024)
```

**Spec de fix**:
Crear factory compartida:

```python
# src/shared/qdrant_factory.py
from shared.qdrant_client import QdrantClient

_clients: dict[str, QdrantClient] = {}

def get_qdrant(collection: str, dim: int = 1024) -> QdrantClient:
    key = f"{collection}:{dim}"
    if key not in _clients:
        _clients[key] = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
            collection=collection,
            embedding_dim=dim
        )
    return _clients[key]
```

**Criterio de aceptación**:
- [ ] 0 instanciaciones directas de QdrantClient en módulos server
- [ ] Todos usan `get_qdrant(collection)` desde factory
- [ ] 1 conexión reutilizada por colección
