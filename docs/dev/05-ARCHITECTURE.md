# ARQUITECTURA — MCP Memory Server V3

> Documento de referencia para entender la arquitectura del sistema.

## Vista General

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENTES (pi, Claude Code, etc.)             │
│                        ↓ HTTP/SSE                               │
├─────────────────────────────────────────────────────────────────┤
│                    1MCP GATEWAY (:3050)                         │
│                  Proxy HTTP → stdio/stdio                       │
│                                                                  │
│  Enruta llamadas a servidores MCP individuales                  │
│  Herramientas visibles: {server}_1mcp_{tool}                    │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│ automem  │autodream │ vk-cache │ mem0     │ engram   │ seq-think│
│          │          │          │ bridge   │ bridge   │          │
│ L0/L1    │ L2-L4    │ L5       │ L1       │ L3       │ Reasoning│
│ Ingesta  │Consolida.│Recuperac.│Hechos    │Decisiones│ Planning │
│          │          │ Intelig. │ Prefer.  │  Vault   │          │
├──────────┴──────────┴──────────┴──────────┴──────────┴──────────┤
│                      SHARED MODULES                              │
│  embedding.py │ llm/ │ models/ │ retrieval/ │ compliance/       │
├─────────────────────────────────────────────────────────────────┤
│                      BACKENDS                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ Qdrant   │  │ Ollama   │  │ llama.cpp│                      │
│  │ :6333    │  │ :11434   │  │ engine/  │                      │
│  │ Vectores │  │ qwen2.5  │  │ bge-m3   │                      │
│  │ + BM25   │  │ qwen3.5  │  │ 1024d    │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
├─────────────────────────────────────────────────────────────────┤
│                    FILESYSTEM                                    │
│  ~/.memory/          vault/           MCP-servers/              │
│  ├── raw_events.jsonl├── Decisions/   ├── models/              │
│  ├── heartbeats/     ├── Patterns/    ├── engine/              │
│  ├── engram/         ├── Notes/       └── scripts/             │
│  ├── dream/          └── Inbox/                                 │
│  └── staging_buffer/                                            │
└─────────────────────────────────────────────────────────────────┘
```

## Capas de Memoria

```
L0 RAW          Eventos crudos append-only (JSONL)
       ↓ ingest
L1 WORKING      Hechos, pasos, preferencias (automem → Qdrant)
       ↓ promote (cada 10 turns)
L2 EPISODIC     Episodios agrupados por scope
       ↓ consolidate (cada 1h, usa Ollama)
L3 SEMANTIC     Decisiones, entidades, patrones (engram + vault)
       ↓ consolidate (cada 24h, usa Ollama)
L4 CONSOLIDATED Narrativas, resúmenes, dreams
       ↓ dream (semanal, usa Ollama)
L4+ DREAM       Detección de patrones cross-layer
```

## Flujo de Datos Típico

```
Usuario pregunta algo
       ↓
vk-cache: request_context(query)
       ↓
classify_intent(query) → QueryIntent(entities=[...])
       ↓
retrieve_parallel() → busca en Qdrant (dense + BM25)
       ↓
rank_and_fuse() → combina, deduplica, puntúa
       ↓
pack_context() → ensambla dentro de token budget
       ↓
ContextPack → enriquece la respuesta del agente
```

## Conexiones entre Componentes

| Desde | Hacia | Protocolo | Puerto/Path |
|-------|-------|-----------|-------------|
| Clientes | 1MCP Gateway | HTTP/SSE | :3050/mcp |
| 1MCP | Servidores MCP | stdio | subprocess |
| Servidores MCP | Qdrant | HTTP | :6333 |
| Servidores MCP | Ollama | HTTP | :11434 |
| automem | llama.cpp | subprocess | engine/bin/llama-embedding |
| vk-cache | llama.cpp | subprocess | engine/bin/llama-embedding |
| engram-bridge | Filesystem | directo | ~/.memory/engram/, vault/ |

## Colecciones Qdrant (actual)

| Nombre | Dim | Sparse | Propósito | Puntos |
|--------|-----|--------|-----------|--------|
| automem | 1024 | BM25 | Memorias L0-L4 | 11 |
| mem0_memories | 1024 | BM25 | Hechos de usuario | 0 |
| conversations | 1024 | BM25 | Conversaciones | 0 |
| vkcache | — | none | Context packs | 0 |

## Variables de Entorno Clave

| Variable | Default | Uso |
|----------|---------|-----|
| `QDRANT_URL` | http://127.0.0.1:6333 | URL de Qdrant |
| `EMBEDDING_DIM` | 1024 | Dimensiones de embedding |
| `EMBEDDING_BACKEND` | llama_cpp | Backend: llama_cpp / http / noop |
| `LLM_BACKEND` | ollama | LLM para consolidación |
| `LLM_MODEL` | qwen2.5:7b | Modelo LLM principal |
| `SMALL_LLM_MODEL` | qwen3.5:2b | Micro-LLM para ranking |
| `DREAM_PROMOTE_L1` | 10 | Turns para L1→L2 |
| `DREAM_PROMOTE_L2` | 3600 | Segs para L2→L3 |
| `DREAM_PROMOTE_L3` | 86400 | Segs para L3→L4 |

## Directorios

| Path | Contenido |
|------|-----------|
| `MCP-servers/shared/` | Módulos compartidos (embedding, llm, models, retrieval) |
| `MCP-servers/servers/` | Servidores MCP individuales |
| `MCP-servers/engine/` | Binarios llama.cpp |
| `MCP-servers/models/` | Modelos .gguf |
| `MCP-servers/vault/` | Vault de Obsidian |
| `MCP-servers/config/` | Configuración 1mcp |
| `MCP-servers/scripts/` | Scripts de utilidad |
| `~/.memory/` | Datos de runtime (events, heartbeats, dream state) |

---

*Documento generado por pi — 16/04/2026*
