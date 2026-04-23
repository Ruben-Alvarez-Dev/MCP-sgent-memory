# Grupo F — Observabilidad

## Especificaciones

### SPEC-F1: Conectar @observe a todas las tools

**ID auditoría**: OBS-H1
**Severidad**: HIGH
**Módulo**: todos los server/main.py

**Problema**: `shared/observe.py` tiene decorator `@observe` con JSONL logging y metrics. 0 módulos lo usan.

**Spec de fix**:
```python
# En cada módulo server/main.py:
from shared.observe import observe

@observe
async def memorize(...):
    ...

@observe
async def recall(...):
    ...
```

**Criterio de aceptación**:
- [ ] Todas las tools públicas tienen @observe
- [ ] Cada call se logea a `data/tool_calls.jsonl`
- [ ] Metrics disponibles via `observe.metrics.get()`
- [ ] Dashboard HTTP arrancable en puerto 8080

---

### SPEC-F2: Structured logging mínimo

**ID auditoría**: OBS-H2
**Severidad**: HIGH
**Módulos**: todos

**Problema**: Solo 12 calls a logging en 8619 LOC. Las tools son caja negra.

**Spec de fix**:
```python
# En cada server/main.py:
import logging
logger = logging.getLogger(f"agent-memory.{module_name}")

# Al inicio de cada tool:
logger.info(f"tool_name(params)")

# En errores:
logger.error(f"tool_name failed: {e}", exc_info=True)
```

Configurar logging centralizado:
```python
# src/shared/logging_config.py
import logging

def setup_logging(level="INFO"):
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, "server.log")),
            logging.StreamHandler()
        ]
    )
```

**Criterio de aceptación**:
- [ ] Cada tool logea entry y exit
- [ ] Errores logean con exc_info=True
- [ ] Logs van a `~/.memory/server.log`
- [ ] Log rotation (10MB, 3 backups)

---

### SPEC-F3: Health check como endpoint HTTP

**ID auditoría**: OBS-H3
**Severidad**: MEDIUM
**Módulo**: `src/shared/health.py`

**Problema**: health.py solo funciona como CLI. No hay forma de consultar estado via HTTP.

**Spec de fix**: Añadir endpoint al gateway o como servidor independiente:

```python
# Opción A: Añadir al unified server
@server.tool("health_check")
async def health_check() -> dict:
    from shared.health import run_health_check
    return await run_health_check()

# Opción B: Servidor HTTP standalone en puerto 8081
# (para monitoring externo, no MCP)
```

**Criterio de aceptación**:
- [ ] `GET http://localhost:8081/health` retorna JSON con estado de todos los servicios
- [ ] Incluye: Qdrant, llama-server, Ollama, disk space, collection sizes
- [ ] Return code 200 si todo OK, 503 si algo falla

---

### SPEC-F4: Correlation IDs propagados

**ID auditoría**: OBS-H4
**Severidad**: LOW
**Módulo**: todos

**Problema**: ContextPack tiene request_id pero no se usa para correlacionar logs.

**Spec de fix**:
```python
# En unified server, generar correlation_id al inicio de cada tool call:
import contextvars
correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id")

# Propagar a logging:
class CorrelationFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id.get("none")
        return True
```

**Criterio de aceptación**:
- [ ] Cada tool call tiene correlation_id único
- [ ] Logs incluyen correlation_id
- [ ] Se puede tracear una request end-to-end
