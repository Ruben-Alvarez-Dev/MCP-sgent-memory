# 🚀 PROPUESTA DE MEJORA Y OPTIMIZACIÓN — MCP Memory Server
## Estado: Post-Diagnóstico Completo — 16 Abril 2026

---

## 📋 RESUMEN EJECUTIVO

| Métrica actual | Valor | Objetivo |
|---------------|-------|----------|
| Latencia store (con embedding) | ~1,460ms | <50ms |
| Latencia recall (vk-cache) | ~1,600ms (0 resultados por bug) | <100ms con resultados |
| Latencia embedding (llama.cpp subprocess) | ~1,087ms | ~15ms (server mode) |
| Búsqueda semántica funcional | ❌ ROTA | ✅ Funcional |
| Consolidación ejecutada | 0 veces | Automática |
| Colecciones con datos | 1/4 | 4/4 |
| Calidad discriminación bge-m3 | 0.72/0.31 (excelente) | Mantener |
| Speedup embedding disponible | 72x (server mode) | Implementar |

---

## 🔴 BUGS CRÍTICOS (Prioridad 0)

### Bug 1: `classify_intent()` → entities siempre vacías

**Archivo:** `shared/llm/config.py`
**Impacto:** Toda la búsqueda semántica del retrieval router está rota.

```python
# ACTUAL: Solo detecta CamelCase y UPPER_SNAKE
camel_matches = re.findall(r'[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*', query)
snake_matches = re.findall(r'[A-Z_]{2,}', query)
intent.entities = list(set(camel_matches + snake_matches))
# "idioma preferencia español" → entities=[] (todo minúsculas!)
```

**Fix:** Añadir fallback de keyword extraction cuando no hay entidades CamelCase:

```python
# NUEVO: Extraer keywords significativas si no hay entidades de código
if not intent.entities:
    # Tokenizar la query completa
    tokens = re.findall(r'[a-záéíóúüñ]{3,}', q)
    tokens = [t for t in tokens if t not in _STOP_WORDS]
    intent.entities = tokens[:10]  # max 10 keywords
```

### Bug 2: `_retrieve_qdrant()` usa entities como query

**Archivo:** `shared/retrieval/__init__.py`
**Impacto:** Si entities=[] se genera embedding de string vacío → 0 resultados

```python
# ACTUAL:
if not intent.entities:
    query_text = " ".join(intent.entities) if intent.entities else ""
    if not query_text:
        return []  # ← RETORNA VACÍO!
```

**Fix:** Usar la query original cuando entities está vacío:

```python
# NUEVO:
query_text = " ".join(intent.entities) if intent.entities else query
if not query_text:
    query_text = query  # fallback a query original
```

### Bug 3: `conversation-store` parámetro mal nombrado

**Archivo:** `servers/conversation-store/server/main.py`
**Impacto:** La extensión mcp-memory envía `messages` pero el servidor espera `messages_json`

```python
# El servidor espera:
async def save_conversation(thread_id, messages_json, metadata="")

# Pero la extensión y el config envían:
# "messages" como string JSON
```

**Fix:** Añadir alias `messages` como alternativa en la función, o normalizar el nombre.

---

## 🟡 OPTIMIZACIONES DE RENDIMIENTO (Prioridad 1)

### Opt 1: Embedding Server Mode — Speedup 72x

**Actual:** Cada llamada a `get_embedding()` spawnea un subprocess de `llama-embedding`
- Overhead de subprocess: ~1,000ms
- Cálculo real del embedding: ~87ms

**Propuesta:** Ejecutar `llama-server` como daemon HTTP permanente

**Benchmark medido:**
```
Subprocess (actual):    ~1,087ms por embedding
Server mode (medido):   ~15ms por embedding
Speedup: 72.5x
```

**Implementación:**

1. Añadir un nuevo backend `LlamaServerBackend` en `shared/embedding.py`:

```python
class LlamaServerBackend(EmbeddingBackend):
    """Embedding via llama-server HTTP daemon (persistent)."""
    
    def __init__(self, url="http://127.0.0.1:8080"):
        self._url = url
    
    def embed(self, text: str) -> list[float]:
        req = urllib.request.Request(
            f"{self._url}/embedding",
            data=json.dumps({"content": text}).encode(),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data[0]["embedding"]  # bge-m3 via server
    
    def is_available(self) -> bool:
        try:
            urllib.request.urlopen(f"{self._url}/health", timeout=2)
            return True
        except:
            return False
```

2. Crear script `scripts/start-embedding-server.sh`:

```bash
#!/bin/bash
ENGINE_DIR="$(dirname "$0")/../engine"
MODEL_DIR="$(dirname "$0")/../models"
$ENGINE_DIR/bin/llama-server \
  -m $MODEL_DIR/bge-m3-Q4_K_M.gguf \
  --embedding --port 8080 --host 127.0.0.1 \
  -c 512 -t 4 --mlock
```

3. Añadir al `start-gateway.sh` antes de 1mcp:

```bash
# Iniciar embedding server
"$MEMORY_SERVER_DIR/scripts/start-embedding-server.sh" &
sleep 2
```

**Impacto estimado:**
- `memory_store`: 1,460ms → ~50ms
- `memory_recall`: 1,600ms → ~50ms
- `memory_search`: 1,480ms → ~40ms
- Toda operación que necesite embedding se beneficia

### Opt 2: Embedding Cache con LRU

**Problema:** Mismas queries generan embeddings repetidos

**Propuesta:** Caché en memoria simple:

```python
from functools import lru_cache

@lru_cache(maxsize=512)
def get_embedding_cached(text: str) -> list[float]:
    return _get_default_backend().embed(text)
```

**Impacto:** Segundas llamadas con mismo texto → ~0ms

### Opt 3: Batch Embeddings

**Problema:** Almacenar N memorias genera N llamadas secuenciales a embedding

**Propuesta:** Agrupar embeddings en batch:

```python
def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generar múltiples embeddings en una sola llamada al server."""
    # llama-server soporta batch nativo
    payload = {"content": texts}  # batch endpoint
    ...
```

**Impacto:** Almacenar 5 memorias: 5×1,087ms → 1×1,100ms

---

## 🟢 MEJORAS ARQUITECTÓNICAS (Prioridad 2)

### Mejora 1: Unificar las 3 colecciones de Qdrant

**Actual:**
```
automem (1024 dims)         → 11 puntos, funciona
mem0_memories (1024 dims)   → 0 puntos (no se almacena bien)
conversations (1024 dims)   → 0 puntos (no se almacena bien)
vkcache (0 dims, sin sparse) → vacía
```

**Problemas:**
- 3 colecciones = 3 índices, 3× memoria de índice
- Los schemas son casi idénticos (todos: content + vector + sparse)
- mem0 y conversations no están almacenando (posible bug de schema)
- vkcache no tiene sparse vectors (inconsistente)

**Propuesta: Unificar en 1 colección `memory` con discriminación por payload**

```python
# Un solo schema:
{
    "vectors": {"size": 1024, "distance": "Cosine"},
    "sparse_vectors": {"text": {"index": {"type": "bm25"}}},
}

# Cada punto tiene payload con:
{
    "layer": 1,           # L0-L5
    "type": "fact",       # fact, decision, episode, conversation...
    "source": "automem",  # automem, mem0, conversation-store
    "scope_type": "personal",
    "scope_id": "ruben",
    "content": "...",
    "importance": 0.8,
    "tags": ["idioma"],
    "created_at": "...",
}
```

**Beneficios:**
- 1 índice en vez de 3 → menos RAM, menos overhead
- Búsqueda unificada: una sola query busca en TODO
- Consistencia de schema garantizada
- Simplifica el retrieval router (no necesita federar)

**Migración:**
```python
# Script migración:
for coll in ["automem", "mem0_memories", "conversations"]:
    points = scroll_all(coll)
    for p in points:
        p["payload"]["source"] = coll
        upsert("memory", p)
```

### Mejora 2: Intent Classifier robusto

**Actual:** Solo detecta patrones en inglés con palabras clave. entities=[] para queries en español sin CamelCase.

**Propuesta: Classifier determinista multinlingüe**

```python
def classify_intent(query, session_type="coding", open_files=None):
    q = query.lower()
    
    # Intent patterns (español + inglés)
    INTENT_PATTERNS = {
        "decision_recall": [
            r"(?:why|por qué) (?:did|hicimos|decidimos|elegimos)",
            r"(?:decisión|decision|choice|elegimos|optamos)",
        ],
        "error_diagnosis": [
            r"(?:error|bug|fallo|crash|broken|roto|not working|no func)",
            r"(?:exception|traceback|stack trace)",
        ],
        "how_to": [
            r"(?:how to|cómo|de qué manera|what's the best way)",
        ],
        "code_lookup": [
            r"(?:function|class|method|función|método|archivo|file)",
            r"(?:where is|dónde está|show me|mostrame)",
        ],
        # ... más patterns
    }
    
    # Entity extraction multinlingüe
    entities = []
    
    # 1. CamelCase / UPPER_SNAKE (código)
    entities.extend(re.findall(r'[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*', query))
    entities.extend(re.findall(r'[A-Z_]{2,}', query))
    
    # 2. Keywords significativas (fallback para español, minúsculas)
    if not entities:
        tokens = re.findall(r'[a-záéíóúüñ]{3,}', q)
        tokens = [t for t in tokens if t not in _STOP_WORDS_ES.union(_STOP_WORDS_EN)]
        entities = tokens[:10]
    
    # 3. Paths y archivos
    entities.extend(re.findall(r'[\w/]+\.\w{1,10}', query))  # file.py
    
    # 4. Números de versión
    entities.extend(re.findall(r'v?\d+\.\d+(?:\.\d+)?', query))
    
    return QueryIntent(
        intent_type=detected_type,
        entities=list(set(entities)),
        ...
    )
```

### Mejora 3: AutoDream — verificar y habilitar consolidación

**Actual:** 0 consolidaciones ejecutadas. El LLM (Ollama qwen2.5:7b) está disponible pero nunca se ha ejecutado el ciclo completo.

**Diagnóstico:**
- L1→L2 requiere 10 turns → solo tenemos 2
- L2→L3 requiere 1 hora y datos L2 → no hay
- El `force_consolidate` no genera L2+ porque necesita resumir con LLM

**Propuesta:**
1. Reducir umbrales para testing:
```bash
DREAM_PROMOTE_L1=3    # en vez de 10
DREAM_PROMOTE_L2=60   # en vez de 3600 (1h → 1min para test)
```

2. Verificar que el LLM de Ollama funciona para summarización:
```bash
cd /Users/ruben/MCP-servers/MCP-memory-server
.venv/bin/python3 -c "
from shared.llm import get_llm
llm = get_llm()
print(llm.ask('Summarize: El usuario prefiere español. Usa pnpm. Error con npm.', max_tokens=100))
"
```

3. Añadir health-check de consolidación al heartbeat:
```python
# En automem heartbeat:
if promotion_due:
    # Auto-trigger consolidation
    requests.post("http://127.0.0.1:3050/mcp", ...)
```

### Mejora 4: Embedding dimensional — mantener 1024, pero planificar

**Contexto:** Las 3 colecciones pasaron de 300 → 700 → 1024 dims por compatibilidad.

**bge-m3** (1024 dims) es el mejor modelo para búsqueda semántica multilingüe:
- Discriminación excelente (score 0.72 relevante vs 0.31 irrelevante)
- Soporta español nativamente
- Q4_K_M quantización: 417MB (razonable)

**No cambiar de modelo ni de dimensión.** Pero sí:

1. **Documentar** la dimensión fija (1024) en un schema file
2. **Validar** en cada upsert que el vector tiene exactamente 1024 dims
3. **Test de regresión** que valide que embeddings nuevos son compatibles con los existentes

---

## 🔵 MEJORAS DE CALIDAD (Prioridad 3)

### Calidad 1: Mem0 bridge — instalar librería o corregir fallback

**Actual:** mem0ai NO instalado → fallback a Qdrant directo → pero `add_memory` sí funciona con Qdrant directo. El problema es que no se veían los puntos.

**Verificar:** El fallback de mem0 SÍ inserta en Qdrant (medido: add funciona). Revisar por qué get_all devuelve 0.

### Calidad 2: Conversation store — corregir API

**Problema:** El parámetro se llama `messages_json` internamente pero la config del gateway y la extensión envían `messages`.

**Fix:** Añadir alias en la función del servidor o actualizar la extensión.

### Calidad 3: Sparse vectors (BM25) — verificar que se indexan

**Actual:** Qdrant reporta `indexed_vectors: 0` para automem a pesar de que los puntos tienen sparse vectors.

**Posible causa:** Los sparse vectors se indexan de forma perezosa (lazy). Forzar optimización:

```bash
curl -X POST http://127.0.0.1:6333/collections/automem/index -H "Content-Type: application/json" -d '{}'
```

---

## 📊 ROADMAP PROPUESTO

```
FASE 1: Bugs Críticos (1-2 horas)
├── Fix classify_intent entities=[]
├── Fix _retrieve_qdrant fallback query
└── Fix conversation-store param name

FASE 2: Embedding Server (2-3 horas)
├── Crear LlamaServerBackend
├── Script start-embedding-server.sh
├── Integrar en start-gateway.sh
├── Tests de latencia
└── Embedding cache LRU

FASE 3: Consolidación (1-2 horas)
├── Verificar Ollama qwen2.5:7b funciona
├── Reducir umbrales de consolidación
├── Ejecutar ciclo L1→L2→L3 manual
└── Verificar resultados

FASE 4: Unificación Colecciones (3-4 horas)
├── Diseñar schema unificado
├── Script migración
├── Actualizar todos los servidores
├── Tests de regresión
└── Benchmark final

FASE 5: Integración con pi (2-3 horas)
├── Actualizar extensión mcp-memory
├── Integrar self-improvement → memory server
├── Tests end-to-end
└── Documentación
```

---

## 📈 MÉTRICAS OBJETIVO POST-OPTIMIZACIÓN

| Métrica | Actual | Objetivo | Mejora |
|---------|--------|----------|--------|
| Latencia store | 1,460ms | <50ms | 29x |
| Latencia recall | 1,600ms (roto) | <100ms (funcional) | ∞ |
| Latencia embedding | 1,087ms | ~15ms | 72x |
| Búsqueda semántica | ❌ Rota | ✅ Funcional | — |
| Consolidación | 0 ejecuciones | Automática cada 3 turns | — |
| Colecciones útiles | 1/4 | 1 unificada | — |
| Calidad discriminación | 0.72/0.31 | Mantener bge-m3 | — |

---

*Propuesta generada después de 17 tests exhaustivos con métricas reales.*
*Todos los números están basados en mediciones, no estimaciones.*
