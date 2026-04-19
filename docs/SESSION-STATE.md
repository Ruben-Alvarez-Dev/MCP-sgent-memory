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
| Unit tests (pytest) | **22/22** (+2 skipped) | `tests/test_*.py` |
| System health | **31/31** | `tests/test_system_health.py` |
| E2E bench | **62/62** | `bench/e2e_bench.py` |
| Flow verification | **58/59** | `bench/flow_verification.py` |
| R4 (intermittent) | mem0 search timing | Nuevo dato no se encuentra por RUN_ID (race con Qdrant indexing) |

## Datos Acumulados
- 86 events en JSONL
- 85 thinking sessions
- 5 decisions en engram
- 11 reminders activos
- 13 heartbeats de agentes
- 17 staging changes
- 0 bytes de logs (vacío)

## Problemas Conocidos
1. ~~Gateway sin auto-restart~~ — ✅ **Sprint 5**: launchd plist activo
2. ~~Qdrant sin auto-restart~~ — ✅ **Sprint 5**: launchd plist activo
3. ~~39 paths absolutos en mcp.json~~ — ✅ **Sprint 6**: solo 28 (command+args+PYTHONPATH), data paths derivados por env_loader.py
4. ~~Datos crecen sin cleanup~~ — ✅ **Sprint 7**: lifecycle.sh semanal (JSONL rotation, sessions, staging, heartbeats, Qdrant backup)
5. **observe.py sin uso real** — Existe pero no hay alerting
6. ~~Sin backup de Qdrant~~ — ✅ **Sprint 7**: snapshots automáticos semanales

## Plan Siguiente (priorizado por impacto)

### Sprint 5: Resiliencia ✅ COMPLETADO
- [x] launchd plist para 1mcp gateway (`com.memory-server.gateway.plist`)
- [x] launchd plist para Qdrant (`com.memory-server.qdrant.plist`)
- [x] Circuit breaker en `shared/embedding.py` (3 failures → open, 30s recovery, fallback a subprocess)
- [x] Health check unificado `shared/health.py` (6 checks: qdrant, llama-server, gateway, embedding, disk, launchd)
- [x] Watchdog `scripts/watchdog.sh` + launchd cada 5 min (`com.memory-server.watchdog.plist`)
- [x] Eliminado plist viejo `com.memory.qdrant` (ruta obsoleta)
- [x] Tests E2E: 62/62 pasados

### Sprint 6: Config Portable ✅ COMPLETADO
- [x] `config/mcp.json.template` con placeholders `{{DIR}}`
- [x] `scripts/configure.sh` genera mcp.json + 5 launchd plists desde 1 variable
- [x] Eliminados 11 data paths redundantes (39→28) — `env_loader.py` los deriva
- [x] Portable: `configure.sh /new/path` en otra máquina
- [x] Tests E2E: 62/62 pasados con config reducida

### Sprint 7: Data Lifecycle ✅ COMPLETADO
- [x] `scripts/lifecycle.sh` — JSONL rotation (10K lines), thinking sessions (30d), staging (7d)
- [x] Heartbeats cleanup (7d), reminders dismissed (90d)
- [x] Qdrant backup automático (snapshots semanales, keep 3)
- [x] `com.memory-server.lifecycle.plist` (domingos 03:00)
- [x] `--status`, `--dry-run`, `--backup` modes

### Sprint 8: Fix Flows
- [ ] R4: mem0 search — usar wait+retry o buscar por contenido parcial
- [x] R13: consolidate — timeout catcheado graceful (completa en background)

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
| `src/shared/embedding.py` | `async_embed()` centralizado + **circuit breaker** |
| `src/shared/health.py` | **Health check unificado** (6 services) |
| `config/mcp.json.template` | **Template portable** ({{DIR}} placeholders) |
| `scripts/configure.sh` | **Genera config + plists** desde 1 variable |
| `scripts/lifecycle.sh` | **Data cleanup + Qdrant backup** semanal |
| `scripts/watchdog.sh` | **Auto-recovery** cada 5 min |
| `bench/e2e_bench.py` | 62 tests E2E |
| `bench/flow_verification.py` | 59 tests de flujo |
| `docs/FUSION-DESIGN-v2.md` | Arquitectura (23KB) |
| `docs/FUSION-SPEC-v3.md` | 12 specs con AC (29KB) |
