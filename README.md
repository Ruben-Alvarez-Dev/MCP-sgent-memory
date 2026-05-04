# MCP-agent-memory

> **Persistent multi-layer memory for AI coding agents.**
> 53 MCP tools + HTTP API + auto-trigger plugin + bilingual vault. Zero-config memory that works without the LLM remembering to use it.

---

## What It Does

AI coding agents (OpenCode, Claude Code, etc.) are stateless — they forget everything when a session ends or context compacts. MCP-agent-memory gives them a **backpack** of persistent memory that survives across sessions, compactions, and restarts.

The backpack captures events **automatically** (no LLM decision needed) and provides 53 tools the agent can use when it needs to recall, decide, or reason.

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                        THE BACKPACK SYSTEM                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐    ┌──────────────────────────────────┐  │
│  │  backpack-orchestrator│    │      MCP-agent-memory            │  │
│  │  (OpenCode Plugin)    │    │      (Python MCP Server)         │  │
│  │                       │    │                                   │  │
│  │  AUTO-TRIGGERS:       │    │  53 MCP TOOLS:                   │  │
│  │  • Every user prompt  │──→│  • L0_capture_* (ingest, memorize) │  │
│  │  • Every tool call    │──→│  • L0_to_L4_consolidation_*       │  │
│  │  • Every file edit    │──→│  • L5_routing_* (context retrieval)│  │
│  │  • Session idle       │──→│  • L2_conversations_* (threads)    │  │
│  │  • Context compact    │──→│  • L3_facts_* (semantic CRUD)      │  │
│  │  • Commit validation  │    │  • L3_decisions_* (vault)         │  │
│  │                       │    │  • Lx_reasoning_* (plans)         │  │
│  │  HTTP → localhost:8890│    │                                   │  │
│  └──────────────────────┘    │  HTTP API → localhost:8890       │  │
│                               │  MCP stdio → stdin/stdout        │  │
│                               └──────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────┐    ┌──────────────────────────────────┐  │
│  │  engram.ts (Plugin)   │    │  Engram Go Binary               │  │
│  │  Go binary lifecycle  │──→│  mem_save, mem_search, etc.      │  │
│  │  Session registration │    │  SQLite + FTS5                   │  │
│  └──────────────────────┘    └──────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                        STORAGE                               │   │
│  │  Qdrant (vectors) │ SQLite (embedding cache) │ Filesystem   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Memory Layers

```
L0 RAW          → Append-only event lake (JSONL)
L1 WORKING      → Steps, facts, hot dialogue (Qdrant)
L2 EPISODIC     → Grouped events, incidents (Qdrant + SQLite)
L3 SEMANTIC     → Decisions, entities, patterns (Qdrant + filesystem)
L4 CONSOLIDATED → Narratives, deep summaries (Qdrant)
L5 SELECTIVE    → Context routing and assembly
```

### What's Automatic vs What Needs Agent Judgment

| Category | Trigger | Examples |
|----------|---------|----------|
| **AUTO** (plugin handles it) | Every user prompt, tool call, file edit, compaction | `L0_capture_ingest_event`, `L0_capture_heartbeat`, `L2_conversations_save`, `L0_to_L4_consolidation_consolidate` |
| **LLM DECIDES** | Agent recognizes a decision, bugfix, or discovery | `L0_capture_memorize`, `L3_decisions_save`, `L5_routing_request_context` |
| **USER ASKS** | Explicit user request | `health_check`, `*_status`, `*_delete_*`, `L3_decisions_search` |

---

## Module Reference

### L0_capture — Real-time Memory Ingestion (`L0_capture_*`)

| Tool | Auto? | Description |
|------|-------|-------------|
| `L0_capture_heartbeat` | ✅ | Signal agent alive, track turns, pre-compute embeddings |
| `L0_capture_ingest_event` | ✅ | Ingest raw L0 event (terminal, git, file, tool_call, user_prompt, file_edited) |
| `L0_capture_memorize` | 🧠 | Store a memory requiring judgment (decision, bugfix, discovery, fact) |
| `L0_capture_status` | 👤 | Show L0_capture daemon status |

### L0_to_L4_consolidation — Memory Consolidation (`L0_to_L4_consolidation_*`)

| Tool | Auto? | Description |
|------|-------|-------------|
| `L0_to_L4_consolidation_heartbeat` | ✅ | Check consolidation thresholds (L1→L2→L3→L4) |
| `L0_to_L4_consolidation_consolidate` | ✅ | Run consolidation across all layers |
| `L0_to_L4_consolidation_dream` | ✅ | Trigger deep dream cycle (background pattern detection) |
| `L0_to_L4_consolidation_dream_status` | 👤 | Check background dream task status |
| `L0_to_L4_consolidation_force_promote` | 👤 | Force-promote memories between layers (debug) |
| `L0_to_L4_consolidation_get_narrative` | 🧠 | Retrieve L4 consolidated memories |
| `L0_to_L4_consolidation_get_semantic` | 🧠 | Retrieve L3 semantic memories |
| `L0_to_L4_consolidation_status` | 👤 | Show L0_to_L4_consolidation daemon state |

### L5_routing — Smart Context Retrieval (`L5_routing_*`)

| Tool | Auto? | Description |
|------|-------|-------------|
| `L5_routing_request_context` | 🧠 | Smart context retrieval with intent classification |
| `L5_routing_check_reminders` | ✅ | Check pending context reminders |
| `L5_routing_push_reminder` | ✅ | Push a context reminder for later injection |
| `L5_routing_detect_shift` | ✅ | Detect domain shift between queries |
| `L5_routing_dismiss_reminder` | ⚙️ | Dismiss a reminder (internal) |
| `L5_routing_status` | 👤 | Show L5_routing router status |

### L2_conversations — Thread Persistence (`L2_conversations_*`)

| Tool | Auto? | Description |
|------|-------|-------------|
| `L2_conversations_save` | ✅ | Save a conversation thread (auto on compaction) |
| `L2_conversations_search` | 🧠 | Search past conversations by similarity |
| `L2_conversations_get` | 🧠 | Retrieve a conversation by thread ID |
| `L2_conversations_list_threads` | 👤 | List recent conversation threads |
| `L2_conversations_status` | 👤 | Show conversation store status |

### L3_facts — Semantic Memory (`L3_facts_*`)

| Tool | Auto? | Description |
|------|-------|-------------|
| `L3_facts_add` | 🧠 | Add a semantic memory for a user |
| `L3_facts_search` | 🧠 | Search semantic memories |
| `L3_facts_list` | 👤 | List all memories for a user |
| `L3_facts_delete` | 👤 | Delete a memory by ID |
| `L3_facts_status` | 👤 | Show L3_facts status |

### L3_decisions — Decision Memory & Vault (`L3_decisions_*`)

| Tool | Auto? | Description |
|------|-------|-------------|
| `L3_decisions_save` | 🧠 | Save an architectural decision as Markdown |
| `L3_decisions_search` | 🧠 | Search decisions by keyword |
| `L3_decisions_get` | 🧠 | Get a specific decision by file path |
| `L3_decisions_list` | 🧠 | List decisions with optional filtering |
| `L3_decisions_delete` | 👤 | Delete a decision file |
| `L3_decisions_vault_write` | 🧠 | Write a note to the Obsidian vault |
| `L3_decisions_vault_read_note` | 🧠 | Read a vault note |
| `L3_decisions_vault_list_notes` | 🧠 | List notes in a vault folder |
| `L3_decisions_vault_process_inbox` | 👤 | Process vault inbox items |
| `L3_decisions_vault_integrity_check` | 👤 | Verify vault consistency |
| `L3_decisions_status` | 👤 | Show L3_decisions status |

### Lx_reasoning — Sequential Thinking (`Lx_reasoning_*`)

| Tool | Auto? | Description |
|------|-------|-------------|
| `Lx_reasoning_think` | 🧠 | Multi-step reasoning chain |
| `Lx_reasoning_record_step` | 🧠 | Record a single thinking step |
| `Lx_reasoning_create_plan` | 🧠 | Create an execution plan |
| `Lx_reasoning_update_plan` | 🧠 | Update a plan step status |
| `Lx_reasoning_reflect` | 🧠 | Reflect on reasoning quality |
| `Lx_reasoning_propose_changes` | 🧠 | Propose a code change set |
| `Lx_reasoning_apply_sandbox` | 🧠 | Apply changes in sandbox mode |
| `Lx_reasoning_get_session` | 🧠 | Retrieve a thinking session |
| `Lx_reasoning_list_sessions` | 👤 | List recent thinking sessions |
| `Lx_reasoning_status` | 👤 | Show sequential thinking status |

### Health

| Tool | Description |
|------|-------------|
| `health_check` | Check health of all memory subsystems (Qdrant, embedding, collections, disk) |

**Legend**: ✅ = auto-triggered by plugin | 🧠 = LLM decides when | 👤 = user-triggered | ⚙️ = internal

---

## Directory Structure

```
MCP-servers/agent-memory/
├── bin/                          # Executables: qdrant, llama-server
├── etc/                          # Config: .env, qdrant.yaml, mcp.json
├── data/                         # ALL persistent memory
│   ├── L0-sensory/              # events.jsonl
│   ├── L1-working/              # agents/
│   ├── L2-episodic/             # conversations.db
│   ├── L3-semantic/             # decisions/, facts/
│   ├── L4-narrative/            # consolidation-state.json
│   ├── L5-selective/            # reminders/
│   ├── Lx-deliberative/         # sessions/, plans/
│   └── Lx-persistent/           # bilingual vault
│       ├── ES/                  # Spanish (user writes in Obsidian)
│       │   ├── Conocimiento/
│       │   ├── Decisiones/
│       │   ├── Notas/
│       │   ├── Inbox/
│       │   ├── Episodios/
│       │   └── Entidades/
│       ├── EN/                  # English (system copy)
│       │   ├── knowledge/
│       │   ├── decisions/
│       │   ├── notes/
│       │   ├── inbox/
│       │   ├── episodes/
│       │   └── entities/
│       └── .system/             # counter.json
├── qdrant/                      # Vector storage
├── engine/                      # Compiled llama.cpp
├── models/                      # GGUF: embeddings/, reasoning/
├── logs/
├── src/
│   ├── shared/                 # Core library (pip install -e .)
│   │   ├── config.py           # Environment configuration
│   │   ├── embedding.py        # BGE-M3 via llama.cpp
│   │   ├── qdrant_client.py    # Qdrant vector operations
│   │   ├── sanitize.py         # Input validation & XSS protection
│   │   ├── retrieval/          # Hybrid retrieval + ranking
│   │   ├── vault_manager/      # Obsidian vault atomic writes
│   │   ├── conversation_db.py  # SQLite + FTS5 thread storage
│   │   ├── timeline.py         # Event timeline
│   │   ├── llm/                # LLM integration (llama.cpp)
│   │   ├── diff_sandbox.py     # Code change sandbox
│   │   ├── observe.py          # File system observer
│   │   └── vault_constants.py  # Folder mappings
│   ├── unified/server/main.py  # Unified MCP server entrypoint
│   ├── L0_capture/             # Auto-capture: memorize, ingest, heartbeat
│   ├── L0_to_L4_consolidation/ # Memory consolidation & dreaming
│   ├── L2_conversations/       # Thread storage & search
│   ├── L3_facts/               # Semantic memory CRUD
│   ├── L3_decisions/           # Vault decisions + Obsidian notes
│   ├── L5_routing/             # Context retrieval + reminders
│   └── Lx_reasoning/           # Sequential thinking + plans
├── install/                    # Bootstrap + app-install scripts
├── tests/                      # 164 tests (core/ + app/)
│   ├── core/                   # No external services needed
│   └── app/                    # Requires Qdrant + embedding server
├── install/
├── backups/
└── .venv/
```

---

## Vault Bilingual System

The vault is a bilingual knowledge base that supports both Spanish (ES) and English (EN) versions of all notes.

### File Format

```
L{layer}_{TYPE}_{YYYYMMDDTHHMMSS}_{NNNNN}_{lang}.md
```

**Example**: `L3_decision_20260103T143022_00001_EN.md`

### Directory Structure

- **ES/** (Spanish): User writes here in Obsidian
- **EN/** (English): System maintains automatic copy
- **.system/**: Internal metadata (counter.json)

### Classification Tags

| Tag | Destination Folder |
|-----|-------------------|
| `#decision` | Decisiones/ / decisions/ |
| `#conocimiento` | Conocimiento/ / knowledge/ |
| `#episodio` | Episodios/ / episodes/ |
| `#entidad` | Entidades/ / entities/ |
| `#nota` | Notas/ / notes/ |
| **No tag** | Notas/ / notes/ (default) |

### Auto-Serialization Daemon

The vault processor (`vault_processor.py`) runs as a launchd service with WatchPaths monitoring. When you save a note in Obsidian (ES), it automatically:

1. Detects file changes
2. Extracts content and metadata
3. Generates English translation (if needed)
4. Creates/updates EN version
5. Updates Qdrant embeddings
6. Updates `.system/counter.json`

---

## Engine

MCP-agent-memory uses **llama.cpp** compiled from source with Metal GPU support for fast, local inference.

### Components

- **Embedding Model**: bge-m3 (1024 dimensions)
- **LLM**: qwen2.5-7b-instruct
- **Backend**: llama.cpp with Metal acceleration
- **Installation**: NO Homebrew dependencies — compiled from source

### Compilation

The installer automatically compiles llama.cpp with Metal support:

```bash
cd engine/llama.cpp
cmake -DCMAKE_BUILD_TYPE=Release -DLLAMA_METAL=ON ..
make -j$(sysctl -n hw.ncpu)
```

---

## Installation

```bash
# Full install (bootstrap + app configuration)
curl -fsSL https://raw.githubusercontent.com/Ruben-Alvarez-Dev/MCP-agent-memory/main/install.sh | bash

# Custom path
curl -fsSL ... | bash -s -- ~/my-path

# Skip LLM model download (~4.4GB)
SKIP_LLM=1 bash install.sh

# Reconfigure without re-bootstrap (e.g., new MCP client)
bash install.sh --app-only
```

The installer has two phases:
1. **Bootstrap** (`install/bootstrap.sh`) — venv, Qdrant, BGE-M3 embedding, optional LLM model
2. **App Install** (`install/app-install.sh`) — config, MCP client setup, verification

Or install from source as a Python package:
```bash
pip install -e .   # installs agent-memory-core with all dependencies
```

### Post-Install: Enable the Backpack Plugin

For OpenCode users, copy the plugin:

```bash
cp plugins/backpack-orchestrator.ts ~/.config/opencode/plugins/
```

Then restart OpenCode. The plugin auto-connects to the HTTP API on localhost:8890.

---

## Configuration

### Environment Variables (`etc/.env`)

```env
QDRANT_URL=http://127.0.0.1:6333
EMBEDDING_BACKEND=llama_server
LLAMA_SERVER_URL=http://127.0.0.1:8081
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
LLM_BACKEND=llama_cpp
LLM_MODEL=qwen2.5:7b
AUTOMEM_API_PORT=8890              # HTTP sidecar port (default: 8890)
```

### MCP Client Configuration

**OpenCode** (`~/.config/opencode/opencode.json`):
```json
{
  "mcpServers": {
    "MCP-agent-memory": {
      "type": "local",
      "command": ["/path/to/.venv/bin/python3", "-u", "/path/to/src/unified/server/main.py"],
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

---

## HTTP API — Plugin Sidecar

The MCP server exposes a lightweight HTTP API on port 8890 for plugin-to-server communication. This runs in a background thread alongside the MCP stdio server.

| Method | Endpoint | Maps to MCP Tool |
|--------|----------|-----------------|
| GET | `/api/health` | Health check |
| POST | `/api/ingest-event` | `L0_capture_ingest_event` |
| POST | `/api/heartbeat` | `L0_capture_heartbeat` |
| POST | `/api/heartbeat-dream` | `L0_to_L4_consolidation_heartbeat` |
| POST | `/api/save-conversation` | `L2_conversations_save` |
| POST | `/api/consolidate` | `L0_to_L4_consolidation_consolidate` |

---

## Security

- **Input sanitization**: OWASP-grade — Unicode normalization, bidi stripping, invisible char removal, path traversal prevention (652 lines in `sanitize.py`)
- **Filename validation**: OS-safe filenames, Windows reserved name checking
- **Path confinement**: L3_decisions and vault restricted to project directories
- **Config validation**: URLs, backends, dimensions validated at startup
- **HTTP API**: localhost only (127.0.0.1), no network exposure

---

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

---

## Version History

| Version | Milestone | What Changed |
|---------|-----------|--------------|
| **v0.1** | Proof of concept | Individual servers running separately |
| **v0.2** | Unified server | 7→1 consolidation with dynamic module loading |
| **v1.0** | MVP Release | 53 tools, 92% domain coverage, full sanitization, benchmarks |
| **v1.1** | Security audit | OWASP-grade input sanitization (652 lines), path confinement |
| **v1.2** | The Backpack | `backpack-orchestrator` plugin + HTTP API sidecar. Auto-triggers |
| **v2.0** | **Descriptive Naming** | Lx_NAME scheme, bilingual vault, compiled engine, modular installer |

### v2.0 — Descriptive Naming (Current)

**What changed**: Renamed all modules and tools to use the descriptive Lx_NAME scheme for clarity:

- `automem` → `L0_capture_*`
- `autodream` → `L0_to_L4_consolidation_*`
- `vk_cache` → `L5_routing_*`
- `conversation_store` → `L2_conversations_*`
- `mem0` → `L3_facts_*`
- `engram` → `L3_decisions_*`
- `sequential_thinking` → `Lx_reasoning_*`

**New features**:
- Bilingual vault (ES/EN) with auto-translation
- Compiled llama.cpp engine (no Homebrew dependencies)
- Modular installer with engine compilation
- Launchd services for vault processor and Qdrant watchdog

---

## License

MIT
