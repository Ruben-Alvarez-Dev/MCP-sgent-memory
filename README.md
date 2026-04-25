# MCP-agent-memory

A unified MCP (Model Context Protocol) memory server that provides persistent, multi-layer memory for AI coding agents. Runs as a single MCP server with 51 tools across 7 memory subsystems.

## Features

- **AutoMem** — Real-time memory ingestion (L0 raw events → L1 working memory)
- **AutoDream** — Memory consolidation across layers (L1→L2→L3→L4)
- **VK-Cache** — Smart context retrieval with intent classification
- **Conversation Store** — Thread-based conversation persistence
- **Mem0** — Semantic memory with user-scoped CRUD operations
- **Engram** — Decision memory, vault management, model packs
- **Sequential Thinking** — Reasoning chains and execution plans

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Unified MCP Server                        │
│                    (FastMCP, stdio)                          │
├──────┬──────┬──────┬──────┬──────┬──────────┬──────────────┤
│automem│dream │ vk-  │conv- │ mem0 │ engram   │ sequential-  │
│       │      │cache │store │      │          │ thinking     │
├──────┴──────┴──────┴──────┴──────┴──────────┴──────────────┤
│                      Shared Layer                           │
│  config │ embedding │ qdrant_client │ sanitize │ logging   │
├────────────────────────────────────────────────────────────┤
│                    Storage Layer                            │
│  Qdrant (vectors) │ SQLite (cache) │ Filesystem (vault)   │
└────────────────────────────────────────────────────────────┘
```

## Requirements

- Python 3.12+
- [Qdrant](https://qdrant.tech/) (vector database)
- [llama.cpp](https://github.com/ggerganov/llama.cpp) with BGE-M3 model (embedding server)
- [llama.cpp](https://llama_cpp.ai/) or llama.cpp (LLM backend)

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Ruben-Alvarez-Dev/MCP-agent-memory/main/install.sh | bash
```

Installs to `~/MCP-servers/MCP-agent-memory` by default. Custom path:

```bash
curl -fsSL https://raw.githubusercontent.com/Ruben-Alvarez-Dev/MCP-agent-memory/main/install.sh | bash -s -- ~/my-custom-path
```

The installer performs 8 steps with a visual checklist:
- Python venv creation
- Dependency installation (pydantic, httpx, mcp)
- Qdrant vector database startup
- BGE-M3 embedding model download + llama-server startup
- llama.cpp LLM backend detection
- Config generation (.env + directory structure)
- MCP client configuration (auto-detects Pi, Claude Desktop)
- Full verification (imports, config, connectivity, unit tests)

## Configuration

### Environment Variables

Create `config/.env`:

```env
QDRANT_URL=http://127.0.0.1:6333
EMBEDDING_BACKEND=llama_server
LLAMA_SERVER_URL=http://127.0.0.1:8081
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
LLM_BACKEND=llama_cpp
LLM_MODEL=qwen2.5:7b
```

### MCP Client Configuration

Add to your MCP client config (e.g., `~/.pi/mcp.json`):

```json
{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "/path/to/.venv/bin/python3",
      "args": ["-u", "/path/to/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "/path/to/src",
        "MEMORY_SERVER_DIR": "/path/to/MCP-agent-memory",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "EMBEDDING_BACKEND": "llama_server",
        "LLAMA_SERVER_URL": "http://127.0.0.1:8081",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024"
      }
    }
  }
}
```

## Tools Reference

### AutoMem (`automem_*`)

| Tool | Description |
|------|-------------|
| `automem_memorize` | Store a memory (fact, preference, step, etc.) |
| `automem_ingest_event` | Ingest a raw event (terminal, git, file, system) |
| `automem_heartbeat` | Update agent heartbeat signal |
| `automem_status` | Show AutoMem daemon status |

### AutoDream (`autodream_*`)

| Tool | Description |
|------|-------------|
| `autodream_consolidate` | Run memory consolidation cycle |
| `autodream_dream` | Trigger deep dream cycle (pattern detection) |
| `autodream_get_consolidated` | Get L4 consolidated memories |
| `autodream_get_semantic` | Get L3 semantic memories |
| `autodream_heartbeat` | AutoDream heartbeat |
| `autodream_status` | Show AutoDream status |

### VK-Cache (`vk_cache_*`)

| Tool | Description |
|------|-------------|
| `vk_cache_request_context` | Smart context retrieval with intent classification |
| `vk_cache_push_reminder` | Push a context reminder |
| `vk_cache_check_reminders` | Check pending reminders |
| `vk_cache_dismiss_reminder` | Dismiss a reminder |
| `vk_cache_detect_context_shift` | Detect conversation context shift |
| `vk_cache_status` | Show VK-Cache status |

### Conversation Store (`conversation_store_*`)

| Tool | Description |
|------|-------------|
| `conversation_store_save_conversation` | Save a conversation thread |
| `conversation_store_search_conversations` | Search past conversations |
| `conversation_store_get_conversation` | Retrieve a conversation by ID |
| `conversation_store_list_threads` | List recent threads |
| `conversation_store_status` | Show store status |

### Mem0 (`mem0_*`)

| Tool | Description |
|------|-------------|
| `mem0_add_memory` | Add a semantic memory for a user |
| `mem0_search_memory` | Search semantic memories |
| `mem0_get_all_memories` | List all memories for a user |
| `mem0_delete_memory` | Delete a memory by ID |
| `mem0_status` | Show mem0 status |

### Engram (`engram_*`)

| Tool | Description |
|------|-------------|
| `engram_save_decision` | Save an architectural decision |
| `engram_search_decisions` | Search decisions by keyword |
| `engram_get_decision` | Get a decision by file path |
| `engram_list_decisions` | List decisions with filtering |
| `engram_delete_decision` | Delete a decision |
| `engram_vault_write` | Write a note to the vault |
| `engram_vault_read_note` | Read a vault note |
| `engram_vault_list_notes` | List vault notes |
| `engram_vault_process_inbox` | Process vault inbox items |
| `engram_vault_integrity_check` | Verify vault consistency |
| `engram_get_model_pack` | Get a model configuration pack |
| `engram_set_model_pack` | Set active model pack |
| `engram_list_model_packs` | List available model packs |
| `engram_status` | Show engram status |

### Sequential Thinking (`sequential_thinking_*`)

| Tool | Description |
|------|-------------|
| `sequential_thinking_sequential_thinking` | Step-by-step reasoning chain |
| `sequential_thinking_record_thought` | Record a single thought step |
| `sequential_thinking_create_plan` | Create an execution plan |
| `sequential_thinking_update_plan_step` | Update a plan step status |
| `sequential_thinking_reflect` | Reflect on reasoning quality |
| `sequential_thinking_propose_change_set` | Propose a code change set |
| `sequential_thinking_apply_sandbox` | Apply changes in sandbox mode |
| `sequential_thinking_get_thinking_session` | Retrieve a thinking session |
| `sequential_thinking_list_thinking_sessions` | List recent sessions |
| `sequential_thinking_status` | Show thinking status |

### Health (`health_check`)

| Tool | Description |
|------|-------------|
| `health_check` | Check health of all memory subsystems |

## Security

- **Input sanitization**: OWASP-grade (Unicode normalization, bidi stripping, path traversal prevention)
- **Filename validation**: OS-safe filenames, Windows reserved name checking
- **Path confinement**: Engram decisions and vault restricted to project directories
- **Config validation**: URLs, backends, dimensions validated at startup

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

45 tests across:
- `test_engram.py` — Path confinement, model pack sanitization
- `test_qdrant_client.py` — Vector validation, retry logic, config
- `test_sanitize.py` — Text, filename, folder, JSON, tag sanitization

## License

MIT
