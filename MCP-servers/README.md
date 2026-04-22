# MCP-servers — Source Code

This directory contains all server source code, the unified entry point, shared modules, and the installer.

## Structure

```
MCP-servers/
├── automem/               ← Memory ingestion daemon
├── autodream/             ← Consolidation & dream cycle
├── vk-cache/              ← Vector retrieval & context assembly
├── conversation-store/    ← Thread persistence
├── mem0/                  ← Semantic memory (Mem0-compatible)
├── engram/                ← Decisions, vault, model packs
├── sequential-thinking/   ← Reasoning chains & planning
├── unified/               ← Single entry point (51 tools)
│   └── server/main.py
├── shared/                ← Common modules
│   ├── embedding.py       ← Embedding backends (llama_server, llama_cpp, noop)
│   ├── env_loader.py      ← Environment configuration
│   ├── models/            ← Pydantic data models
│   ├── llm/               ← LLM backends (ollama, lmstudio, llama_cpp)
│   ├── retrieval/         ← Code maps, repo indexing
│   ├── compliance/        ← Policy enforcement
│   ├── vault_manager/     ← Obsidian vault operations
│   ├── sanitize.py        ← Input validation
│   ├── observe.py         ← Observability hooks
│   ├── health.py          ← Unified health check CLI
│   └── workspace/         ← Git worktree management
├── config/
│   └── .env.example       ← Environment template
├── scripts/               ← Startup scripts
├── tests/                 ← Module-level tests
├── install.sh             ← Unified installer
└── build-package.sh       ← Package builder
```

## Quick Start

```bash
bash install.sh
```

See [../README.md](../README.md) for full documentation.
