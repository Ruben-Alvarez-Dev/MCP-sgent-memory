# ESPECIFICACIÓN DE OPTIMIZACIÓN — MCP Memory Server V3.1

> Basado en el diagnóstico del 16/04/2026.
> Todas las optimizaciones están respaldadas por métricas reales.

## Objetivo

Llevar el sistema de su estado actual (búsqueda rota, 1.5s de latencia, 0 consolidaciones) a producción-ready:
- Búsqueda semántica funcional en <100ms
- Almacenamiento en <50ms
- Consolidación automática operativa
- 1 colección unificada en vez de 4

---

## FASE 1: BUGS CRÍTICOS

### TASK-1.1: Fix classify_intent() — entities vacías

**Archivo:** `MCP-servers/shared/llm/config.py`
**Prioridad:** P0 — Bloqueante
**Estimación:** 30 min

**Problema:** Solo extrae CamelCase/UPPER_SNAKE. Queries en español minúsculas → entities=[].

**Especificación del fix:**

```python
# Añadir después de la extracción actual de CamelCase/SNAKE:

# Fallback: keyword extraction para queries sin entidades de código
if not intent.entities:
    # Stop words español + inglés
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "how", "what", "why", "when", "where", "who", "which",
        "do", "does", "did", "will", "would", "could", "should",
        "el", "la", "los", "las", "un", "una", "de", "del", "que",
        "y", "o", "pero", "con", "sin", "para", "por", "se", "su",
        "como", "muy", "es", "son", "tiene", "este", "esta",
        "no", "si", "mi", "tu", "lo", "le", "me", "te", "nos",
    }
    tokens = re.findall(r'[a-záéíóúüñ]{3,}', q)
    tokens = [t for t in tokens if t not in STOP_WORDS]
    intent.entities = tokens[:10]
```

**Criterio de aceptación:**
```
Input:  "idioma preferencia español"
Output: entities=["idioma", "preferencia", "español"]

Input:  "error permisos npm install"
Output: entities=["error", "permisos", "npm", "install"]

Input:  "AuthService JWT token"
Output: entities=["AuthService", "JWT"]  # CamelCase sigue funcionando
```

### TASK-1.2: Fix _retrieve_qdrant() — fallback a query original

**Archivo:** `MCP-servers/shared/retrieval/__init__.py`
**Prioridad:** P0 — Bloqueante
**Estimación:** 15 min

**Problema:** Si entities=[] no genera embedding de búsqueda.

**Especificación del fix:**

```python
# Reemplazar el bloque actual:
# ANTES:
if not intent.entities:
    query_text = " ".join(intent.entities) if intent.entities else ""
    if not query_text:
        return []

# DESPUÉS:
# Prioridad: entities > query completa > return vacío
query_text = " ".join(intent.entities) if intent.entities else ""
if not query_text:
    query_text = intent.intent_type  # al menos el tipo de intent
if not query_text:
    return []
```

**Nota:** TASK-1.1 hace que esto casi nunca se active, pero es necesario como safety net.

### TASK-1.3: Fix conversation-store param name

**Archivo:** `MCP-servers/servers/conversation-store/server/main.py`
**Prioridad:** P1
**Estimación:** 15 min

**Problema:** La función espera `messages_json` pero la extensión envía `messages`.

**Especificación del fix:**

```python
# Añadir alias en la función:
async def save_conversation(
    thread_id: str,
    messages: str = "",        # Nuevo: alias
    messages_json: str = "",   # Legacy
    metadata: str = "",
) -> str:
    raw = messages or messages_json  # Aceptar ambos
    messages_list = json.loads(raw)
    ...
```

**Actualizar también:** la extensión `~/.pi/agent/extensions/mcp-memory/index.ts` para enviar `messages_json`.

### TASK-1.4: Investigar mem0-bridge puntos vacíos

**Archivo:** `MCP-servers/servers/mem0-bridge/server/main.py`
**Prioridad:** P1
**Estimación:** 30 min

**Problema:** `add_memory` retorna OK, pero `get_all_memories` muestra 0 puntos.

**Investigación necesaria:**
1. Verificar que `add_memory` con fallback directo a Qdrant escribe realmente
2. Verificar que `get_all_memories` lee de la misma colección
3. Revisar si hay issue con el formato de punto (ID, vector, payload)

**Test de verificación:**
```bash
cd ~/MCP-servers/MCP-agent-memory
.venv/bin/python3 -c "
from servers.mem0_bridge.server.main import *
import asyncio
async def test():
    # Add directamente
    async with httpx.AsyncClient() as client:
        import uuid
        from shared.embedding import get_embedding
        vec = get_embedding('test mem0')
        point = {
            'id': str(uuid.uuid4()),
            'vector': vec,
            'payload': {'content': 'test mem0', 'user_id': 'ruben'},
        }
        resp = await client.put(
            'http://127.0.0.1:6333/collections/mem0_memories/points?wait=true',
            json={'points': [point]}
        )
        print(f'Insert: {resp.status_code} {resp.text[:200]}')
        
        # Verificar
        resp2 = await client.post(
            'http://127.0.0.1:6333/collections/mem0_memories/points/scroll',
            json={'limit': 10, 'with_payload': True}
        )
        print(f'Scroll: {resp2.json()}')
asyncio.run(test())
"
```

---

## FASE 2: EMBEDDING SERVER MODE

### TASK-2.1: Implementar LlamaServerBackend

**Archivo:** `MCP-servers/shared/embedding.py`
**Prioridad:** P0 — Performance crítico
**Estimación:** 1 hora

**Problema:** Cada llamada a `get_embedding()` spawnea un subprocess (~1,087ms). Server mode medido a 15ms (72x más rápido).

**Especificación:**

```python
class LlamaServerBackend(EmbeddingBackend):
    """Embedding via llama-server HTTP daemon (persistent).
    
    72x más rápido que subprocess (15ms vs 1,087ms).
    Requiere llama-server corriendo como daemon.
    """
    
    def __init__(self):
        self._url = os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8080")
        self._available: Optional[bool] = None
    
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._url}/health", method="GET")
            urllib.request.urlopen(req, timeout=2)
            self._available = True
        except Exception:
            self._available = False
        return self._available
    
    def embed(self, text: str) -> list[float]:
        import urllib.request, json
        
        req = urllib.request.Request(
            f"{self._url}/embedding",
            data=json.dumps({"content": text}).encode(),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            # Formato: [{"index": 0, "embedding": [[float, ...]]}]
            return data[0]["embedding"]
```

**Actualizar el registry:**
```python
_BACKENDS = {
    "llama_cpp": LlamaCppBackend,
    "llama_server": LlamaServerBackend,  # NUEVO
    "http": HttpBackend,
    "noop": NoOpBackend,
}
```

**Fallback automático:**
```python
def _get_default_backend() -> EmbeddingBackend:
    global _default_backend
    if _default_backend is None:
        # Intentar server primero, fallback a subprocess
        server = LlamaServerBackend()
        if server.is_available():
            _default_backend = server
        else:
            _default_backend = LlamaCppBackend()
    return _default_backend
```

### TASK-2.2: Script de inicio del embedding server

**Archivo:** `MCP-servers/scripts/start-embedding-server.sh`
**Prioridad:** P0
**Estimación:** 30 min

```bash
#!/bin/bash
# Start embedding server as persistent daemon
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR/../engine"
MODEL_DIR="$SCRIPT_DIR/../models"
PORT="${LLAMA_SERVER_PORT:-8080}"

MODEL="$MODEL_DIR/bge-m3-Q4_K_M.gguf"
if [ ! -f "$MODEL" ]; then
    echo "ERROR: Model not found: $MODEL" >&2
    exit 1
fi

# Check if already running
if curl -s "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
    echo "Embedding server already running on port $PORT"
    exit 0
fi

echo "Starting embedding server on port $PORT..."
"$ENGINE_DIR/bin/llama-server" \
    -m "$MODEL" \
    --embedding \
    --port "$PORT" \
    --host 127.0.0.1 \
    -c 512 \
    -t 4 \
    --mlock \
    2>/dev/null &

# Wait for ready
for i in $(seq 1 30); do
    if curl -s "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
        echo "Embedding server ready (PID $!)"
        exit 0
    fi
    sleep 0.5
done

echo "ERROR: Embedding server failed to start" >&2
exit 1
```

### TASK-2.3: Integrar en start-gateway.sh

**Archivo:** `MCP-servers/start-gateway.sh`
**Prioridad:** P0
**Estimación:** 15 min

**Añadir antes de lanzar 1mcp:**
```bash
# Start embedding server (daemon, 72x faster than subprocess)
"$MEMORY_SERVER_DIR/scripts/start-embedding-server.sh"
export EMBEDDING_BACKEND=llama_server
```

### TASK-2.4: Embedding cache LRU

**Archivo:** `MCP-servers/shared/embedding.py`
**Prioridad:** P1
**Estimación:** 15 min

```python
from functools import lru_cache

# Cache transparente, mismo texto = mismo vector sin llamada
_cached_embed = lru_cache(maxsize=512)(_get_default_backend().embed)

def get_embedding(text: str) -> list[float]:
    return _cached_embed(text)
```

**Nota:** `lru_cache` funciona con strings hasheables. Para invalidar por tamaño, el maxsize=512 cubre ~512 textos únicos frecuentes.

---

## FASE 3: HABILITAR CONSOLIDACIÓN

### TASK-3.1: Verificar LLM de consolidación

**Archivo:** N/A (verificación)
**Prioridad:** P1
**Estimación:** 15 min

**Test:**
```bash
cd ~/MCP-servers/MCP-agent-memory
.venv/bin/python3 -c "
from shared.llm import get_llm
llm = get_llm()
print(f'LLM disponible: {llm.is_available()}')
result = llm.ask('Resume en 1 frase: El usuario prefiere español. Usa pnpm. Hubo error con npm.', max_tokens=100)
print(f'Resultado: {result}')
"
```

**Si falla:** Verificar Ollama corriendo y modelo qwen2.5:7b disponible.

### TASK-3.2: Ajustar umbrales para testing

**Archivo:** `MCP-servers/servers/autodream/server/main.py`
**Prioridad:** P1
**Estimación:** 15 min

**Cambios configurables via env:**
```python
# En producción:
PROMOTE_L1_TO_L2 = int(os.getenv("DREAM_PROMOTE_L1", "10"))     # turns
PROMOTE_L2_TO_L3 = int(os.getenv("DREAM_PROMOTE_L2", "3600"))    # seconds
PROMOTE_L3_TO_L4 = int(os.getenv("DREAM_PROMOTE_L3", "86400"))   # seconds

# Para testing:
# DREAM_PROMOTE_L1=3 DREAM_PROMOTE_L2=60 DREAM_PROMOTE_L3=300
```

**No hardcodear valores más bajos.** Usar env vars para que producción mantenga los valores conservadores.

### TASK-3.3: Test de ciclo completo de consolidación

**Estimación:** 30 min

```bash
# 1. Almacenar 5+ memorias
# 2. Ejecutar heartbeat con turn_count=3+
# 3. Force consolidate
# 4. Verificar L2 creado
# 5. Verificar L3 con resumen
```

---

## FASE 4: UNIFICACIÓN DE COLECCIONES

### TASK-4.1: Diseñar schema unificado

**Prioridad:** P2
**Estimación:** 1 hora

**Colección única `memory`:**
```json
{
    "vectors": {"size": 1024, "distance": "Cosine"},
    "sparse_vectors": {"text": {"index": {"type": "bm25"}}}
}
```

**Payload unificado:**
```json
{
    "layer": 1,
    "type": "fact",
    "source": "automem",
    "scope_type": "personal",
    "scope_id": "ruben",
    "content": "...",
    "importance": 0.8,
    "tags": ["idioma"],
    "confidence": 0.7,
    "created_at": "2026-04-16T...",
    "updated_at": "2026-04-16T...",
    "user_id": "ruben",
    "thread_id": null,
    "promoted_to": null,
    "source_event_ids": []
}
```

**Discriminación por `source`:**
- `automem` → memorias directas del agente
- `mem0` → hechos/preferencias de usuario
- `conversation` → hilos de conversación
- `engram` → decisiones del vault
- `autodream` → memorias consolidadas

### TASK-4.2: Script de migración

**Archivo:** `MCP-servers/scripts/migrate-unify-collections.py`
**Prioridad:** P2
**Estimación:** 2 horas

1. Crear colección `memory` con schema unificado
2. Migrar puntos de `automem`, `mem0_memories`, `conversations`
3. Añadir campo `source` a cada punto migrado
4. Verificar integridad (count antes = count después)
5. Renombrar colecciones viejas como backup (`automem_backup`)

### TASK-4.3: Actualizar servidores

**Archivos:** Todos los servidores que usan Qdrant
**Prioridad:** P2
**Estimación:** 2 horas

Actualizar cada servidor para escribir a colección `memory` en vez de su colección propia.

### TASK-4.4: Actualizar retrieval router

**Archivo:** `MCP-servers/shared/retrieval/__init__.py`
**Prioridad:** P2
**Estimación:** 1 hora

Simplificar: una sola colección, filtrar por `source` y `layer` en el payload en vez de federar múltiples colecciones.

---

## FASE 5: INTEGRACIÓN CON PI

### TASK-5.1: Actualizar extensión mcp-memory

**Archivo:** `~/.pi/agent/extensions/mcp-memory/index.ts`
**Prioridad:** P2
**Estimación:** 1 hora

- Corregir nombres de parámetros (messages → messages_json)
- Añadir manejo de errores del gateway
- Añadir retry logic

### TASK-5.2: Enrutar self-improvement → memory server

**Archivo:** `~/.pi/agent/AGENTS.md`
**Prioridad:** P2
**Estimación:** 30 min

Ya documentado en AGENTS.md. Requiere que Fase 1 esté completa para funcionar.

### TASK-5.3: Tests end-to-end

**Prioridad:** P2
**Estimación:** 1 hora

```
1. Store → verificar en Qdrant
2. Recall → verificar que encuentra lo almacenado
3. Consolidate → verificar L1→L2→L3
4. Recall después de consolidar → verificar que encuentra L3
5. Decision → verificar en vault
6. Conversation → verificar búsqueda
```

---

## MÉTRICAS OBJETIVO

| Métrica | Actual | Post-Fase 1+2 | Post-Fase 4 |
|---------|--------|---------------|-------------|
| Latencia store | 1,460ms | **<50ms** | <50ms |
| Latencia recall | 1,600ms (❌ roto) | **<100ms** (✅) | <80ms |
| Latencia embedding | 1,087ms | **~15ms** | ~15ms |
| Búsqueda semántica | ❌ Rota | ✅ Funcional | ✅ Unificada |
| Consolidación | 0 ejecuciones | Automática | Automática |
| Colecciones | 4 (1 útil) | 4 (funcionales) | **1 unificada** |
| Calidad embedding (bge-m3) | 0.72/0.31 | Mantener | Mantener |

---

## DEPENDENCIAS

```
FASE 1 (Bugs) ← sin dependencias, empezar aquí
    ↓
FASE 2 (Embedding server) ← independiente de Fase 1 pero se beneficia
    ↓
FASE 3 (Consolidación) ← requiere Fase 1 para que haya datos que consolidar
    ↓
FASE 4 (Unificación) ← requiere Fase 1+2+3 estables
    ↓
FASE 5 (Integración pi) ← requiere todo lo anterior
```

---

*Especificación generada por pi — 16/04/2026*
*Runtime: `/Users/ruben/MCP-servers/MCP-agent-memory/`*
*Proyecto: `/Users/ruben/Code/PROJECT-MCP-agent-memory/`*
