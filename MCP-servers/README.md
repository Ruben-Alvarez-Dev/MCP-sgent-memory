# MCP Memory Server — Complete Documentation

> **Version:** 1.0.0
> **Date:** 2026-04-08
> **Status:** Ready for delivery

---

## Overview

Self-contained, production-ready memory system for AI agents. 6-layer memory stack with bidirectional LLM protocol, bundled embedding engine, and zero external dependencies.

### Key Features

- **Zero external deps**: No Docker, no Homebrew, no Ollama. Everything bundled.
- **Agent-independent**: Memory daemons run 24/7 regardless of LLM connection state.
- **Bidirectional protocol**: LLM pulls context, system pushes reminders.
- **Scoped backpacks**: Each agent has isolated memory with declared permissions.
- **Auto-start on boot**: launchd services for Qdrant and Gateway.

---

## Architecture

### 7 MCP Servers

| Server | Layer | Tools | Purpose |
|--------|-------|-------|---------|
| **automem** | L0/L1/L2 | 4 | Real-time ingest, heartbeat, event capture |
| **autodream** | L3/L4 | 5 | Scheduled consolidation, summarization, dream cycles |
| **vk-cache** | L5 | 6 | Unified retrieval, context assembly, bidirectional protocol |
| **sequential-thinking** | — | 8 | Structured reasoning framework, planner, reflection |
| **conversation-store** | L2 | 5 | Full conversation threads with semantic search |
| **mem0-bridge** | L1 | 5 | Semantic memory (facts, preferences) |
| **engram-bridge** | L3 | 6 | Curated decisions, entities, patterns (filesystem) |

### Memory Layers

```
L0 RAW          → Append-only JSONL audit trail
L1 WORKING      → Hot facts, recent steps (Qdrant + bundled embeddings)
L2 EPISODIC     → Conversations, incidents (Qdrant)
L3 SEMANTIC     → Decisions, entities, patterns (Engram + Qdrant)
L4 CONSOLIDATED → Summaries, narratives, dreams (Qdrant)
L5 CONTEXT      → Ephemeral packs (assembled on demand)
```

### Promotion Schedule

| Transition | Trigger | Frequency |
|------------|---------|-----------|
| L0 → L1 | Every event | Real-time |
| L1 → L2 | Group related steps | Every 10 turns |
| L2 → L3 | LLM extract decisions | Every hour |
| L3 → L4 | Narrative consolidation | Every 24h |
| L4 Dream | Deep pattern detection | Every 7 days |

---

## Installation

### From .dmg

1. Open `MCP-Memory-Server.dmg`
2. Run `install.sh`
3. Choose install location (default: `~/MCP-servers/MCP-agent-memory/`)
4. Wait for services to start

### Prerequisites

- **macOS** (Apple Silicon)
- **Python 3.10+**
- **Node.js 20+** (optional, for HTTP gateway)

### What Gets Installed

```
~/MCP-servers/MCP-agent-memory/
├── engine/                    ← Bundled llama.cpp + 11 libraries
│   ├── bin/llama-embedding
│   └── lib/*.dylib, *.so
├── models/                    ← Embedding model (44MB)
│   └── all-minilm-l6-v2_f16.gguf
├── servers/                   ← 7 MCP server implementations
├── shared/                    ← Data models + embedding wrapper
├── config/                    ← .env + mcp.json
├── skills/                    ← Agent instruction sets
└── .venv/                     ← Python environment
```

---

## Usage

### Start Services

```bash
# Recommended: Start all-in-one launcher (daemonized embedding server + config)
./scripts/start-all.sh

# Services auto-start via launchd. To manually control components:
launchctl start com.agent-memory.qdrant
launchctl start com.agent-memory.gateway  # if Node.js installed
```

### Embedding Engine (Híbrido - Dos Tiempos)

The system automatically chooses the best available embedding strategy:

1. **Fast Path (17ms)**: Connects to a persistent `llama-server` HTTP daemon. 
2. **Fallback Path (1.2s)**: Spawns a `llama-embedding` subprocess (robust, zero-config).
3. **Instant Path (<1μs)**: LRU Cache hit for previously seen strings.

**Speedup:** Using the server daemon provides a **70x speedup** over the fallback path.

To manage the server daemon:
```bash
./scripts/start-embedding-server.sh  # Start daemon
./scripts/stop-embedding-server.sh   # Stop daemon
```

### Verify Installation

```bash
# Check services
launchctl list | grep memory-server

# Test health
curl -s http://127.0.0.1:6333/collections   # Qdrant
curl -s http://127.0.0.1:3050/health        # Gateway

# Test engine
source ~/MCP-servers/MCP-agent-memory/.venv/bin/activate
python3 -c "
from shared.embedding import get_embedding
vec = get_embedding('hello world')
print(f'{len(vec)} dimensions: {[round(v,4) for v in vec[:5]]}')
"
```

### Connect a Client

**HTTP Endpoint:** `http://127.0.0.1:3050/mcp`

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "memory": {
      "url": "http://127.0.0.1:3050/mcp?app=cursor"
    }
  }
}
```

**Claude Code:**
```bash
claude mcp add -t http memory "http://127.0.0.1:3050/mcp?app=claude-code"
```

### Available Tools (39 total)

| Server | Tool Name | Description |
|--------|-----------|-------------|
| automem | `heartbeat` | Signal agent is alive |
| automem | `memorize` | Store a memory |
| automem | `ingest_event` | Capture raw event |
| automem | `status` | Daemon status |
| autodream | `consolidate` | Run consolidation |
| autodream | `dream` | Deep dream cycle |
| autodream | `get_consolidated` | Get L4 memories |
| autodream | `get_semantic` | Get L3 memories |
| autodream | `status` | Daemon status |
| vk-cache | `request_context` | Pull context |
| vk-cache | `check_reminders` | Check pending reminders |
| vk-cache | `push_reminder` | Push a reminder |
| vk-cache | `dismiss_reminder` | Dismiss a reminder |
| vk-cache | `detect_context_shift` | Detect topic change |
| vk-cache | `status` | Router status |
| sequential-thinking | `sequential_thinking` | Start thinking session |
| sequential-thinking | `record_thought` | Record a conclusion |
| sequential-thinking | `create_plan` | Create execution plan |
| sequential-thinking | `update_plan_step` | Update step status |
| sequential-thinking | `reflect` | Review and find gaps |
| sequential-thinking | `get_thinking_session` | Get thinking trace |
| sequential-thinking | `list_thinking_sessions` | List all sessions |
| sequential-thinking | `status` | Server status |
| conversation-store | `save_conversation` | Save a thread |
| conversation-store | `get_conversation` | Get a thread |
| conversation-store | `search_conversations` | Semantic search |
| conversation-store | `list_threads` | List recent threads |
| conversation-store | `status` | Server status |
| mem0-bridge | `add_memory` | Add semantic memory |
| mem0-bridge | `search_memory` | Search memories |
| mem0-bridge | `get_all_memories` | List all memories |
| mem0-bridge | `delete_memory` | Delete a memory |
| mem0-bridge | `status` | Server status |
| engram-bridge | `save_decision` | Save a decision |
| engram-bridge | `search_decisions` | Search decisions |
| engram-bridge | `get_decision` | Get a decision |
| engram-bridge | `list_decisions` | List decisions |
| engram-bridge | `delete_decision` | Delete a decision |
| engram-bridge | `status` | Server status |

---

## Bidirectional Protocol

### PULL: LLM Requests Context

```
LLM → vk-cache: request_context(query="What about project X?")
Memory → LLM: ContextPack with ranked, deduplicated, compressed context
```

### PUSH: Memory Proactively Reminds

```
System detects: domain change, periodic timer, relevant entity mentioned
System → vk-cache: push_reminder(reason="domain_change_detected")
LLM → vk-cache: check_reminders() → receives pending reminders
LLM → vk-cache: dismiss_reminder(reminder_id) → system learns preferences
```

### Handshake Logic

1. LLM receives context pack or reminder
2. LLM uses it → system tracks usage (+weight next time)
3. LLM asks for more → explicit `request_context`
4. LLM dismisses → system learns
5. If ignored N turns → auto-decay

---

## Configuration

### Environment Variables (`config/.env`)

```bash
# Qdrant
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=automem

# Embeddings
EMBEDDING_DIM=384

# AutoDream schedules (seconds)
DREAM_PROMOTE_L1=10
DREAM_PROMOTE_L2=3600
DREAM_PROMOTE_L3=86400
DREAM_PROMOTE_L4=604800

# VK-Cache
VK_MIN_SCORE=0.3
VK_MAX_ITEMS=8
VK_MAX_TOKENS=8000
```

### Data Directories

```
~/.memory/
├── raw_events.jsonl       # L0 audit trail
├── engram/                # L3 decisions (Markdown)
├── dream/                 # Consolidation state
├── heartbeats/            # Agent heartbeat files
├── reminders/             # Pending context reminders
├── thoughts/              # Sequential thinking sessions
├── qdrant.log             # Qdrant stdout
├── qdrant-error.log       # Qdrant stderr
├── gateway.log            # Gateway stdout
└── gateway-error.log      # Gateway stderr
```

---

## Management

### Service Control

```bash
# Qdrant
launchctl stop com.agent-memory.qdrant
launchctl start com.agent-memory.qdrant

# Gateway
launchctl stop com.agent-memory.gateway
launchctl start com.agent-memory.gateway

# Check status
launchctl list | grep memory-server
```

### Logs

```bash
tail -f ~/.memory/qdrant.log
tail -f ~/.memory/qdrant-error.log
tail -f ~/.memory/gateway.log
tail -f ~/.memory/gateway-error.log
```

### Troubleshooting

| Symptom | Solution |
|---------|----------|
| Qdrant not starting | Check `~/.memory/qdrant-error.log`, verify `ulimit -n 10240` |
| Gateway not responding | `launchctl stop/start com.agent-memory.gateway` |
| Engine not found | Verify `~/MCP-servers/MCP-agent-memory/engine/bin/llama-embedding` exists |
| Model not found | Verify `~/MCP-servers/MCP-agent-memory/models/*.gguf` exists |
| High memory usage | Run `autodream → consolidate` to prune old memories |

---

## Testing

```bash
cd ~/MCP-servers/MCP-agent-memory
source .venv/bin/activate

# Engine test
python3 -c "
from shared.embedding import get_embedding
vec = get_embedding('hello world')
assert len(vec) == 384
print('✅ Engine OK')
"

# Gateway test (requires services running)
curl -s http://127.0.0.1:3050/health | python3 -m json.tool

# Full E2E test
python3 /tmp/e2e_test.py
# Expected: 41/41 passed
```

---

## License

MIT
