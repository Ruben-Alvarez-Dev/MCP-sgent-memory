# Structure Map — MCP-agent-memory v2.1.0

## Top-level tree (relevant only)
```
src/
├── unified/server/main.py          (229)  Gateway unificado + health_check
├── L0_capture/server/main.py       (184)  Ingest automatizada + memorizar
├── L0_to_L4_consolidation/         (425)  Consolidación entre capas (ISO-06 NO-OPs)
├── L2_conversations/server/main.py (225)  Hilos de conversación
├── L3_decisions/server/main.py     (197)  Vault decisiones + markdown
├── L3_facts/server/main.py         ( 77)  Hechos semánticos (muy pequeño)
├── L5_routing/server/main.py       (202)  Enrutamiento + contexto
├── Lx_reasoning/server/main.py     (193)  Razonamiento secuencial + planes
└── shared/
    ├── memory_db.py        (654)  Motor SQLite engine-level
    ├── embedding.py        (700)  Backend embeddings (BGE-M3)
    ├── sanitize.py         (729)  Sanitización inputs
    ├── retrieval/__init__.py (494) Router retrieval
    ├── retrieval/code_map.py (664) Code map generation
    ├── retrieval/pruner.py   (135) Token pruning
    ├── retrieval/repo_map.py (182) Repo map
    ├── identity.py         (183) Auth tokens + fail-closed boot
    ├── scope.py            (185) Aislamiento tenants
    ├── compliance/__init__.py(273) Verificación reglas
    ├── vault_manager/__init__.py(826) Vault Obsidian
    ├── api_server.py       (381) Sidecar HTTP API
    ├── conversation_db.py  (371) SQLite + FTS5 hilos
    ├── timeline.py         (277) Timeline backbone
    ├── observe.py          (443) Instrumentación
    ├── models/__init__.py  (290) Data contracts
    ├── config.py           (143) Config centralizado
    └── env_loader.py       (192) Carga de variables
scripts/
├── run_eval.py             (265) Eval-40 runner
├── register_agent.py
└── migrate_to_memory_db.py
install/                    (bootstrap, services, verify)
tests/                      (321 passed / 6 skipped)
config/mcp.json             (MCP server config)
data/memory.db              (SQLite, 0 puntos — DB vacía)
```

## Entrypoints
| Module | Entrypoint | Tools count | Purpose |
|--------|-----------|-------------|---------|
| unified | `src/unified/server/main.py:229` | 54 (total) | Single-entry gateway via FastMCP stdio |
| L0_capture | `src/L0_capture/server/main.py:184` | 4 | ingest_event, memorize, heartbeat, status |
| L0_to_L4 | `src/L0_to_L4_consolidation/server/main.py:425` | 9 | consolidate, approve_promotion, dream, heartbeat... |
| L2_conv | `src/L2_conversations/server/main.py:225` | 5 | save_conversation, get_conversation, search, list, status |
| L3_decisions | `src/L3_decisions/server/main.py:197` | 13 | save/get/list/delete decision, vault operations |
| L3_facts | `src/L3_facts/server/main.py:77` | ~5 | facts CRUD (small module) |
| L5_routing | `src/L5_routing/server/main.py:202` | 6 | request_context, push_reminder, check, dismiss, detect, status |
| Lx_reasoning | `src/Lx_reasoning/server/main.py:193` | 9 | sequential_thinking, create_plan, reflect, propose_change_set |

## Dependencies (pyproject.toml)
```
Core: mcp>=1.27, pydantic>=2.0, python-dotenv>=1.0, pyyaml>=6.0
Dev: pytest>=8.0, pytest-asyncio>=0.23, ruff>=0.4
Runtime (implicit): pygments (for code_map/diff_sandbox)
External (not in pyproject): llama-server (port 8091) or llama.cpp binary
```

## Total lines: ~7,400 Python
