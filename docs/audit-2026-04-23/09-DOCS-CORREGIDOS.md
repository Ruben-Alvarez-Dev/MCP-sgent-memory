# MCP-agent-memory — Documentación Corregida

## Tool Count
**50 tools** (no 51) registradas en el unified server.

## Servicios del Sistema

### LaunchAgents (`com.agent-memory.*`)

| Servicio | plist | Intervalo | Rol |
|---|---|---|---|
| Qdrant | com.agent-memory.qdrant | OnDemand | Vector DB (puerto 6333) |
| llama-server | com.agent-memory.llama-embedding | KeepAlive | Embeddings (puerto 8081, compilado Metal) |
| Gateway | com.agent-memory.gateway | KeepAlive | 1MCP gateway (puerto 3051) |
| Watchdog | com.agent-memory.watchdog | Every 5min | Auto-recovery de servicios |
| Lifecycle | com.agent-memory.lifecycle | Weekly Sun 3am | Cleanup, backup, purge |

### Comandos útiles
```bash
# Ver estado de servicios
launchctl print gui/$(id -u)/com.agent-memory.qdrant

# Ver logs
tail -f ~/.memory/gateway.log
tail -f ~/.memory/qdrant.log
tail -f ~/.memory/server.log          # ← nuevo, logging centralizado

# Health check
PYTHONPATH=src .venv/bin/python3 -c "
from shared.health import run_health_check
import asyncio; asyncio.run(run_health_check())
"

# Lifecycle (dry run)
./scripts/lifecycle.sh --dry-run

# Regenerar mcp.json desde .env
./scripts/generate-mcp-config.sh
```

## Dream Cycle

El dream cycle NO es automático. Es **triggered**:

| Tool | Trigger | Efecto |
|---|---|---|
| `heartbeat()` | Cada turno del agente | Actualiza turn_count |
| `autodream_heartbeat()` | Cada turno | Si threshold alcanzado → promote L1→L2 |
| `consolidate()` | Manual o programado | Promote L2→L3 (usa LLM) |
| `dream()` | Manual | Promote L3→L4 (usa LLM) |

### Flujo de consolidación
```
L0 (raw events) → L1 (working) → L2 (episodic) → L3 (semantic) → L4 (consolidated)
     ingest          heartbeat       consolidate        dream           manual
                  (10 turns)       (1h threshold)    (24h threshold)  (7d threshold)
```

## Troubleshooting

| Problema | Verificar | Fix |
|---|---|---|
| "Collection not found" | Gateway arrancó antes que Qdrant | Reiniciar gateway: `launchctl kickstart ...` |
| "Embedding timeout" | llama-server vivo: `curl localhost:8081/health` | Reiniciar: `launchctl kickstart .../llama-embedding` |
| "Empty search results" | Colección tiene puntos: `curl localhost:6333/collections/automem` | Verificar que dim=1024 |
| "Qdrant connection refused" | Qdrant vivo: `curl localhost:6333/healthz` | `launchctl kickstart .../qdrant` |
| "MCP server not responding" | Pi puede conectar al MCP | Reiniciar Pi, verificar mcp.json |

## Arquitectura de Datos

### Capas de memoria
| Layer | Nombre | Almacenamiento | TTL |
|---|---|---|---|
| L0 | Raw Events | `data/raw_events.jsonl` | 90 días |
| L1 | Working | Qdrant `automem` | 30 días |
| L2 | Episodic | Qdrant `automem` | 180 días |
| L3 | Semantic | Qdrant `automem` + Engram files | ∞ |
| L4 | Consolidated | Qdrant `automem` + Engram files | ∞ |

### Embedding pipeline
- **Texto completo** → almacenado en payload
- **Primeros 2000 chars** → enviado a llama-server para embedding
- **Vector 1024d** → almacenado en Qdrant + cache SQLite
- **Cache**: LRU en memoria (512 entries) + SQLite persistente (~/.memory/embedding_cache.db)

### Políticas de retención
- lifecycle.sh rota JSONL a 10K líneas
- lifecycle.sh purga L0/L1 stale de Qdrant (nunca toca L3/L4)
- Backup semanal de Qdrant (guarda últimos 3 snapshots)
