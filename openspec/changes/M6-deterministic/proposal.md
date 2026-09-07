# Proposal: M6-deterministic — eliminación completa de embeddings, retrieval 100% lexical

## Intent
Ejecutar la restricción dura "cero modelos locales" al máximo: eliminar la
dependencia de embeddings (BGE-M3 / llama-server) del pipeline de retrieval.
El sistema pasará de "dense-first + hash fallback" a "FTS5 + metadata filters +
entity graph boost" — retrieval 100% determinista, sin modelo externo, sin
puerto, sin modelo descargable. Las capas L2-L4 se activan con consolidación
léxica (agrupación, extracción de entidades, clustering por co-ocurrencia).

El agente LLM sigue siendo quien piensa y genera; la memoria solo almacena,
organiza y recupera. Esa separación de preocupaciones es más limpia y más
confiable.

## Capabilities
- Modified: `storage` (STO-07 FTS5 en points; STO-08 entities table;
  STO-09 relations table; migración desde vector-based)
- Modified: `retrieval` (RET-07 reemplaza dense search por FTS5+metadata;
  RET-08 query expansion con synonym dict; RET-09 entity graph boost)
- Modified: `consolidation` (MEM-01 L1→L2 funcional; MEM-02 L2→L3 funcional;
  MEM-03 L3→L4 funcional; NO-OPs eliminados)
- Modified: `isolation` (ISO-18: entity graph scoped por agent_scope)
- Removed: `embedding` (embedding.py 700 líneas, embedding_cache.py 90 líneas,
  hash_vector, todo backend llama_cpp/llama_server/http/noop)
- Cleaned: dead config (llm_model, EMBEDDING_* env vars, porta 8081/8091 drift)

## Tenants/scopes e impacto de aislamiento
Ninguno estructuralmente. FTS5 opera sobre la tabla `points` ya filtrada por
engine scope filter. Las tablas `entities` y `relations` heredan el mismo
patrón ISO-11: `agent_scope` como columna indexada, nunca post-filter.
G-ISOLATION se re-firma (cambio en motor de storage).

## Rollback plan
Revert del commit. Schema añade tablas (`entities`, `relations`, FTS5) que son
aditivas — sin migraciones destructivas. Columna `vector` BLOB se preserva
en points (se ignora en reads) hasta limpieza posterior. Todo lo removido
(embedding.py, cache) es estadoless: no hay datos perdidos.

## Fuera de alcance (con dueño)
- Eliminación de columna `vector` de points → requiere migración batch, se
  pospone a M7 (no bloqueante: se ignora en reads actuales).
- Graph neural entities (relaciones aprendidas) → fuera de scope determinista.
- Multi-idioma query expansion → decisión de owner, no misión técnica.
- Eval-40 re-evaluación con corpus real (no fixture) → backlog futuro.
