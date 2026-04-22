# MCP-sgent-memory

Hierarchical memory system for AI agents — a single MCP server providing 51 tools for persistent, multi-layered memory with semantic search, consolidation, and automatic dream-cycle processing.

## Architecture

```
L0 (Raw Events) → L1 (Working) → L2 (Short-term) → L3 (Semantic) → L4 (Consolidated)
```

### Unified Server

All 7 memory modules are consolidated into **one MCP server** entry point with prefixed tool names:

| Module | Prefix | Purpose | Tools |
|--------|--------|---------|-------|
| **automem** | `automem_*` | Real-time memory ingest | 4 |
| **autodream** | `autodream_*` | Layer consolidation & dream cycle | 6 |
| **vk-cache** | `vk_cache_*` | Vector retrieval & context assembly | 7 |
| **conversation-store** | `conversation_store_*` | Thread persistence | 5 |
| **mem0** | `mem0_*` | Semantic memory (Mem0-compatible) | 5 |
| **engram** | `engram_*` | Decisions, vault, model packs | 14 |
| **sequential-thinking** | `sequential_thinking_*` | Reasoning chains & planning | 10 |

**Total: 51 tools** via a single stdio MCP connection.

### Infrastructure

| Service | Port | Purpose |
|---------|------|---------|
| **Qdrant** | 6333 | Vector database (BM25 + dense) |
| **llama-server** | 8081 | Local embedding inference (BGE-M3) |

## Requirements

- **Python** 3.10+
- **Node.js** (optional, for embedding model download)
- **llama.cpp** — `brew install llama.cpp`
- **Qdrant** — bundled or `brew install qdrant`

## Installation

### One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/Ruben-Alvarez-Dev/MCP-sgent-memory/main/servers/install.sh | bash
```

This single command auto-downloads the repo, compiles llama.cpp from source with Metal (macOS) or CUDA (Linux), downloads the BGE-M3 model, installs deps, starts Qdrant + llama-server, creates collections, generates config, and verifies everything.

### Manual

```bash
git clone https://github.com/Ruben-Alvarez-Dev/MCP-sgent-memory.git
cd MCP-sgent-memory/servers
bash install.sh
```

The installer will:

1. Ask for install location (default: `~/MCP-servers/MCP-agent-memory/`)
2. Detect Python 3.10+ and auto-assign ports
3. Install Qdrant (bundled or system) and create vector collections
4. Copy all 7 server modules + unified entry point
5. Create Python venv with dependencies
6. Generate `.env` and `mcp.json` configuration
7. Create startup scripts
8. Verify installation

### Output Layout

```
~/MCP-servers/MCP-agent-memory/
├── src/                         ← Runtime code
│   ├── automem/server/main.py
│   ├── autodream/server/main.py
│   ├── vk-cache/server/main.py
│   ├── conversation-store/server/main.py
│   ├── mem0/server/main.py
│   ├── engram/server/main.py
│   ├── sequential-thinking/server/main.py
│   ├── unified/server/main.py   ← Single entry point
│   └── shared/                  ← Common modules
├── config/
│   ├── .env                     ← Environment variables
│   └── mcp.json                 ← MCP server config
├── data/                        ← Memory storage (Qdrant + files)
├── vault/                       ← Obsidian vault for decisions
├── .venv/                       ← Python environment
├── bin/                         ← Qdrant binary
├── engine/                      ← llama.cpp binaries
├── models/                      ← Embedding models (.gguf)
└── scripts/                     ← Startup scripts
```

## MCP Configuration

The installer generates `config/mcp.json` with a single unified server:

```json
{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "~/MCP-servers/MCP-agent-memory/.venv/bin/python3",
      "args": ["-u", "~/MCP-servers/MCP-agent-memory/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "~/MCP-servers/MCP-agent-memory/src",
        "MEMORY_SERVER_DIR": "~/MCP-servers/MCP-agent-memory",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024"
      }
    }
  }
}
```

### Connecting to Pi

```bash
cp ~/MCP-servers/MCP-agent-memory/config/mcp.json ~/.pi/mcp.json
```

### Connecting to Claude Code

```bash
claude mcp add -s user MCP-agent-memory \
  --env PYTHONPATH=~/MCP-servers/MCP-agent-memory/src \
  --env MEMORY_SERVER_DIR=~/MCP-servers/MCP-agent-memory \
  --env QDRANT_URL=http://127.0.0.1:6333 \
  -- \
  ~/MCP-servers/MCP-agent-memory/.venv/bin/python3 \
  -u ~/MCP-servers/MCP-agent-memory/src/unified/server/main.py
```

## Tool Reference

### automem_* — Memory Ingestion

| Tool | Description |
|------|-------------|
| `automem_memorize` | Store a memory item with tags and metadata |
| `automem_ingest_event` | Ingest a raw event (terminal, git, file, system) |
| `automem_heartbeat` | Signal agent is alive; trigger promotion checks |
| `automem_status` | Health check for the automem daemon |

### autodream_* — Consolidation

| Tool | Description |
|------|-------------|
| `autodream_consolidate` | Force memory consolidation across layers |
| `autodream_dream` | Run the dream cycle (pattern mining + promotion) |
| `autodream_get_consolidated` | Get L4 consolidated memories |
| `autodream_get_semantic` | Get L3 semantic memories |
| `autodream_heartbeat` | Turn-count heartbeat for promotion scheduling |
| `autodream_status` | Health check for autodream daemon |

### vk_cache_* — Retrieval & Context

| Tool | Description |
|------|-------------|
| `vk_cache_request_context` | Assemble context pack from semantic search |
| `vk_cache_check_reminders` | Check pending context reminders |
| `vk_cache_push_reminder` | Create a context reminder |
| `vk_cache_dismiss_reminder` | Dismiss a reminder by ID |
| `vk_cache_detect_context_shift` | Detect when context needs change |
| `vk_cache_status` | Health check for vk-cache |
| `vk_cache_verify_compliance_tool` | Verify tool compliance policies |

### conversation_store_* — Threads

| Tool | Description |
|------|-------------|
| `conversation_store_save_conversation` | Save a conversation thread |
| `conversation_store_get_conversation` | Retrieve a thread by ID |
| `conversation_store_search_conversations` | Semantic search across threads |
| `conversation_store_list_threads` | List recent conversation threads |
| `conversation_store_status` | Health check for conversation store |

### mem0_* — Semantic Memory

| Tool | Description |
|------|-------------|
| `mem0_add_memory` | Add a semantic memory (user/agent preference) |
| `mem0_search_memory` | Search semantic memories |
| `mem0_get_all_memories` | List all memories for a user |
| `mem0_delete_memory` | Delete a memory by ID |
| `mem0_status` | Health check for mem0 |

### engram_* — Decisions & Vault

| Tool | Description |
|------|-------------|
| `engram_save_decision` | Save an architectural decision |
| `engram_search_decisions` | Search decisions by keyword |
| `engram_get_decision` | Get a specific decision by file path |
| `engram_list_decisions` | List decisions with filters |
| `engram_delete_decision` | Delete a decision file |
| `engram_vault_write` | Write a note to the Obsidian vault |
| `engram_vault_process_inbox` | Process vault inbox items |
| `engram_vault_integrity_check` | Verify vault consistency |
| `engram_vault_list_notes` | List vault notes by folder |
| `engram_vault_read_note` | Read a specific vault note |
| `engram_get_model_pack` | Get model configuration pack |
| `engram_set_model_pack` | Set active model pack |
| `engram_list_model_packs` | List available model packs |
| `engram_status` | Health check for engram |

### sequential_thinking_* — Reasoning

| Tool | Description |
|------|-------------|
| `sequential_thinking_sequential_thinking` | Step-by-step reasoning chain |
| `sequential_thinking_record_thought` | Record a single thought step |
| `sequential_thinking_create_plan` | Create an execution plan |
| `sequential_thinking_update_plan_step` | Update a plan step status |
| `sequential_thinking_reflect` | Reflect on reasoning quality |
| `sequential_thinking_get_thinking_session` | Retrieve a thinking session |
| `sequential_thinking_list_thinking_sessions` | List recent sessions |
| `sequential_thinking_propose_change_set` | Propose a code change set |
| `sequential_thinking_apply_sandbox` | Apply changes in sandbox |
| `sequential_thinking_status` | Health check for sequential thinking |

## How It Works

### Unified Server (`unified/server/main.py`)

The unified server imports all 7 module servers dynamically at startup:

1. Creates a single `FastMCP("MCP-agent-memory")` instance
2. For each server module, imports its `main.py` (which creates its own internal `FastMCP`)
3. Extracts tools from each module's `_tool_manager._tools`
4. Re-registers them with `mcp.add_tool(fn, name=f"{prefix}_{original_name}")`
5. Runs `mcp.run(transport="stdio")` as a single MCP server

This means Pi/Claude sees **one MCP server with 51 tools**, each prefixed by module name to avoid collisions (e.g. `automem_status` vs `autodream_status`).

### Memory Layers

| Layer | Name | Storage | Promotion |
|-------|------|---------|-----------|
| L0 | Raw Events | JSONL file | → L1 on ingest |
| L1 | Working Memory | Qdrant (1024d) | → L2 every N turns |
| L2 | Short-term | Qdrant (1024d) | → L3 on dream cycle |
| L3 | Semantic | Qdrant (1024d) | → L4 on consolidation |
| L4 | Consolidated | Markdown + Qdrant | Final layer |

### Dream Cycle

The `autodream_dream` tool runs a background consolidation process:

1. Scans L1 memories → promotes stable ones to L2
2. Scans L2 memories → clusters and abstracts to L3
3. Mines patterns across L3 → produces L4 consolidated insights
4. Updates Qdrant collections with new embeddings

## Development

### Repo Structure

```
MCP-sgent-memory/
├── servers/           ← All source code (this is what install.sh copies)
│   ├── automem/
│   ├── autodream/
│   ├── vk-cache/
│   ├── conversation-store/
│   ├── mem0/
│   ├── engram/
│   ├── sequential-thinking/
│   ├── unified/           ← Unified entry point
│   ├── shared/            ← Common modules
│   ├── tests/
│   ├── config/
│   │   └── .env.example
│   ├── scripts/
│   ├── install.sh
│   └── build-package.sh
├── tests/                 ← Root-level test suite
├── bench/                 ← Benchmarks
├── docs/                  ← Architecture docs
├── scripts/               ← Dev lifecycle scripts
└── README.md
```

### Running Tests

```bash
cd servers
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
```

### Local Development

```bash
# Install to ~/MCP-servers/MCP-agent-memory/
cd servers cd MCP-servers && bashcd MCP-servers && bash bash install.sh

# Test the unified server
cd ~/MCP-servers/MCP-agent-memory
PYTHONPATH=src .venv/bin/python3 src/unified/server/main.py

# Or test individual module
PYTHONPATH=src .venv/bin/python3 src/automem/server/main.py
```

## License

Private repository.
