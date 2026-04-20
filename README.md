# MCP Memory Server

A hierarchical memory system for AI agents built on the Model Context Protocol (MCP). Provides persistent, multi-layered memory with semantic search, consolidation, and automatic dream-cycle processing.

## Architecture

```
L0 (Raw Events) → L1 (Working) → L2 (Short-term) → L3 (Semantic) → L4 (Consolidated)
```

### Core Servers

| Server | Port | Purpose |
|--------|------|---------|
| **automem** | - | Fast memory store/retrieve |
| **autodream** | - | Background consolidation & dream cycle |
| **conversation-store** | - | Thread/conversation persistence |
| **sequential-thinking** | - | Step-by-step reasoning chains |
| **vk-cache** | - | Vector knowledge cache & context retrieval |
| **mem0** | - | Mem0 compatibility layer |
| **engram** | - | Decision store & Obsidian vault |

### Hub Bridge (Python)

A management layer providing:
- **Catalog** - Artifact ingestion, enrichment, normalization
- **Search** - Full-text and semantic search
- **Security** - Provenance tracking, policy gates, validation
- **Host** - System inventory and config detection
- **Namespace** - Multi-tenant isolation
- **TUI** - Terminal management interface

## Requirements

- Python 3.10+
- [llama.cpp](https://github.com/ggerganov/llama.cpp) for local embeddings
- [Qdrant](https://qdrant.tech/) for vector storage

## Installation

```bash
pip install -r requirements.txt
python -m src
```

## Configuration

See `MCP-servers/config/` for environment templates and launchd configuration.

## License

Private repository.
