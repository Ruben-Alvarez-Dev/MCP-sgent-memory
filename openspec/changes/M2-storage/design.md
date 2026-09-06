# Design: M2-storage

## Módulo nuevo: `src/shared/memory_db.py` (stdlib puro, sin I/O de red)

`MemoryDB(db_path=None, collection="L0_L4_memory", embedding_dim=1024)`.
Paridad de interfaz con `QdrantClient` para que los servidores solo cambien
constructor + import, y BORREN post-filtros (el filtro viaja al motor):

- `async health() -> bool` — pragma quick_check + WAL activo.
- `async ensure_collection() -> None` — CREATE TABLE IF NOT EXISTS.
- `async upsert(point_id, vector, payload, sparse=None)` — vector `list[float]`
  o `None`; si `None` o todo-ceros → BLOB NULL + `payload["embedded"]=false`
  (STO-05: jamás zero-vector persistido). Validación de payload keys heredada.
- `async upsert_batch(points)` — transacción única.
- `async get(point_id) -> {id, payload} | None`.
- `async delete(point_id) -> bool`.
- `async search(vector, limit=10, score_threshold=0.3, filter=None) -> [{id, score, payload}]`
  — **el filtro se traduce a SQL WHERE con parámetros vinculados** (dict formato
  Qdrant `{"must":[{"key":k,"match":{"value":v}}]}` → `json_extract(payload,'$.k')=?`).
  Coseno por fuerza bruta (stdlib `math`, floats unpack de BLOB) SOLO sobre
  filas candidatas del WHERE. Filas con vector NULL: puntuadas contra
  `_hash_vector(sha256(content))` determinista, marcadas `score_source:"hash"`.
- `async scroll(filter=None, limit=50) -> [payload]` — mismo WHERE.
- `async count() -> int`.

### Schema (data/memory.db, `user_version`=2)
```sql
CREATE TABLE points(
  id TEXT, collection TEXT NOT NULL,
  vector BLOB,                      -- NULL permitido, jamás zero-vector
  payload TEXT NOT NULL,            -- JSON
  sparse_json TEXT,                 -- bm25 write-only (RET-05)
  created_at TEXT NOT NULL,
  PRIMARY KEY(collection, id));
CREATE INDEX idx_points_scope ON points(collection, json_extract(payload,'$.agent_scope'), json_extract(payload,'$.user_id'));
```
Threading: `check_same_thread=False`, WAL, `busy_timeout=5000`, `asyncio.Lock`
de escritura por proceso. Multi-proceso (servers stdio separados) seguro por WAL.

## Decisiones y porqués
1. **Fuerza bruta stdlib, no sqlite-vec/numpy**: BD real ~vacía; regla de config
   prohíbe dependencias nuevas sin aprobación; 10k×1024 ≈ <50 ms. Extensión
   vectorial nativa = mejora futura medible, no bloqueante.
1b. **Columnas reales (agent_scope, user_id) en vez de json_extract**: el índice
   con json_extract falla el mantenimiento con payload corrupto (descubierto en
   TDD); las columnas extraídas en escritura aíslan filas corruptas (quedan con
   scope NULL, jamás visibles en lecturas scoped) y endurecen ISO-11 con
   allowlist de claves filtrables {agent_scope, user_id} en vez de regex.
2. **conversation_db apunta a memory.db**: cambia SOLO `_get_db_path()`; sus
   tablas (threads/messages/messages_fts) conviven en el mismo fichero. Cero
   reescritura, unificación de fichero lograda (STO-02 delta).
3. **Demolición**: borrar `qdrant_client.py`, `qdrant_factory.py`,
   `scoped_qdrant.py`, `hybrid_qdrant.py` (ISO-08) y sus tests; migrar los 25
   ficheros que los importan a `MemoryDB` o eliminar la referencia muerta.
4. **ISO-06**: en L0_to_L4, los writes con `scope_id=consolidated/narrative/dream`
   se eliminan (promociones desactivadas, quedan no-ops logueadas con WARN).
5. **ISO-07 jail FS**: `scope_jail_path(base, scope, rel)` en scope.py —
   `Path.resolve()` + `is_relative_to(jail)` fail-closed; vault/decisions lo usan
   en TODO write/read. 5 niveles `c:/p:/a:/s:/u:` soportados en normalize_scope.
6. **events.jsonl permanece** (STO-03): única fuente de re-ingesta para rollback.

## Failure modes + casos adversariales
- Embedding server caído al escribir → vector NULL persistido, nunca zero; la
  fila es recuperable por hash-vector/lexical. (Test: STO-05-T1)
- Filtro con key inexistente → WHERE no matchea, 0 filas, jamás fila sin filtro.
  Fail-closed: search sin filter y sin allowlist explícita Lanza `ScopeRequired`.
  (Tests: ISO-05-T1..T3, A3)
- Payload JSON corrupto → fila se ignora y se cuenta en `health().corrupt_rows`,
  nunca crashea una búsqueda. (Test: STO-01-T4)
- SQL injection vía key del filtro → keys validadas `^[a-z_][a-z0-9_]*$` y
  valor SIEMPRE parametrizado. (Test: A14)
- Escritura concurrente multi-proceso → WAL + busy_timeout; retry implícito de
  SQLite. (Test: STO-01-T5)
- Traversal en jail (`../../etc`, symlinks) → resolve+commonpath rechaza ANTES
  de tocar FS. (Tests: A5, A6, A10)
- Migration legacy: filas Qdrant preexistentes → script `scripts/migrate_to_memory_db.py`
  idempotente desde events.jsonl; Qdrant NO se lee en la migración (demoledor).
- Rendimiento degenerado (>50k puntos) → `health()` reporta `scan_ms`; umbral
  documentado para activar sqlite-vec en misión futura, no silently lento.

## Cobertura adversarial (tests/adversarial/)
Green en M2: A3 (facts cross-user vía engine), A5 (jail traversal write),
A6 (jail symlink escape), A10 (filter-bypass: key rara/None), A14 (SQL injection
en filtro), A15 (scroll sin filtro falla closed). A11/A12/A16 → M5 (tronco).
