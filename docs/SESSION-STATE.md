# MCP Memory Stack — Session State & Project Documentation

> **Last updated:** 2026-04-15
> **Status:** V3 / Evolution V2 in active implementation
> **This document:** Resume point for future sessions

---

## 1. Quick Resume — Where We Are

### ✅ V3 / Evolution V2 implemented in this branch
| Capability | Status | Notes |
|-----------|--------|-------|
| Local skill registry bootstrap in `1mcp-agent` | ✅ Implemented | Loads `MCP-servers/skills/*/SKILL.md` through `src/core/skills/loader.ts` and registers them into `InstructionAggregator` during server setup |
| Local skill instructions in aggregated prompt | ✅ Implemented | Standalone local skills are now injected even when they are not backed by outbound MCP connections |
| Repository map models | ✅ Implemented | `shared/models/repo.py` adds `RepoNode` and `RepoMap` |
| Repo map retrieval utility | ✅ Implemented | `shared/retrieval/repo_map.py` resolves target files plus immediate dependencies |
| Repository L2 indexer | ✅ Implemented | `shared/retrieval/index_repo.py` scans repo files and upserts symbol signatures into Qdrant layer 2 |
| Token pruning | ✅ Implemented | `shared/retrieval/pruner.py` now does AST-based body collapsing for Python plus heuristic fallback for other languages |
| `vk-cache` repo-aware enrichment | ✅ Implemented | `request_context` / `push_reminder` can attach repo-map context for code-oriented queries |
| Virtual sandbox | ✅ Implemented | `propose_change_set` + `apply_sandbox` stage and then flush changes to disk |
| `automem` staging visibility | ✅ Implemented | `status()` now reports staging buffer path and staged change sets |
| Zero external calls E2E | ✅ Implemented | `tests/test_zero_external_calls_e2e.py` validates a complex coding flow using only localhost calls |
| 100+ file project audit virtualization | ✅ Implemented | `tests/test_zero_external_calls_e2e.py` now verifies retrieval stays within budget while auditing a generated repo of 120 files |

### 🚧 V3 / Evolution V2 still pending
| Item | Notes |
|------|-------|

### ✅ Completed & Tested
| Component | Status | Tests |
|-----------|--------|-------|
| AutoMem (L0/L1/L2 ingest) | ✅ Working | heartbeat, memorize, ingest_event, status |
| AutoDream (L3/L4 consolidation) | ✅ Working | consolidate, dream, get_consolidated, get_semantic, status |
| VK-Cache (L5 context assembly) | ✅ Working | request_context, reminders, detect_context_shift, status |
| Sequential Thinking + Planner | ✅ Working | 8 tools, all tested |
| Conversation Store | ✅ Working | save, get, search, list_threads, status |
| Mem0 Bridge | ✅ Working | add, search, get_all, delete, status |
| Engram Bridge | ✅ Working | save, search, get, list, delete, status |
| 1MCP Gateway (:3050) | ✅ Running | 39 tools from 7 servers |
| Qdrant (native binary) | ✅ Running | launchd service, auto-start |
| llama.cpp engine (bundled) | ✅ Working | 384 dims, cosine sim 0.534, no Homebrew |
| Embedding model (GGUF) | ✅ Bundled | all-minilm-l6-v2-f16.gguf (44MB) |
| .dmg Installer | ✅ Created | MCP-Memory-Server.dmg (183MB) |
| Full E2E Tests | ✅ 9/9 pass | bundled engine + all 7 servers via gateway |

### ❌ Pending (for future sessions)
| Item | Notes |
|------|-------|
| Connect real LLM client (Cursor/Claude/VS Code) | Gateway ready, client config needed |
| Engranar con `src/` app | MCP Hub Bridge app needs to use this system |
| Install .dmg on clean machine | Full clean install test |
| Add qwen2.5:7b model for summarization | AutoDream falls back to concat without it |
| llama.cpp binary download in installer | Currently requires pre-built engine/ dir |

---

## 2. Architecture — What Was Built

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│  ~/MCP-servers/memory-server/ (self-contained)             │
│                                                             │
│  engine/                                                    │
│  ├── bin/llama-embedding    ← Bundled binary (codesigned)   │
│  └── lib/*.dylib            ← 11 bundled libraries          │
│                                                             │
│  models/                                                    │
│  └── all-minilm-l6-v2_f16.gguf  ← Embedding model (384d)    │
│                                                             │
│  servers/                                                   │
│  ├── automem/               ← L0/L1/L2 real-time ingest     │
│  ├── autodream/             ← L3/L4 scheduled consolidation │
│  ├── vk-cache/              ← L5 context assembly           │
│  ├── conversation-store/    ← Thread recording              │
│  ├── mem0-bridge/           ← Semantic memory               │
│  ├── engram-bridge/         ← Decisions & entities          │
│  └── sequential-thinking/   ← Reasoning + planning           │
│                                                             │
│  shared/                                                    │
│  ├── embedding.py           ← llama.cpp wrapper             │
│  └── models/__init__.py     ← Data contracts                │
│                                                             │
│  config/                                                    │
│  ├── .env                   ← Environment variables          │
│  └── mcp.json               ← 1MCP gateway config           │
│                                                             │
│  skills/                                                    │
│  ├── memory-core/SKILL.md   ← Universal memory protocol     │
│  ├── research/SKILL.md      ← Web search + knowledge        │
│  ├── code/SKILL.md          ← Code analysis                 │
│  └── filesystem/SKILL.md    ← File operations               │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  Qdrant (:6333)              │
│  Native binary, launchd      │
│  Collections: automem,       │
│  conversations, mem0_memories│
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  1MCP Gateway (:3050)        │
│  Node.js, launchd            │
│  Aggregates 7 servers → 39   │
│  tools, single HTTP endpoint │
└──────────────────────────────┘
```

### Memory Layers

```
L0 RAW          → Append-only JSONL audit trail
L1 WORKING      → Hot facts, recent steps (Qdrant + llama.cpp embeddings)
L2 EPISODIC     → Conversations, incidents (Qdrant)
L3 SEMANTIC     → Decisions, entities, patterns (Engram + Qdrant)
L4 CONSOLIDATED → Summaries, narratives, dreams (Qdrant)
L5 CONTEXT      → Ephemeral packs (assembled on demand via vk-cache)
```

### Promotion Schedule

| Transition | Trigger | Frequency |
|------------|---------|-----------|
| L0 → L1 | Every event | Real-time |
| L1 → L2 | Group related steps | Every 10 turns |
| L2 → L3 | LLM extract decisions | Every hour |
| L3 → L4 | Narrative consolidation | Every 24h |
| L4 Dream | Deep pattern detection | Every 7 days |

### Bidirectional Protocol

**PULL (LLM requests context):**
```
LLM → vk-cache: request_context(query="...")
Memory → LLM: ContextPack (ranked, deduplicated, compressed)
```

**PUSH (Memory proactively reminds):**
```
System → vk-cache: push_reminder(reason="domain_change_detected")
LLM → vk-cache: check_reminders() → receives pending reminders
LLM → vk-cache: dismiss_reminder(reminder_id) when done
```

### Key Design Decisions

1. **Self-contained**: No Docker, no Homebrew dependency. All binaries bundled with corrected rpaths and codesigned.
2. **llama.cpp for embeddings**: Replaced Ollama dependency. Binary + 11 libs + model all in engine/ and models/.
3. **Agent-independent**: Memory daemons run continuously regardless of LLM connection state.
4. **Scoped backpacks**: Each agent has isolated memory space with declared scopes and permissions.
5. **Virtual context**: Context is assembled via retrieval, not infinite KV cache.
6. **Local skills only for V3**: `1mcp-agent` now bootstraps instructions from `MCP-servers/skills/`, removing the need for external Gentle AI skill resolution in the active path.
7. **Virtual sandbox first, disk second**: planning stages write to `STAGING_BUFFER` before any filesystem mutation.

---

## 3. Infrastructure — Running Services

### Current State (verify on resume)

```bash
# Check services
launchctl list | grep memory-server
# Expected: com.memory-server.qdrant (running)
# Expected: com.memory-server.gateway (running, if Node.js)

# Check ports
curl -s http://127.0.0.1:6333/collections  # Qdrant
curl -s http://127.0.0.1:3050/health       # 1MCP Gateway

# Test engine
cd ~/MCP-servers/memory-server && source .venv/bin/activate
python3 -c "from shared.embedding import get_embedding; print(len(get_embedding('test')))"
```

### Service Management

```bash
# Qdrant
launchctl stop com.memory-server.qdrant
launchctl start com.memory-server.qdrant

# Gateway
launchctl stop com.memory-server.gateway
launchctl start com.memory-server.gateway

# Logs
tail -f ~/.memory/qdrant.log
tail -f ~/.memory/gateway.log
```

---

## 4. File Locations

| Path | Purpose |
|------|---------|
| `~/MCP-servers/memory-server/` | Main installation (future: dmg installs here) |
| `~/MCP-servers/memory-server/engine/` | Bundled llama.cpp engine |
| `~/MCP-servers/memory-server/models/` | GGUF embedding models |
| `~/.memory/` | Runtime data (JSONL, engrams, dreams, heartbeats, reminders, thoughts) |
| `~/.config/1mcp/` | 1MCP gateway configuration |
| `~/Library/LaunchAgents/com.memory-server.*.plist` | System services |
| `/Users/ruben/Code/PROJECT-Memory/project_MEMORY-after-A0/MCP-servers/` | Source code + .dmg |
| `/Users/ruben/Code/PROJECT-Memory/project_MEMORY-after-A0/MCP-servers/MCP-Memory-Server.dmg` | Deliverable |

---

## 5. Tests — How to Re-run

```bash
cd /Users/ruben/Code/PROJECT-Memory/project_MEMORY-after-A0/MCP-servers
source .venv/bin/activate
export MEMORY_SERVER_DIR="$(pwd)"

# Quick engine test
python3 -c "
from shared.embedding import get_embedding
vec = get_embedding('hello world')
assert len(vec) == 384
print('✅ Engine OK')
"

# Full E2E via gateway (requires gateway running)
python3 /tmp/e2e_test.py
# Expected: 41/41 passed (full suite) or 9/9 (quick suite)
```

---

## 6. Known Issues & Workarounds

| Issue | Status | Workaround |
|-------|--------|------------|
| Qdrant jemalloc on macOS | ✅ Fixed | MALLOC_CONF="background_thread:false" in start script |
| Qdrant v1.13 API change | ✅ Fixed | Response parser handles both list and nested dict formats |
| Binary rpaths after install_name_tool | ✅ Fixed | All deps rewritten to @loader_path, codesigned |
| Embedding model download | ⚠ Manual | Installer requires pre-bundled model; HuggingFace blocks curl |
| AutoDream summarization without qwen2.5:7b | ✅ Handled | Falls back to numbered concatenation |
| Gateway exits after config reload | ✅ Fixed | Config reload disabled; launchd KeepAlive with SuccessfulExit=false |

---

## 7. Next Steps (For Future Sessions)

### Immediate (high priority)
1. **Fix installer model download**: Embed model in .dmg or use huggingface_hub Python API instead of curl
2. **Connect a real client**: Configure Cursor or Claude Code to use http://127.0.0.1:3050/mcp
3. **Engranar con src/**: Update MCP Hub Bridge to use this memory stack

### Medium priority
4. **Add qwen2.5:7b for summarization**: Pull via ollama or bundle in engine/
5. **Clean install test**: Wipe ~/.memory, run install.sh from scratch, verify all 39 tools
6. **Add memory cleanup tool**: Prune old/low-confidence memories

### Low priority
7. **Sequential thinking LLM integration**: Currently framework only, needs local LLM for actual reasoning
8. **Multiple model support**: Allow different embedding models per collection
9. **Web dashboard**: Simple UI for browsing memories

---

## 8. Commands Cheat Sheet

```bash
# Start everything from scratch
launchctl start com.memory-server.qdrant
sleep 5
launchctl start com.memory-server.gateway
sleep 10

# Verify
curl -s http://127.0.0.1:6333/collections | python3 -m json.tool
curl -s http://127.0.0.1:3050/health | python3 -m json.tool

# Add a memory
source ~/MCP-servers/memory-server/.venv/bin/activate
cd ~/MCP-servers/memory-server/servers/automem/server
python3 -c "
import asyncio, os
os.environ['MEMORY_SERVER_DIR'] = os.path.expanduser('~/MCP-servers/memory-server')
from main import memorize
asyncio.run(memorize('Important fact', mem_type='fact', importance=0.9))
"

# Browse memories
curl -s http://127.0.0.1:3050/mcp \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $(curl -si http://127.0.0.1:3050/mcp -X POST \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"cli\",\"version\":\"1.0\"}}}' \
    | grep -i mcp-session-id | tr -d '\r' | cut -d' ' -f2)" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"vk-cache_1mcp_request_context","arguments":{"query":"everything","agent_id":"cli","token_budget":8000}}}'
```

---

## 9. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-06 | Router over monolith | Isolation, swap-ability, debuggability, matches existing spec |
| 2026-04-06 | llama.cpp over Ollama | Self-contained, no external service, bundled in engine/ |
| 2026-04-06 | Qdrant native over Docker | No Docker dependency, native performance, launchd auto-start |
| 2026-04-06 | all-MiniLM-L6-v2 (384d) | Small (44MB F16), fast, good quality for general purpose |
| 2026-04-06 | 6-layer memory stack | Matches spec from project_MEMORY-after-A0-(SPECS) |
| 2026-04-06 | Bidirectional protocol | LLM can pull context, system can push reminders |
| 2026-04-06 | Agent-independent daemons | Memory works when LLM disconnects |
| 2026-04-08 | Bundled engine with corrected rpaths | Zero Homebrew dependency, isolated in install dir |
| 2026-04-08 | .dmg with install.sh | Standard macOS distribution, asks for install location |

---

## 10. Session Handoff

When resuming this session, the agent should:

1. Read this file first
2. Verify running services: `launchctl list | grep memory-server`
3. Test engine: `cd ~/MCP-servers/memory-server && source .venv/bin/activate && python3 -c "from shared.embedding import get_embedding; print(len(get_embedding('resume test')))"`
4. Check gateway: `curl -s http://127.0.0.1:3050/health`
5. Continue from "Next Steps" section above

All source code is in:
`/Users/ruben/Code/PROJECT-Memory/project_MEMORY-after-A0/MCP-servers/`

The deliverable .dmg is:
`/Users/ruben/Code/PROJECT-Memory/project_MEMORY-after-A0/MCP-servers/MCP-Memory-Server.dmg`
