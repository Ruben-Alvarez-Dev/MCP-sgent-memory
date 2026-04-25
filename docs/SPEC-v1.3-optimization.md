# MCP-agent-memory v1.3.0 — Optimization Spec

> **SDD (Spec-Driven Development)** — Spec first, code after.  
> Basado en datos del profiling real del 2026-04-23.

## Objetivo

Reducir latencias p95, mejorar calidad de búsqueda semántica, estabilidad del pipeline, y experiencia de desarrollo. Mantener backward compatibility total.

## Métricas baseline (v1.2.1)

| Operación | p50 | p95 | Nota |
|-----------|-----|-----|------|
| heartbeat | 2ms | 4ms | Baseline |
| vault read | 1ms | 2ms | Disk |
| save decision | 1ms | 2ms | Disk |
| vault write | 5ms | 8ms | Disk |
| mem0 search | 18ms | 41ms | Embed+Qdrant |
| automem memorize | 46ms | 178ms | Embed+Write |
| content 5K | 155ms | 200ms | Tokenization |
| dream cycle | 11.5s | 15s | llama.cpp LLM |
| embedding quality gap | +0.03 | — | Relevant vs irrelevant |
| concurrent speedup | 2.77x | — | 5 tools parallel |

## Métricas target (v1.3.0)

| Operación | Target p50 | Target p95 | Mejora |
|-----------|-----------|-----------|--------|
| mem0 search | 12ms | 25ms | -33% |
| automem memorize | 25ms | 80ms | -45% |
| content 5K | 60ms | 100ms | -50% |
| dream cycle | <1ms* | <1ms* | Async (non-blocking) |
| embedding quality gap | +0.10 | — | +233% |
| batch (10 embeds) | 250ms | 350ms | 1.6x via batch API |

*\*dream se ejecuta en background, la tool devuelve inmediatamente.*

---

## Optimizaciones (Specs individuales)

### OPT-01: Score threshold configurable

**Problema**: Búsquedas irrelevantes devuelven resultados con score 0.49-0.74 sin filtrado. El gap relevante/irrelevante es solo +0.03.

**Solución**: Añadir `score_threshold` param a todas las tools de búsqueda con default 0.5 (actualmente hardcodeado a 0.3 en qdrant_client).

**Archivos**:
- `src/shared/qdrant_client.py` — Ya tiene `score_threshold=0.3` default
- `src/mem0/server/main.py` — Añadir param `min_score: float = 0.5`
- `src/conversation-store/server/main.py` — Añadir param `min_score: float = 0.5`
- `src/vk-cache/server/main.py` — Ya usa `config.vk_min_score`

**Criterio de aceptación**:
- [ ] `mem0_search_memory(query="sushi recipe", min_score=0.7)` devuelve 0 resultados para queries irrelevantes
- [ ] `mem0_search_memory(query="lenguaje programación", min_score=0.5)` devuelve resultados relevantes
- [ ] Default min_score=0.5 mantiene compatibilidad
- [ ] Tests unitarios para threshold filtering

---

### OPT-02: Embedding prefetch en heartbeat

**Problema**: Cada tool call hace un embedding call (~15ms). El heartbeat ya se llama cada turno.

**Solución**: El heartbeat acepta un `pending_queries: list[str]` opcional. Si se proporciona, pre-computa embeddings y los cachea en LRU+SQLite. La próxima llamada a search/memorize encuentra cache hit → 0ms embed.

**Archivos**:
- `src/automem/server/main.py` — Modificar `heartbeat()` params
- `src/shared/embedding.py` — Añadir `prefetch_embeddings(texts)` helper

**Criterio de aceptación**:
- [ ] `heartbeat(agent_id="x", pending_queries=["query1","query2"])` pre-cachea embeddings
- [ ] Post-prefetch, `mem0_search_memory(query="query1")` tiene cache hit → <5ms embed
- [ ] Sin pending_queries, heartbeat funciona igual que antes (backward compat)
- [ ] LRU cache stats muestran hits tras prefetch

---

### OPT-03: Dream async (non-blocking)

**Problema**: `autodream_dream()` bloquea 11.5s llamando a llama.cpp sincrónicamente. El cliente MCP (Pi extension) timeout a 15s.

**Solución**: Dream se ejecuta en background. La tool devuelve inmediatamente con `{status: "dream_scheduled", task_id: "..."}`. Nueva tool `autodream_dream_status(task_id)` para consultar resultado.

**Archivos**:
- `src/autodream/server/main.py` — Refactor `dream()` a async background task
- `src/shared/task_queue.py` — Nuevo: simple asyncio task tracker

**Criterio de aceptación**:
- [ ] `autodream_dream()` responde en <50ms siempre
- [ ] `autodream_dream_status(task_id)` devuelve progreso/resultado
- [ ] Dream real se ejecuta en background correctamente
- [ ] Si llama.cpp cae, dream falla gracefully (no crash)
- [ ] Timeout del 30s en Pi extension nunca se dispara

---

### OPT-04: Qdrant batch upsert

**Problema**: `autodream_consolidate()` hace upserts individuales para cada memoria promovida.

**Solución**: Añadir `batch_upsert(ids, vectors, payloads)` a QdrantClient. Usarlo en consolidate, dream, y batch ingestion.

**Archivos**:
- `src/shared/qdrant_client.py` — Añadir `batch_upsert()`
- `src/autodream/server/main.py` — Usar batch_upsert en consolidate/promote

**Criterio de aceptación**:
- [ ] `batch_upsert(10 items)` funciona correctamente
- [ ] Consolidate con 50+ memorias usa batch en vez de 50 upserts individuales
- [ ] Latencia de consolidate con batch es <50% de individual
- [ ] Datos en Qdrant son idénticos antes/después del refactor

---

### OPT-05: Reconexión automática en extensión Pi

**Problema**: Si el proceso MCP muere, la extensión Pi falla todas las tool calls sin recuperación.

**Solución**: La extensión detecta process exit, re-spawnea, re-initializa, y re-registra tools automáticamente. Reintento con backoff exponencial.

**Archivos**:
- `~/.pi/agent/extensions/mcp-memory/index.ts` — Añadir reconnect logic

**Criterio de aceptación**:
- [ ] Si MCP muere, extensión lo detecta en <5s
- [ ] Auto-reconnect en <3s tras detectar muerte
- [ ] Tool calls durante reconnect esperan (no fallan inmediatamente)
- [ ] Máximo 3 intentos de reconnect, luego error claro
- [ ] Log de reconnect visible en stderr

---

### OPT-06: Content truncation inteligente

**Problema**: Content >1000 chars causa latencia 155ms. El truncado actual es un `text[:2000]` que corta a medias.

**Solución**: Truncado inteligente por oraciones, con summary del resto para no perder contexto.

**Archivos**:
- `src/shared/embedding.py` — Modificar `get_embedding()` truncation
- `src/shared/text.py` — Nuevo: `smart_truncate(text, max_chars=2000)`

**Criterio de aceptación**:
- [ ] 5K chars se trunca a ~2000 chars sin cortar oraciones a medias
- [ ] Latencia para 5K chars baja de 155ms a <60ms
- [ ] Embedding quality no degrada (score dentro de -0.02 del embedding completo)
- [ ] Test con texto que tiene oraciones, párrafos, y listas

---

### OPT-07: Embedding model upgrade path (F16 vs Q4)

**Problema**: bge-m3 Q4_K_M tiene quality gap bajo (+0.03). Modelos F16 o no cuantizados tendrían mejor separation.

**Solución**: Documentar y automatizar el upgrade a F16 o bf16. Añadir benchmark de calidad al verify.sh.

**Archivos**:
- `install.sh` — Añadir opción `--model-precision=f16|q4`
- `verify.sh` — Añadir quality benchmark step
- `docs/embedding-quality.md` — Nuevo: guía de calidad/latencia tradeoffs

**Criterio de aceptación**:
- [ ] `install.sh --model-precision=f16` descarga modelo F16
- [ ] Quality benchmark: gap relevante/irrelevante > +0.10
- [ ] Documentación clara del tradeoff latencia vs calidad
- [ ] verify.sh muestra quality score tras instalación

---

### OPT-08: Layer compaction (L1→L4 lifecycle)

**Problema**: Consolidação no promueve memorias efectivamente. `get_semantic()` y `get_consolidated()` devuelven count=0.

**Solución**: Lower promotion thresholds para testing. Añadir tool `autodream_force_promote(layer, count)` para debugging. Verificar que el lifecycle completo funciona.

**Archivos**:
- `src/autodream/server/main.py` — Ajustar thresholds, añadir force_promote
- `src/shared/config.py` — Añadir configurable promotion intervals

**Criterio de aceptación**:
- [ ] `consolidate(force=True)` promueve al menos 1 memoria de L1→L2
- [ ] `get_semantic()` devuelve >0 memorias tras consolidate
- [ ] `get_consolidated()` devuelve >0 memorias tras 2 consolidaciones
- [ ] Promotion thresholds son configurables via env vars

---

### OPT-09: Estandarizar status codes

**Problema**: Inconsistencia cosmética: `automem` devuelve `"stored"`, `conversation_store` devuelve `"saved"`, `mem0` devuelve `"added"`.

**Solución**: Estandarizar a `"stored"` en todos los módulos. Mantener backward compat con los valores antiguos como aliases.

**Archivos**:
- `src/conversation-store/server/main.py` — `"saved"` → `"stored"`
- `src/mem0/server/main.py` — `"added"` → `"stored"`
- `src/engram/server/main.py` — Verificar consistencia

**Criterio de aceptación**:
- [ ] Todos los módulos devuelven `status: "stored"` al guardar
- [ ] Tests existentes siguen pasando (o se actualizan)
- [ ] Documentación actualizada

---

### OPT-10: Observabilidad — latency tracking

**Problema**: No hay visibilidad de qué componente tarda cuánto dentro de cada tool call.

**Solución**: Añadir latency breakdown al response de cada tool. Campo opcional `_debug` con timing de embed, qdrant, validation, etc.

**Archivos**:
- `src/shared/timing.py` — Nuevo: context manager para timing
- Todos los server/main.py — Añadir timing breakdown

**Criterio de aceptación**:
- [ ] `automem_memorize` devuelve `_debug: {embed_ms: 15, qdrant_ms: 12, total_ms: 46}`
- [ ] Debug info es opcional (env var `MCP_DEBUG=1` para activar)
- [ ] No impacta latencia cuando debug está desactivado

---

## No-go (justificación)

| Idea | Por qué no |
|------|-----------|
| Cambiar a Qdrant gRPC | Complejidad extra, HTTP ya tiene connection pooling |
| Caching en la extensión Pi | Duplica state, inconsistencies risk |
| Multi-process MCP | Complejidad innecesaria para single-user |
| Cambiar a modelo más pequeño | Pierde quality, bge-m3 es el sweet spot |
