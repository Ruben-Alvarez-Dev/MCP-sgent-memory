# MemoryDB API (src/shared/memory_db.py — YA IMPLEMENTADO, no lo modifiques)
```python
from shared.memory_db import MemoryDB
db = MemoryDB(None, collection="L0_L4_memory", embedding_dim=1024)  # path None → data/memory.db
await db.ensure_collection()
await db.upsert(id, vector_o_None, payload_dict, sparse=None)
await db.upsert_batch([{"id","vector","payload"}])
await db.get(id) -> {"id","payload"} | None
await db.delete(id, filter=None) -> bool   # con filter: DELETE atómico id+condición
await db.count() -> int
await db.search(vector|None, limit=10, score_threshold=0.3,
  filter={"must":[{"key":"agent_scope"|"user_id","match":{"value":v}}]}) -> [{"id","score","payload","score_source"}]
await db.scroll(filter=..., limit=50) -> [payload]
await db.health() -> bool
```
REGLAS DURAS: filter OBLIGATORIO en search/scroll (si no: ScopeRequiredError).
Claves permitidas solo: agent_scope, user_id. PROHIBIDO post-filtrar en Python.
PROHIBIDO persistir zero-vectors (pasa vector=None si no hay embedding).
Colecciones (mismo nombre que antes): "L0_L4_memory", "L2_conversations", "L3_facts".
Testear con: .venv/bin/python -m pytest <tu-test> -q  (NUNCA la suite completa)
PROHIBIDO: git, editar ficheros fuera de tu propiedad, crear puertos/daemons.
