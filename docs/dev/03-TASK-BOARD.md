# TASK BOARD — MCP Memory Server V3.1

> Estado: Pendiente de inicio
> Fecha creación: 16/04/2026

## FASE 1: BUGS CRÍTICOS (~1-2h)

| ID | Task | Archivo | Estado | Prioridad | Tiempo est. |
|----|------|---------|--------|-----------|-------------|
| TASK-1.1 | Fix classify_intent() entities vacías | `shared/llm/config.py` | ✅ Completado | P0 | 30min |
| TASK-1.2 | Fix _retrieve_qdrant() fallback query | `shared/retrieval/__init__.py` | ✅ Completado | P0 | 15min |
| TASK-1.3 | Fix conversation-store param name | `servers/conversation-store/server/main.py` | ✅ Completado | P1 | 15min |
| TASK-1.4 | Investigar mem0-bridge puntos vacíos | `servers/mem0-bridge/server/main.py` | ✅ Completado | P1 | 30min |

## FASE 2: EMBEDDING SERVER MODE (~2-3h)

| ID | Task | Archivo | Estado | Prioridad | Tiempo est. |
|----|------|---------|--------|-----------|-------------|
| TASK-2.1 | Implementar LlamaServerBackend | `shared/embedding.py` | ✅ Completado | P0 | 1h |
| TASK-2.2 | Script start-embedding-server.sh | `scripts/start-embedding-server.sh` | ✅ Completado | P0 | 30min |
| TASK-2.3 | Integrar en start-gateway.sh | `start-gateway.sh` | ✅ Completado | P0 | 15min |
| TASK-2.4 | Embedding cache LRU | `shared/embedding.py` | ✅ Completado | P1 | 15min |
| TASK-2.5 | Tests de latencia post-server | `tests/` | ✅ Completado | P1 | 30min |

## FASE 3: HABILITAR CONSOLIDACIÓN (~1-2h)

| ID | Task | Archivo | Estado | Prioridad | Tiempo est. |
|----|------|---------|--------|-----------|-------------|
| TASK-3.1 | Verificar LLM llama.cpp consolidación | — | ⬜ Pendiente | P1 | 15min |
| TASK-3.2 | Ajustar umbrales via env vars | `servers/autodream/server/main.py` | ⬜ Pendiente | P1 | 15min |
| TASK-3.3 | Test ciclo completo consolidación | `tests/` | ⬜ Pendiente | P1 | 30min |

## FASE 4: UNIFICACIÓN DE COLECCIONES (~3-4h)

| ID | Task | Archivo | Estado | Prioridad | Tiempo est. |
|----|------|---------|--------|-----------|-------------|
| TASK-4.1 | Diseñar schema unificado | `docs/dev/` | ⬜ Pendiente | P2 | 1h |
| TASK-4.2 | Script migración | `scripts/migrate-unify.py` | ⬜ Pendiente | P2 | 2h |
| TASK-4.3 | Actualizar servidores | Todos los servers | ⬜ Pendiente | P2 | 2h |
| TASK-4.4 | Actualizar retrieval router | `shared/retrieval/__init__.py` | ⬜ Pendiente | P2 | 1h |
| TASK-4.5 | Tests regresión | `tests/` | ⬜ Pendiente | P2 | 1h |

## FASE 5: INTEGRACIÓN CON PI (~2-3h)

| ID | Task | Archivo | Estado | Prioridad | Tiempo est. |
|----|------|---------|--------|-----------|-------------|
| TASK-5.1 | Actualizar extensión mcp-memory | `~/.pi/agent/extensions/mcp-memory/` | ⬜ Pendiente | P2 | 1h |
| TASK-5.2 | Enrutar self-improvement → memory server | `~/.pi/agent/AGENTS.md` | ⬜ Pendiente | P2 | 30min |
| TASK-5.3 | Tests end-to-end | `tests/` | ⬜ Pendiente | P2 | 1h |
| TASK-5.4 | Benchmark final + documentación | `docs/dev/` | ⬜ Pendiente | P2 | 30min |

## Leyenda

- ⬜ Pendiente
- 🔄 En progreso
- ✅ Completado
- ❌ Bloqueado
- ⏭️ Skipped

## Progreso total

- Fase 1: 4/4 tasks (100%)
- Fase 2: 5/5 tasks (100%)
- Fase 3: 0/3 tasks (0%)
- Fase 4: 0/5 tasks (0%)
- Fase 5: 0/4 tasks (0%)
- **Total: 0/21 tasks (0%)**
