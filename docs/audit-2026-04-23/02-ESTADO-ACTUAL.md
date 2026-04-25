# Estado Actual del Sistema — 2026-04-23

## Servicios

| Servicio | LaunchAgent | PID | Binario | Estado |
|---|---|---|---|---|
| Qdrant | com.agent-memory.qdrant | activo | bin/qdrant | ✅ Corriendo |
| llama-server | com.agent-memory.llama-embedding | activo | engine/bin/llama-server (compilado Metal) | ✅ Corriendo |
| Gateway | com.agent-memory.gateway | activo | 1mcp serve (puerto 3051) | ✅ Corriendo |
| Watchdog | com.agent-memory.watchdog | cargado | scripts/watchdog.sh (cada 5min) | ✅ Activo |
| Lifecycle | com.agent-memory.lifecycle | cargado | scripts/lifecycle.sh (dom 3am) | ✅ Programado |
| llama.cpp | llama_cpp | 654 | /opt/homebrew (solo para LLM, no modelos) | ✅ Corriendo |

## Modelos

| Modelo | Rol | Tamaño | Medio | Estado |
|---|---|---|---|---|
| BGE-M3 (bge-m3-Q4_K_M.gguf) | Embeddings 1024d | 417MB | llama-server (engine/bin/) | ✅ |
| qwen2.5:7b | LLM principal (consolidación) | 4.7GB | llama.cpp | ✅ |
| qwen3.5:2b | Micro-LLM (ranking) | 2.7GB | llama.cpp | ✅ |

## Qdrant

| Colección | Puntos | Dim | Sparse |
|---|---|---|---|
| automem | 3 | 1024 | ✅ BM25 |
| conversations | 2 | 1024 | ✅ BM25 |
| mem0_memories | 2 | 1024 | ✅ BM25 |

## Archivos de datos

```
data/
├── raw_events.jsonl          (L0 - audit trail, 5 líneas)
├── memory/
│   ├── engram/general/       (1 decisión .md)
│   ├── dream/state.json      (estado dream cycle)
│   ├── thoughts/             (5 sesiones de pensamiento)
│   ├── heartbeats/           (1 heartbeat)
│   └── reminders/            (vacío)
├── staging_buffer/           (vacío)
├── aliases/                  (Qdrant interno)
└── collections/              (vacío - datos en storage/)
storage/                      (datos reales de Qdrant)
vault/                        (vacío)
```

## Bugs corregidos esta sesión

1. ✅ mem0 IDs no-UUID → str(uuid.uuid4())
2. ✅ conversation-store IDs no-UUID → str(uuid.uuid4())
3. ✅ llama-server apuntaba a Homebrew → plist actualizado a engine/bin/
4. ✅ Binarios compilados con dylibs rotas → recompilado estático
5. ✅ Qdrant config apuntaba a ./data → ./storage
6. ✅ LaunchAgents duplicados → consolidados bajo com.agent-memory.*
7. ✅ Scripts watchdog/lifecycle no copiados → descargados y configurados
8. ✅ Sin auto-inicialización → _initialize() en unified server
9. ✅ autodream sin ensure_collection → añadido
10. ✅ ulimit too low para Qdrant → start-qdrant.sh con ulimit -n 10240

## Bugs pendientes (ver 03-AUDITORIA-COMPLETA.md)

- 6 Critical
- 14 High
- 8 Medium
- 5 Low
