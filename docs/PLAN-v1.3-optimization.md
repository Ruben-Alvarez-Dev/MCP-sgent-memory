# MCP-agent-memory v1.3.0 — Execution Plan

> Spec-driven, episodic, granular. Cada episode es atomic y deployable.

## Episodes Overview

```
E01: Score threshold        ← quality + search filtering
E02: Dream async             ← estabilidad + UX
E03: Batch upsert            ← performance bulk ops
E04: Content truncation      ← latency para textos largos
E05: Status standardization  ← consistencia API
E06: Observability           ← debug capability
E07: Prefetch heartbeat      ← latency optimization
E08: Auto-reconnect Pi       ← resiliencia
E09: Layer compaction fix    ← data lifecycle
E10: Embedding upgrade path  ← quality
```

---

## E01: Score threshold configurable
**Prioridad**: ALTA (mejora calidad de búsqueda inmediatamente)
**Estimación**: 1.5h
**Dependencias**: Ninguna

### E01.S1: Añadir min_score param a qdrant_client.search()
```
Archivo: src/shared/qdrant_client.py
- Modificar search() para aceptar score_threshold como param (ya lo tiene como default)
- Exportar helper search_with_threshold(vector, limit, threshold)
Test: test_qdrant_search_threshold()
```

### E01.S2: Añadir min_score a mem0_search_memory
```
Archivo: src/mem0/server/main.py
- Añadir param min_score: float = 0.5
- Pasar threshold a qdrant.search(vector, score_threshold=min_score)
Test: test_mem0_search_with_min_score()
  - Store 3 memorias con contenido diverso
  - Search irrelevante con min_score=0.7 → 0 resultados
  - Search relevante con min_score=0.5 → al menos 1 resultado
```

### E01.S3: Añadir min_score a conversation_store_search
```
Archivo: src/conversation-store/server/main.py
- Añadir param min_score: float = 0.5
- Pasar threshold a qdrant.search()
Test: test_conv_search_with_min_score()
```

### E01.S4: Verificar que vk_cache ya lo usa correctamente
```
Archivo: src/vk-cache/server/main.py
- Verificar que usa config.vk_min_score
- Añadir log del threshold usado
Test: test_vk_cache_uses_threshold()
```

### E01.S5: Integration test
```
- E2E: store 5 memorias → search irrelevante → verify 0 results
- E2E: search relevante → verify results con score >= 0.5
- Verify backward compat: search sin min_score funciona igual
```

**Criterio de despliegue**: Todos los tests pasan, quality gap medible > +0.05

---

## E02: Dream async (non-blocking)
**Prioridad**: ALTA (bloquea el cliente Pi)
**Estimación**: 3h
**Dependencias**: Ninguna

### E02.S1: Crear task_queue.py
```
Archivo: src/shared/task_queue.py (NUEVO)
- TaskTracker class con asyncio.create_task
- track(task_id, coroutine) → task_id
- get_status(task_id) → {status, progress, result, error}
- tasks se limpian tras 1h
Test: test_task_tracker_basic()
```

### E02.S2: Refactor dream() a background task
```
Archivo: src/autodream/server/main.py
- Dream actual → _dream_impl() (internal)
- Nuevo dream() → schedulea _dream_impl via TaskTracker, devuelve task_id
- Resultado: {status: "dream_scheduled", task_id: "..."}
Test: test_dream_returns_immediately()
```

### E02.S3: Añadir tool dream_status
```
Archivo: src/autodream/server/main.py
- Nueva tool: autodream_dream_status(task_id: str)
- Devuelve: {status: "running"|"completed"|"failed", result: {...}, duration_ms: ...}
- Registrar como mcp.tool en register_tools()
Test: test_dream_status_completed(), test_dream_status_unknown()
```

### E02.S4: Actualizar extensión Pi
```
Archivo: ~/.pi/agent/extensions/mcp-memory/index.ts
- Actualizar promptSnippet de autodream_dream
- Añadir promptSnippet para autodream_dream_status
```

### E02.S5: Integration test
```
- E2E: dream() responde en <50ms
- E2E: dream_status() muestra "running" luego "completed"
- E2E: Si Ollama cae, dream_status muestra "failed" (no crash)
```

**Criterio de despliegue**: dream() nunca bloquea >100ms, dream_status() funcional

---

## E03: Batch upsert en Qdrant
**Prioridad**: MEDIA
**Estimación**: 2h
**Dependencias**: Ninguna

### E03.S1: Añadir batch_upsert a QdrantClient
```
Archivo: src/shared/qdrant_client.py
- async batch_upsert(items: list[{id, vector, payload, sparse}])
- Usa Qdrant /points batch API
- Chunk en grupos de 100 si necesario
Test: test_batch_upsert_10_items(), test_batch_upsert_200_items()
```

### E03.S2: Refactor consolidate para usar batch
```
Archivo: src/autodream/server/main.py
- _promote_l1_l2: recolectar items, luego batch_upsert
- _promote_l2_l3: idem
Test: test_consolidate_uses_batch()
```

### E03.S3: Benchmark batch vs individual
```
Script: tests/bench_batch_upsert.py
- 50 upserts individual vs 1 batch de 50
- Verificar speedup > 2x
- Verificar datos idénticos
```

**Criterio de despliegue**: Batch funciona, consolidate usa batch, speedup medible

---

## E04: Content truncation inteligente
**Prioridad**: MEDIA
**Estimación**: 2h
**Dependencias**: Ninguna

### E04.S1: Crear text.py con smart_truncate
```
Archivo: src/shared/text.py (NUEVO)
- smart_truncate(text, max_chars=2000) → str
- Corta en último punto/oración dentro del límite
- Añade "..." si truncó
- Preserva primeros y últimos chars (head + tail strategy para embeddings)
Test: test_smart_truncate_sentence(), test_smart_truncate_paragraph(),
      test_smart_truncate_short(), test_smart_truncate_list()
```

### E04.S2: Usar smart_truncate en get_embedding
```
Archivo: src/shared/embedding.py
- Reemplazar text[:2000] por smart_truncate(text, 2000)
Test: test_embed_5k_chars_latency() → <60ms
```

### E04.S3: Quality regression test
```
- Embed 5 textos de 5K chars con truncate viejo vs nuevo
- Verificar cosine similarity > 0.95 entre ambos embeddings
- Verificar latency < 60ms
```

**Criterio de despliegue**: 5K chars <60ms, quality no degrada

---

## E05: Estandarizar status codes
**Prioridad**: BAJA (cosmético)
**Estimación**: 1h
**Dependencias**: Ninguna

### E05.S1: Estandarizar a "stored"
```
Archivos:
- src/conversation-store/server/main.py: "saved" → "stored"
- src/mem0/server/main.py: "added" → "stored"
- Verificar engram ya usa "saved"/"written" (mantener, son domain-specific)
Test: Actualizar tests existentes
```

### E05.S2: Documentar status codes
```
Archivo: docs/api-reference.md (NUEVO o actualizar)
- Tabla: módulo → operación → status code
- Backward compat note
```

**Criterio de despliegue**: Tests pasan, docs actualizados

---

## E06: Observability — latency tracking
**Prioridad**: MEDIA (debug capability)
**Estimación**: 2h
**Dependencias**: Ninguna

### E06.S1: Crear timing.py
```
Archivo: src/shared/timing.py (NUEVO)
- @timed_tool decorator para MCP tools
- Accumulate timing dentro de cada tool call
- Debug output solo si MCP_DEBUG=1
Test: test_timed_decorator()
```

### E06.S2: Aplicar a tools principales
```
Archivos: automem, mem0, conversation-store, engram server/main.py
- Decorar memorize, search, save_conversation, save_decision
- Añadir _debug field al response cuando MCP_DEBUG=1
Test: test_debug_output()
```

### E06.S3: Extension Pi muestra timing
```
Archivo: ~/.pi/agent/extensions/mcp-memory/index.ts
- Si response tiene _debug, log a stderr
```

**Criterio de despliegue**: MCP_DEBUG=1 muestra breakdown, MCP_DEBUG=0 zero overhead

---

## E07: Embedding prefetch en heartbeat
**Prioridad**: MEDIA
**Estimación**: 2h
**Dependencias**: E06 (timing para medir impacto)

### E07.S1: Añadir pending_queries a heartbeat
```
Archivo: src/automem/server/main.py
- Nuevo param: pending_queries: list[str] = []
- Si no vacío, llamar async_embed_batch(pending_queries) en background
- No bloquear el heartbeat response
Test: test_heartbeat_with_prefetch()
```

### E07.S2: Verificar cache hit post-prefetch
```
Test: test_prefetch_creates_cache_hit()
- heartbeat con pending_queries=["query1"]
- Luego mem0_search("query1") → embed_ms < 5ms (cache hit)
```

### E07.S3: Extension Pi envía queries de contexto
```
Archivo: ~/.pi/agent/extensions/mcp-memory/index.ts
- Al recibir tool_call, extraer query del params
- Incluir en próximo heartbeat como pending_queries
```

**Criterio de despliegue**: Prefetch funciona, cache hits medibles

---

## E08: Auto-reconnect extensión Pi
**Prioridad**: ALTA (resiliencia)
**Estimación**: 3h
**Dependencias**: Ninguna

### E08.S1: Detectar process exit
```
Archivo: ~/.pi/agent/extensions/mcp-memory/index.ts
- proc.on('exit') → marcar client como dead
- Pendings requests → enqueue para retry
```

### E08.S2: Reconnect con backoff
```
Archivo: ~/.pi/agent/extensions/mcp-memory/index.ts
- reconnect() con exponential backoff: 1s, 2s, 4s
- Máximo 3 intentos
- Re-initializa: initialize() + tools/list()
- NO re-registrar tools (Pi no lo soporta dinámicamente)
- Flag existing tools como "reconnected"
```

### E08.S3: Queue pending calls durante reconnect
```
Archivo: ~/.pi/agent/extensions/mcp-memory/index.ts
- Pending calls se encolan
- Tras reconnect, se reenvían
- Timeout total: 30s (incluye reconnect time)
```

### E08.S4: Test de resiliencia
```
- Matamos proceso MCP manualmente
- Ejecutamos tool call → espera reconnect
- Verificar que responde tras reconnect
- Verificar que falla claro tras 3 intentos
```

**Criterio de despliegue**: MCP muere → auto-reconnect → tools siguen funcionando

---

## E09: Layer compaction fix
**Prioridad**: MEDIA
**Estimación**: 2h
**Dependencias**: E03 (batch upsert)

### E09.S1: Debuggear promotion pipeline
```
- Añadir logging detallado a _promote_l1_l2, _promote_l2_l3
- Verificar que los thresholds son alcanzables
- Verificar que Qdrant filters son correctos
```

### E09.S2: Añadir force_promote tool
```
Archivo: src/autodream/server/main.py
- Nueva tool: autodream_force_promote(from_layer: int, count: int = 10)
- Fuerza promoción de N memorias de from_layer a from_layer+1
- Útil para debugging y testing
Test: test_force_promote_l1_to_l2()
```

### E09.S3: Configurable thresholds
```
Archivo: src/shared/config.py
- PROMOTE_L1_THRESHOLD, PROMOTE_L2_THRESHOLD, PROMOTE_L3_THRESHOLD
- Defaults razonables (5 turns para L1→L2, etc.)
- Env vars para override
```

### E09.S4: Integration test completo
```
- Store 10 memorias en L1
- force_promote(from_layer=1, count=10)
- Verificar get_semantic() > 0
- force_promote(from_layer=2, count=10)
- Verificar get_consolidated() > 0
```

**Criterio de despliegue**: Lifecycle L1→L2→L3→L4 funciona end-to-end

---

## E10: Embedding upgrade path
**Prioridad**: BAJA (investigación)
**Estimación**: 2h
**Dependencias**: E06 (timing para benchmark)

### E10.S1: Benchmark F16 vs Q4 quality
```
Script: tests/bench_embedding_quality.py
- Download bge-m3-F16.gguf (si existe) o bf16
- Benchmark: 20 pares de queries relevantes/irrelevantes
- Medir: quality gap, latency, memory usage
```

### E10.S2: Añadir opción al installer
```
Archivo: install.sh
- --model-precision=q4 (default) o --model-precision=f16
- Auto-detect disponible
```

### E10.S3: Quality benchmark en verify.sh
```
Archivo: verify.sh
- Step: embedding quality test
- Store 5 memorias, search 5 queries (3 relevantes + 2 irrelevantes)
- Verify avg relevant score > avg irrelevant score + 0.10
```

**Criterio de despliegue**: Tradeoff documentado, installer soporta ambas opciones

---

## Orden de ejecución

```
Sprint 1 (estabilidad + quality):
  E01 Score threshold      → filtrado de ruido
  E02 Dream async          → no más timeouts
  E08 Auto-reconnect       → resiliencia

Sprint 2 (performance):
  E03 Batch upsert         → bulk ops
  E04 Content truncation   → latencia textos largos
  E06 Observability        → debug capability

Sprint 3 (lifecycle + polish):
  E09 Layer compaction     → data lifecycle
  E07 Prefetch heartbeat   → cache hits
  E05 Status standardize   → consistencia
  E10 Embedding upgrade    → quality (opcional)
```

## Definition of Done (por episode)

1. Spec items verdes (todos los criterios de aceptación)
2. Tests unitarios pasando
3. Integration test E2E pasando
4. Commit + push con mensaje descriptivo
5. Tag al final de cada sprint
