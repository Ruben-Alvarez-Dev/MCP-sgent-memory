# MCP-agent-memory

> **Persistent multi-layer memory for AI coding agents.**
> 54 MCP tools + HTTP API + auto-trigger plugin + bilingual vault. Zero-config memory that works without the LLM remembering to use it.

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
│  │  AUTO-TRIGGERS:       │    │  54 MCP TOOLS:                   │  │
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
│  │  memory.db (SQLite stdlib, WAL) │ Filesystem (vault/files)  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Storage**: a single `data/memory.db` (SQLite stdlib, WAL mode). No daemons,
no ports, no external vector database. The `MemoryDB` engine enforces scope
filters at the SQL level (`agent_scope` / `user_id` / `layer`, validated via
allowlist), forbids persisted zero-vectors (`NULL` + deterministic hash-vector
instead), boosts lexical matches with sparse vectors (RET-05) and performs
deletes atomically (no TOCTOU window).

### Memory Layers

```
L0 RAW          → Append-only event lake (JSONL)
L1 WORKING      → Steps, facts, hot dialogue (memory.db)
L2 EPISODIC     → Grouped events, incidents (memory.db)
L3 SEMANTIC     → Decisions, entities, patterns (memory.db + filesystem)
L4 CONSOLIDATED → Narratives, deep summaries (memory.db)
L5 SELECTIVE    → Context routing and assembly
```

### What's Automatic vs What Needs Agent Judgment

| Category | Trigger | Examples |
|----------|---------|----------|
| **AUTO** (plugin handles it) | Every user prompt, tool call, file edit, compaction | `L0_capture_ingest_event`, `L0_capture_heartbeat`, `L2_conversations_save`, `L0_to_L4_consolidation_consolidate` |
| **LLM DECIDES** | Agent recognizes a decision, bugfix, or discovery | `L0_capture_memorize`, `L3_decisions_save`, `L5_routing_request_context` |
| **USER ASKS** | Explicit user request | `health_check`, `*_status`, `*_delete_*`, `L3_decisions_search` |

---

## Evaluation

Deterministic retrieval eval over the frozen 40-query set (ES/EN, 5 intents)
against a traceable 38-doc fixture built from this repo:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_eval.py   # writes results YAML
```

Latest run (M5): **Recall@5 = 0.463 · MRR = 0.4767** (hash-vector embeddings,
degraded mode — real embeddings score higher). Evidence:
`openspec/changes/M5-troncal/evidence/eval-40-results-m5.yaml`.

## Module Reference

54 tools, auto-registered from the 7 module servers by the unified
entrypoint (names below are the live registry — regenerated M5):

| Tool | Purpose |
|---|---|
| `L0_capture_heartbeat` | Update agent heartbeat. Call every turn to signal the agent is alive. |
| `L0_capture_ingest_event` | Ingest a raw L0 event (terminal, git, file, system, diff). |
| `L0_capture_memorize` | Store a memory. L0_capture ingests it immediately. |
| `L0_capture_status` | Show L0_capture daemon status — always ON regardless of agent state. |
| `L0_to_L4_consolidation_approve_promotion` | M5-trunk (ISO-06/ISO-16): copy source points into the human-approved |
| `L0_to_L4_consolidation_consolidate` | Run consolidation across all layers. |
| `L0_to_L4_consolidation_dream` | Trigger a deep dream cycle — DISABLED in M2 (ISO-06): no-op, zero writes. |
| `L0_to_L4_consolidation_dream_status` | Check status of a background dream task. |
| `L0_to_L4_consolidation_force_promote` | Force promotion of memories between layers for testing. |
| `L0_to_L4_consolidation_get_consolidated` | Get consolidated memories (L4). |
| `L0_to_L4_consolidation_get_semantic` | Get semantic memories (L3). |
| `L0_to_L4_consolidation_heartbeat` | Signal that the agent is alive. Triggers auto-consolidation if thresholds met. |
| `L0_to_L4_consolidation_status` | Show L0_to_L4_consolidation daemon status. |
| `L2_conversations_get_conversation` | Retrieve a conversation thread by ID. |
| `L2_conversations_list_threads` | List recent conversation threads ordered by last update. |
| `L2_conversations_save_conversation` | Save a conversation thread. |
| `L2_conversations_search_conversations` | Search conversations by semantic similarity + full-text search. |
| `L2_conversations_status` | Show conversation store status. |
| `L3_decisions_delete_decision` | Delete a decision file. |
| `L3_decisions_get_decision` | Get a specific decision by file path. |
| `L3_decisions_get_model_pack` |  |
| `L3_decisions_list_decisions` | List decisions with optional filtering (scoped: own + shared only). |
| `L3_decisions_list_model_packs` |  |
| `L3_decisions_save_decision` | Save an architectural decision as a Markdown file (scoped: non-shared scopes are namespaced). |
| `L3_decisions_search_decisions` | Search decisions by keyword matching (token-based, scoped: own + shared only). |
| `L3_decisions_set_model_pack` |  |
| `L3_decisions_status` |  |
| `L3_decisions_vault_integrity_check` |  |
| `L3_decisions_vault_list_notes` |  |
| `L3_decisions_vault_process_inbox` |  |
| `L3_decisions_vault_read_note` |  |
| `L3_decisions_vault_write` | Write a note to the Obsidian vault. |
| `L3_facts_add_memory` | Add a semantic memory for a user. |
| `L3_facts_delete_memory` | Delete a memory by ID. |
| `L3_facts_get_all_memories` | Get all memories for a user. |
| `L3_facts_search_memory` | Search semantic memories for a user. |
| `L3_facts_status` | Show L3_facts status. |
| `L5_routing_check_reminders` | Check pending context reminders. |
| `L5_routing_detect_context_shift` | Detect if conversation context has shifted domains. |
| `L5_routing_dismiss_reminder` | Dismiss a reminder (scoped: only own + shared namespaces are searched). |
| `L5_routing_push_reminder` | System pushes a context reminder to the LLM. |
| `L5_routing_request_context` | LLM requests context. Returns a ContextPack with smart routing. |
| `L5_routing_status` | Show vk-cache router status. |
| `Lx_reasoning_apply_sandbox` | Apply changes in sandbox mode. |
| `Lx_reasoning_create_plan` | Create an execution plan with steps. |
| `Lx_reasoning_get_thinking_session` | Retrieve a thinking session. |
| `Lx_reasoning_list_thinking_sessions` | List recent thinking sessions. |
| `Lx_reasoning_propose_change_set` | Propose a code change set. |
| `Lx_reasoning_record_thought` | Record a single thought step. |
| `Lx_reasoning_reflect` | Reflect on reasoning quality. |
| `Lx_reasoning_sequential_thinking` | Step-by-step reasoning chain for complex problems. |
| `Lx_reasoning_status` | Show sequential thinking status. |
| `Lx_reasoning_update_plan_step` | Update a plan step status. |
| `health_check` | Check health of all memory subsystems. |

## Directory Structure

```
MCP-servers/agent-memory/
├── bin/                          # launchd scripts: vault processor & watcher
├── etc/                          # Config: .env, mcp.json
├── data/                         # ALL persistent memory
│   ├── memory.db                 # Single SQLite store (stdlib, WAL): points + conversations + facts
│   ├── agents.json               # Agent identity registry (0600, sha256 hashes only)
│   ├── L0-sensory/              # events.jsonl (append-only audit + ingestion fallback)
│   ├── L1-working/              # agents/
│   ├── L4-narrative/            # consolidation-state.json
│   ├── L5-selective/            # reminders/
│   ├── Lx-deliberative/         # sessions/, plans/
│   ├── staging_buffer/
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
├── openspec/                     # Specs + gated milestones M0–M5 (storage, identity, trunk…)
├── scripts/                      # register_agent.py, migrate_to_memory_db.py, ops scripts
├── logs/
├── src/
│   ├── shared/                  # Core library (path-imported; venv-in-repo)
│   │   ├── memory_db.py         # MemoryDB engine: SQLite + WAL, SQL-level scope filters
│   │   ├── identity.py          # M4 identity: registry, verify, strict fail-closed boot
│   │   ├── scope.py             # 5-level namespace c:/p:/a:/s:/u:, FS jail
│   │   ├── retrieval/           # Hybrid retrieval, sparse boost (RET-05)
│   │   ├── api_server.py        # HTTP sidecar :8890 (optional token, ISO-17)
│   │   ├── sanitize.py          # Input validation & XSS protection
│   │   ├── vault_manager/       # Obsidian vault atomic writes
│   │   └── config.py            # Environment configuration
│   ├── unified/server/main.py   # Unified MCP server entrypoint (stdio)
│   ├── L0_capture/              # Auto-capture: memorize, ingest, heartbeat
│   ├── L0_to_L4_consolidation/  # Memory consolidation & dreaming
│   ├── L2_conversations/        # Thread storage & search
│   ├── L3_facts/                # Semantic memory CRUD
│   ├── L3_decisions/            # Vault decisions + Obsidian notes
│   ├── L5_routing/              # Context retrieval + reminders
│   └── Lx_reasoning/            # Sequential thinking + plans
├── tests/                       # core/ (no external services) + adversarial/
├── install/                     # Bootstrap + app-install scripts
├── backups/
└── .venv/
```

> **Legacy (pre-v3.0, historical only)**: the old stack — Qdrant vector DB,
> BGE-M3 embeddings and qwen2.5 served by a compiled llama.cpp engine
> (`bin/qdrant`, `qdrant/`, `engine/`, `models/`) — was retired during the
> memory-zero program (M2/M5). It is no longer part of the architecture.

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
5. Indexes the note in `memory.db`
6. Updates `.system/counter.json`

---

## Retrieval & Ranking

- **Single store**: `data/memory.db` — SQLite (stdlib only, WAL mode). No daemons, no ports.
- **Scope filters at the SQL level**: `agent_scope` / `user_id` / `layer` with an allowlist of filter keys — enforced by the engine, never by Python post-filtering.
- **Sparse boost (RET-05)**: stable lexical sparse vectors boost dense scores at read time (SHA-256 token hashing — process-stable).
- **Zero-vectors prohibited (STO-05)**: failed embeddings persist as `vector=NULL` + `embedded=false`; at query time they are scored against a deterministic hash-vector (`score_source="hash"`).
- **Deterministic ranking**: no micro-LLM in the query path — hard constraint, enforced in code.
- **Atomic deletes**: `delete(id, filter)` runs as a single engine-level operation — no TOCTOU window.
- **Trunk consolidation (M5)**: `merged` is a reserved scope — engine-level writes require human approval + provenance (`approved_by`), ISO-16.

---

## Installation

```bash
# Full install (bootstrap + app configuration)
curl -fsSL https://raw.githubusercontent.com/Ruben-Alvarez-Dev/MCP-agent-memory/main/install.sh | bash

# Custom path
curl -fsSL ... | bash -s -- ~/my-path

# Reconfigure without re-bootstrap (e.g., new MCP client)
bash install.sh --app-only
```

The installer has two phases:
1. **Bootstrap** (`install/bootstrap.sh`) — venv and dependencies (no external services required)
2. **App Install** (`install/app-install.sh`) — config, MCP client setup, verification

Or install from source as a Python package:
```bash
# M5 audit: pip-install is NOT supported (path-based imports, venv-in-repo
# deployment). Use install/bootstrap.sh to create .venv + deps instead.
```

### Post-Install: Enable the Backpack Plugin

For OpenCode users, copy the plugin:

```bash
# plugin lives in its own repo — not bundled here
# cp plugins/backpack-orchestrator.ts ~/.config/opencode/plugins/
```

Then restart OpenCode. The plugin auto-connects to the HTTP API on localhost:8890.

---

## Configuration

### Environment Variables (`config/.env` — see `config/.env.example`)

```env
MEMORY_SERVER_DIR=/path/to/MCP-agent-memory
AUTOMEM_API_PORT=8890              # HTTP sidecar port (default: 8890)

# Identity (M4) — per agent, generated by scripts/register_agent.py
MEMORY_AGENT_ID=director-1
MEMORY_AGENT_TOKEN=<printed once at registration>
MEMORY_IDENTITY_MODE=strict        # open (default, WARN) | strict (fail-closed)
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
        "MEMORY_AGENT_ID": "director-1",
        "MEMORY_AGENT_TOKEN": "<token>",
        "MEMORY_IDENTITY_MODE": "strict"
      }
    }
  }
}
```

---

## Identity & Isolation

Each MCP server instance runs under a **harness-asserted identity** (M4). Register an agent:

```bash
python scripts/register_agent.py --agent-id director-1
```

The CLI prints the credential block to paste into your MCP client config:

```env
MEMORY_AGENT_ID=director-1
MEMORY_AGENT_TOKEN=<printed once>
MEMORY_IDENTITY_MODE=strict
```

- `data/agents.json` — identity registry with `0600` permissions; stores **sha256 hashes only** (the token is never persisted in the file nor logged).
- **Modes**: `open` (default, emits a visible WARN) | `strict` — missing or invalid credentials abort boot before any tool is registered (fail-closed).
- **Scopes**: engine-level filters with filesystem jail and the 5-level namespace `c:x/p:y/a:z/s:w/u:v` (fixed order, levels optional).

---

## HTTP API — Plugin Sidecar

The MCP server exposes a lightweight HTTP API on port 8890 for plugin-to-server communication. This runs in a background thread alongside the MCP stdio server. The sidecar binds to `127.0.0.1` only and supports an **optional bearer token** (ISO-17) that inherits the M4 identity — when configured, tokenless requests are rejected.

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
- **Identity (M4)**: harness-asserted `MEMORY_AGENT_ID`/`MEMORY_AGENT_TOKEN`; registry `data/agents.json` (`0600`, sha256 hashes only); `strict` mode boots fail-closed
- **HTTP API**: localhost only (127.0.0.1), optional bearer token (ISO-17), no network exposure
- **Trunk guard (ISO-16)**: reserved scopes (`merged`) reject engine-level writes lacking human approval + provenance

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
| **v3.0** | **memory-zero (M0–M5)** | Single `memory.db` store (Qdrant retired — legacy only), identity M4, trunk M5, deterministic ranking |

### v2.0 — Descriptive Naming

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
- Launchd services for vault processor and Qdrant watchdog *(legacy — the watchdog was removed together with Qdrant in v3.0)*

### v3.0 — memory-zero (Current)

Architecture program executed in gated milestones (`openspec/changes/M0…M5`):

- **M1 — Isolation**: engine-level scope filters (SQL `WHERE` with bound params, key allowlist), 5-level namespace `c:/p:/a:/s:/u:`, filesystem jail
- **M2 — Storage**: one `data/memory.db` (SQLite stdlib, WAL). **Qdrant demolished** — remains legacy context only; zero-vectors prohibited (`NULL` + deterministic hash-vector); atomic anti-TOCTOU deletes
- **M3 — Retrieval**: sparse lexical boost on the read path (RET-05), deterministic ranking
- **M4 — Identity**: harness-asserted identity, `agents.json` registry (0600, sha256 only), strict fail-closed boot
- **M5 — Trunk**: `merged` scope requires human approval + provenance (ISO-16); hard constraint "no local generation models" enforced in code; sidecar HTTP optional token (ISO-17)

---

## License

MIT
