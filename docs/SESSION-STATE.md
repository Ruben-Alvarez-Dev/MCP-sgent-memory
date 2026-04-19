# MCP Memory Server — Estado y Plan (2025-04-19)

## Rutas
- **Producción**: `/Users/ruben/MCP-servers/MCP-memory-server/`
- **Desarrollo**: `/Users/ruben/Code/PROJECT-MCP-memory-server/`

## Estado del Sistema
| Componente | Estado | Detalle |
|---|---|---|
| Servers | 7/7 healthy | automem, engram, mem0, vk-cache, autodream, conversation-store, sequential-thinking |
| Tools | 51 | Gateway 1mcp puerto 3050 |
| Qdrant | 4 collections | automem=250pts, conversations=17pts, mem0_memories=23pts, vkcache=0pts |
| llama-server | Running | Puerto 8081, BGE-M3 1024 dims, 30ms/embedding |
| Embedding params | `-np 3 -ub 8192` | 3 slots paralelos, physical batch 8192 |
| launchd | llama-server only | Gateway y Qdrant NO tienen launchd |
| Commit último | sanitize v2 | Fix supplementary planes + soft hyphen |

## Tests
| Suite | Resultado | Detalle |
|---|---|---|
| E2E bench | **62/62** | `bench/e2e_bench.py` |
| Flow verification | **57/59** | `bench/flow_verification.py` |
| R4 (falla) | mem0 search timing | Dato nuevo no se encuentra por RUN_ID |
| R13 (falla) | consolidate timeout | 38s > curl timeout de 30s |

## Datos Acumulados
- 86 events en JSONL
- 85 thinking sessions
- 5 decisions en engram
- 11 reminders activos
- 13 heartbeats de agentes
- 17 staging changes
- 0 bytes de logs (vacío)

## Problemas Conocidos
1. **Gateway sin auto-restart** — 1mcp no tiene launchd, si se reinicia Mac no arranca
2. **Qdrant sin auto-restart** — No tiene launchd
3. **39 paths absolutos en mcp.json** — No portable entre máquinas
4. **Datos crecen sin cleanup** — No hay rotation policy
5. **observe.py sin uso real** — Existe pero no hay alerting
6. **Sin backup de Qdrant** — Si corrompe, se pierde todo

## Plan Siguiente (priorizado por impacto)

### Sprint 5: Resiliencia
- [ ] launchd plist para 1mcp gateway
- [ ] launchd plist para Qdrant
- [ ] Circuit breaker en shared/embedding.py (retry si llama-server cae)
- [ ] Health check endpoint unificado
- [ ] Auto-recovery script (watchdog)

### Sprint 6: Config Portable
- [ ] Template mcp.json con variables de entorno
- [ ] Script `configure.sh` que genera mcp.json desde template
- [ ] Eliminar los 39 paths absolutos
- [ ] Validar config al arrancar

### Sprint 7: Data Lifecycle
- [ ] Rotation policy para JSONL events
- [ ] Cleanup de thinking sessions antiguas
- [ ] Qdrant point TTL (configurable)
- [ ] Backup automático de Qdrant snapshots
- [ ] prune_stale_memories en retrieval/pruner.py

### Sprint 8: Fix Flows
- [ ] R4: mem0 search — usar wait+retry o buscar por contenido parcial
- [ ] R13: consolidate — subir timeout o hacer async con callback

### Sprint 9: Monitoring Real
- [ ] Dashboard HTTP simple (puerto 3051)
- [ ] Métricas: requests/min, latencia p50/p95, errores
- [ ] Alertas: servicio caído, disco lleno, Qdrant degradado

## Key Decisions
- **Self-contained**: todo en `$MEMORY_SERVER_DIR`
- **Embeddings**: llama.cpp local (`bin/engine/`), NO Ollama/LM Studio
- **Code Maps**: Pygments (no tree-sitter, too heavy)
- **Hybrid search**: `/points/search` (NOT `/points/query` — scores=0.0 en Qdrant v1.13)
- **Sanitización**: OWASP + Unicode UTS #36/39, codepoint sets explícitos
- **Model Packs**: YAML files en `data/memory/engram/model-packs/`

## Archivos Clave
| Archivo | Propósito |
|---|---|
| `/Users/ruben/.config/1mcp/mcp.json` | Config gateway (7 servers) |
| `~/Library/LaunchAgents/com.memory-server.llama-embedding.plist` | launchd auto-start |
| `bin/engine/bin/llama-server` | HTTP embedding daemon |
| `bin/models/bge-m3-Q4_K_M.gguf` | Modelo embedding (417MB) |
| `src/shared/sanitize.py` | Capa sanitización universal |
| `src/shared/retrieval/__init__.py` | Router de búsqueda híbrida |
| `src/shared/embedding.py` | `async_embed()` centralizado |
| `bench/e2e_bench.py` | 62 tests E2E |
| `bench/flow_verification.py` | 59 tests de flujo |
| `docs/FUSION-DESIGN-v2.md` | Arquitectura (23KB) |
| `docs/FUSION-SPEC-v3.md` | 12 specs con AC (29KB) |
