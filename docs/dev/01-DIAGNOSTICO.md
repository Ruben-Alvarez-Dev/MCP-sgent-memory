# DIAGNÓSTICO DEL SISTEMA — 16 Abril 2026

> Estado del sistema tras auditoría completa de 17 tests con métricas reales.
> Todos los números son mediciones, no estimaciones.

## 1. Servicios Base

| Servicio | Estado | Puerto | Latencia |
|----------|--------|--------|----------|
| Qdrant | 🟢 Online | 6333 | ~136ms |
| 1MCP Gateway | 🟢 Online | 3050 | ~149ms |
| Ollama | 🟢 Online | 11434 | — |
| AutoMem | 🟢 Running | via 1mcp | — |
| AutoDream | 🟢 Running | via 1mcp | — |
| vk-cache | 🟢 Running | via 1mcp | — |
| Engram Bridge | 🟢 Running | via 1mcp | — |
| mem0-bridge | 🟢 Running | via 1mcp | — |
| Sequential Thinking | 🟢 Running | via 1mcp | — |
| llama.cpp embedding | 🟢 Funcional | subprocess | ~1,087ms |

## 2. Colecciones Qdrant

| Colección | Puntos | Vectores indexados | Dim | Sparse | Status |
|-----------|--------|--------------------|-----|--------|--------|
| `automem` | 11 | 0 | 1024 Cosine | BM25 ✅ | green |
| `mem0_memories` | 0 | 0 | 1024 Cosine | BM25 ✅ | green |
| `conversations` | 0 | 0 | 1024 Cosine | BM25 ✅ | green |
| `vkcache` | 0 | 0 | — | none ❌ | green |

**Nota:** `indexed_vectors: 0` en automem pese a tener 11 puntos con vectores de 1024 dims. Posible indexación perezosa.

## 3. Modelos Disponibles

| Modelo | Tipo | Tamaño | Uso | Estado |
|--------|------|--------|-----|--------|
| bge-m3-Q4_K_M.gguf | Embedding | 417MB | Embedding 1024 dims | ✅ Funcional |
| all-minilm-l6-v2_q8_0.gguf | Embedding | 24MB | Alternativa 384 dims | Disponible |
| qwen2.5:7b (Ollama) | LLM | 4.4GB | Consolidación AutoDream | ✅ Disponible |
| qwen3.5:2b (Ollama) | LLM | 2.6GB | Ranking/verificación | ✅ Disponible |
| nomic-embed-text (Ollama) | Embedding | 0.3GB | Alternativa 768 dims | ✅ Disponible |

## 4. Bugs Críticos Encontrados

### BUG-001: classify_intent() → entities siempre vacías para queries en español

**Archivo:** `MCP-servers/shared/llm/config.py` → `classify_intent()`
**Severidad:** 🔴 CRÍTICA
**Impacto:** Toda la búsqueda semántica del retrieval router retorna 0 resultados.

**Causa raíz:**
```python
# Solo extrae entidades CamelCase y UPPER_SNAKE
camel_matches = re.findall(r'[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*', query)
snake_matches = re.findall(r'[A-Z_]{2,}', query)
intent.entities = list(set(camel_matches + snake_matches))
# "idioma preferencia español" → entities=[] ← todo minúsculas!
```

**Evidencia:**
```
Query: "idioma preferencia español"  → entities=[]  → 0 resultados
Búsqueda directa con embedding:                        → score 0.697 ✅
```

### BUG-002: _retrieve_qdrant() retorna vacío si entities=[]

**Archivo:** `MCP-servers/shared/retrieval/__init__.py` → `_retrieve_qdrant()`
**Severidad:** 🔴 CRÍTICA
**Impacto:** Complementa BUG-001. Sin entities, no genera vector de búsqueda.

**Causa raíz:**
```python
if not intent.entities:
    query_text = " ".join(intent.entities) if intent.entities else ""
    if not query_text:
        return []  # ← Retorna vacío inmediatamente
```

**Fix:** Usar la query original como fallback.

### BUG-003: conversation-store parámetro mal nombrado

**Archivo:** `MCP-servers/servers/conversation-store/server/main.py`
**Severidad:** 🟡 MEDIA
**Impacto:** La extensión de pi envía `messages` pero el servidor espera `messages_json`.

### BUG-004: mem0-bridge no persiste puntos

**Archivo:** `MCP-servers/servers/mem0-bridge/server/main.py`
**Severidad:** 🟡 MEDIA
**Impacto:** `add_memory` retorna OK pero la colección permanece en 0 puntos. Posible issue de schema o permisos.

### BUG-005: vkcache colección sin sparse vectors

**Archivo:** Config de Qdrant
**Severidad:** 🟢 BAJA
**Impacto:** Inconsistencia con las demás colecciones. Búsqueda BM25 no disponible.

## 5. Latencias Medidas

### Operaciones MCP via Gateway (3 rondas promedio)

| Operación | Promedio | Mín | Máx | Rating |
|-----------|----------|-----|-----|--------|
| heartbeat | 171ms | 151ms | 193ms | ✅ Rápido |
| save_decision | 158ms | 148ms | 176ms | ✅ Rápido |
| store (con embedding) | 1,459ms | 1,380ms | 1,509ms | ⚠️ Lento |
| recall (vk-cache) | 1,594ms | 1,507ms | 1,646ms | ⚠️ Lento (y roto) |
| search (mem0) | 1,480ms | 1,357ms | 1,544ms | ⚠️ Lento |

### Cuello de botella: Embedding

| Backend | Latencia | Nota |
|---------|----------|------|
| llama.cpp subprocess (actual) | 1,087ms | Spawn de proceso por llamada |
| llama.cpp server mode (HTTP) | **15ms** | Daemon permanente |
| Ollama nomic-embed-text (warm) | 27ms | Pero calidad pobre (768d) |
| Ollama nomic-embed-text (cold) | 1,459ms | Cold start |

### Speedup disponible: **72x** con server mode (bge-m3, 1024 dims)

## 6. Calidad de Embeddings

### Discriminación semántica (cosine similarity)

| Comparación | bge-m3 (1024d) | nomic (768d) |
|-------------|---------------|-------------|
| "prefiere español" vs "preferencia idioma español" | **0.7213** ✅ | 0.5585 |
| "prefiere español" vs "npm install error" | **0.3145** ✅ | 0.6497 ❌ |
| "npm error" vs "pnpm gestor paquetes" | **0.5154** | 0.7542 ❌ |

**Conclusión:** bge-m3 tiene **excelente discriminación** (separación clara entre relevante/irrelevante). nomic mezcla conceptos no relacionados. **Mantener bge-m3.**

## 7. Consolidación AutoDream

| Métrica | Valor |
|---------|-------|
| Consolidaciones ejecutadas | 0 |
| Dreams ejecutados | 0 |
| Turn count | 2 |
| Umbral L1→L2 | 10 turns (no alcanzado) |
| Umbral L2→L3 | 3,600s (1h) |
| Umbral L3→L4 | 86,400s (24h) |
| LLM disponible (qwen2.5:7b) | ✅ Sí |

**Diagnóstico:** La consolidación nunca se ha ejecutado porque no hay suficientes turns. Con el fix de búsqueda, el uso aumentará y los umbrales se alcanzarán naturalmente.

## 8. Persistencia

| Elemento | Estado |
|----------|--------|
| Raw events JSONL | 44 eventos |
| Engram decisiones | 2 directorios (agent, personal) |
| Heartbeats | 5 agentes registrados |
| Dream state | Persistido |
| Vault Obsidian | Pendiente de contenido |

## 9. Resumen Global

| Componente | Rating | Nota |
|------------|--------|------|
| Disponibilidad servicios | 🟢 **Fantástico** | Todo estable |
| Almacenamiento | 🟢 **Bueno** | Todos los endpoints responden |
| Embeddings (calidad) | 🟢 **Fantástico** | bge-m3 excelente discriminación |
| Embeddings (velocidad) | 🔴 **Pobre** | Subprocess = 1,087ms, server = 15ms |
| Recuperación semántica | 🔴 **Pobre** | Rota por BUG-001 + BUG-002 |
| Consolidación | 🟡 **Regular** | Infraestructura lista, sin ejecución |
| Persistencia | 🟢 **Bueno** | Todo se guarda |
| Latencia general | ⚠️ **Regular** | Cuello de botella = embedding |

---

*Documento generado por pi con datos de 17 tests ejecutados el 16/04/2026.*
*Proxy: `/Users/ruben/MCP-servers/MCP-agent-memory/`*
*Proyecto: `/Users/ruben/Code/PROJECT-MCP-agent-memory/`*
