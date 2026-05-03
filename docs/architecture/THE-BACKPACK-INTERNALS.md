# The Backpack — HOW IT WORKS INSIDE

  The mechanics. The plumbing. What happens when you write a message.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PART A: THE WIRING — What connects to what

  When you write "fix the auth bug", THIS happens:

  ┌─────────────────────────────────────────────────────┐
  │  OpenCode (AI-enabled editor)                        │
  │                                                     │
  │  1. You type → OpenCode receives the text           │
  │                                                     │
  │  2. OpenCode passes it to the AGENT (gentleman, glm-5.1)│
  │     The agent decides which tools to use            │
  │                                                     │
  │  3. BEFORE executing any tool:                       │
  │     ┌─────────────────────────────┐                 │
  │     │ backpack-orchestrator.ts    │                 │
  │     │ Hook: tool.execute.before   │                 │
  │     │                             │                 │
  │     │ Is write/edit? → Gate 1     │                 │
  │     │ Is .env?        → Gate 3     │                 │
  │     │ Is long file?   → Gate 4     │                 │
  │     │ 6+ tools in a row? → Gate 5  │                 │
  │     │ Writing without reading? → Gate 6│           │
  │     └─────────────────────────────┘                 │
  │     If a gate says BLOCKED → the tool is NOT executed│
  │                                                     │
  │  4. The tool executes (bash, edit, read, MCP...)     │
  │                                                     │
  │  5. AFTER executing:                                │
  │     ┌─────────────────────────────┐                 │
  │     │ backpack-orchestrator.ts    │                 │
  │     │ Hook: tool.execute.after    │                 │
  │     │                             │                 │
  │     │ POST http://127.0.0.1:8890  │                 │
  │     │ /api/ingest-event           │                 │
  │     │ {type:"tool_call",          │                 │
  │     │  content:"bash: git log"}   │                 │
  │     └─────────────────────────────┘                 │
  │     The event goes to sidecar → L0_capture → raw_events│
  │                                                     │
  └─────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PART B: THE MCP — How OpenCode talks to The Backpack

  OpenCode knows nothing about memory. It speaks MCP (Model Context Protocol).

  MCP = a protocol that says:
  - "I have these tools available"
  - "Each tool accepts these parameters"
  - "The result comes in this format"

  Our MCP server has 53 tools organized like this:

  ┌───────────────────────────────────────────────────┐
  │  MCP-agent-memory (single Python process)         │
  │                                                   │
  │  ├── L0_capture (8 tools)                         │
  │  │   ├── memorize        → save something         │
  │  │   ├── ingest_event    → capture event          │
  │  │   ├── heartbeat       → "I'm alive, turn N"    │
  │  │   └── ...                                       │
  │  │                                                │
  │  ├── L0_to_L4_consolidation (5 tools)              │
  │  │   ├── dream           → dream (consolidate)    │
  │  │   ├── consolidate     → force consolidation    │
  │  │   ├── get_semantic    → read L3                │
  │  │   └── get_consolidated→ read L4                │
  │  │                                                │
  │  ├── L5_routing (4 tools)                         │
  │  │   ├── request_context → "give me context for X"│
  │  │   ├── push_reminder   → remind the agent       │
  │  │   ├── check_reminders → are there reminders?   │
  │  │   └── detect_context_shift → did topic change? │
  │  │                                                │
  │  ├── L2_conversations (5 tools)                   │
  │  │   ├── save_conversation                        │
  │  │   ├── get_conversation                         │
  │  │   ├── search_conversations                     │
  │  │   ├── list_threads                             │
  │  │   └── status                                   │
  │  │                                                │
  │  ├── L3_facts (4 tools)                           │
  │  │   ├── add_memory                               │
  │  │   ├── search_memory                            │
  │  │   ├── get_all_memories                         │
  │  │   └── delete_memory                            │
  │  │                                                │
  │  ├── L3_decisions (7 tools)                       │
  │  │   ├── save_decision                            │
  │  │   ├── search_decisions                         │
  │  │   ├── list_decisions                           │
  │  │   ├── vault_write / vault_read                 │
  │  │   └── ...                                      │
  │  │                                                │
  │  └── Lx_reasoning (7 tools)                        │
  │      ├── sequential_thinking                      │
  │      ├── create_plan / update_plan_step           │
  │      ├── propose_change_set                       │
  │      └── ...                                      │
  │                                                   │
  │  Total: ~53 tools                                 │
  │  Transport: stdio (standard input/output)         │
  │  OpenCode launches it as a child process          │
  └───────────────────────────────────────────────────┘

  BUT ALSO there's an HTTP SIDECAR (port 8890):

  ┌───────────────────────────────────────────────────┐
  │  The sidecar runs INSIDE the same MCP process     │
  │                                                   │
  │  The backpack-orchestrator.ts (TypeScript)        │
  │  CANNOT call MCP tools directly.                  │
  │  It calls the sidecar via HTTP.                   │
  │                                                   │
  │  fetch("http://127.0.0.1:8890/api/ingest-event")  │
  │  fetch("http://127.0.0.1:8890/api/heartbeat")     │
  │  fetch("http://127.0.0.1:8890/api/request-context")│
  │  fetch("http://127.0.0.1:8890/api/save-conversation")│
  │                                                   │
  │  The sidecar receives the HTTP and calls the      │
  │  Python function internally. Without going through │
  │  MCP stdio.                                       │
  │                                                   │
  │  WHY: OpenCode hooks are TypeScript.              │
  │  Memory is Python. The bridge is HTTP.            │
  └───────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PART C: STORAGE — Where each thing lives

  TODAY (problematic):

  ┌──────────────┐
  │   Qdrant     │ ← VECTOR DB (semantic search)
  │              │
  │  L0_capture  │    L1 working memory
  │  L3_facts    │    L3 semantic
  │  L2_conversations│  conversations (DON'T BELONG HERE)
  └──────────────┘
  ┌──────────────┐
  │  JSONL file  │ ← raw_events.jsonl
  │              │    L0 raw events
  └──────────────┘
  ┌──────────────┐
  │  filesystem  │ ← L3_decisions Markdown files
  │              │    decisions + vault
  └──────────────┘

  Problem: 3 layers in Qdrant. If it goes down, everything goes down.
  Problem: Conversations are TEXT, not VECTORS.

  TOMORROW (the right way):

  ┌──────────────┐
  │  JSONL       │ ← L0 raw events (append-only)
  └──────────────┘
  ┌──────────────┐
  │  SQLite      │ ← L1/L2 working + episodic
  │              │    COMPLETE conversations
  │              │    Entities, relationships, timeline
  │              │    FTS5 for full-text search
  │              │    ACID, transactions, WAL mode
  └──────────────┘
  ┌──────────────┐
  │  Qdrant      │ ← ONLY L3/L4 semantic + consolidated
  │              │    Only vectors. Only embeddings.
  │              │    No huge payloads.
  └──────────────┘
  ┌──────────────┐
  │  filesystem  │ ← L3_decisions (Markdown, durable)
  └──────────────┘

  SQLite + Qdrant are linked by IDs.
  Timeline lives in SQLite. Embeddings in Qdrant.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PART D: THE GATES — How they protect you

  The backpack-orchestrator has 6 gates. Each one is
  a TypeScript function that runs BEFORE or AFTER a
  tool call. If it throws Error, the tool is NOT executed.

  Gate 1: CONTEXT VERIFICATION (v1.3)
  ────────────────────────────────────
  Did the agent verify context before writing?
  If not → BLOCKED. You can't modify code without
  knowing what memory has about that project.

  Gate 2: CONVENTIONAL COMMITS (v1.2)
  ───────────────────────────────────
  Does the commit message follow type(scope): desc format?
  If not → BLOCKED. "fixed some stuff" doesn't pass.

  Gate 3: .ENV PROTECTION (v1.5)
  ──────────────────────────────
  Are you editing .env, .pem, .key, credentials?
  → BLOCKED. Never touch secrets.

  Gate 4: LONG FILE GUARD (v1.5)
  ──────────────────────────────
  Are you reading a +1000 line file without offset/limit?
  → BLOCKED. First check size, then read in parts.

  Gate 5: CONTEXT SPIRAL (v1.5)
  ─────────────────────────────
  Did you make 6+ tool calls without the user speaking?
  → BLOCKED. You probably entered a loop.

  Gate 6: BLIND WRITE (v1.5)
  ──────────────────────────
  Are you writing a file you didn't read first?
  → BLOCKED. Read first, write after.

  All DISABLED now (defaults inverted).
  Activate with BACKPACK_GATE_*=true in environment.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PART E: WHAT COMES FROM STATE OF THE ART

  We researched 20+ systems and papers. What applies:

  ┌──────────────────────┬─────────────────────────────┐
  │  PATTERN             │  HOW WE APPLY IT            │
  ├──────────────────────┼─────────────────────────────┤
  │                      │                             │
  │  TMS (Truth          │  Each memory saves WHY      │
  │  Maintenance System) │  it exists (justification)  │
  │                      │  If base changes,           │
  │                      │  dependents are re-evaluated│
  │                      │                             │
  │  CRAG (Corrective    │  Relevance scoring →        │
  │  RAG)                │  if low, search more &      │
  │                      │  take corrective action     │
  │                      │                             │
  │  Chain-of-           │  Verify INDEPENDENTLY       │
  │  Verification        │  from original draft        │
  │                      │  Without bias of what you   │
  │                      │  believe                   │
  │                      │                             │
  │  Agent-as-Judge      │  An agent with MCP tools    │
  │  (2026)              │  VERIFIES memories against  │
  │                      │  real sources               │
  │                      │                             │
  │  FreshQA             │  Classify memories by       │
  │                      │  change speed:              │
  │                      │  never/slow/fast/realtime   │
  │                      │  Fast ones verified more    │
  │                      │                             │
  │  PROV-O (W3C)        │  Each memory carries:       │
  │                      │  wasGeneratedBy,            │
  │                      │  wasDerivedFrom,            │
  │                      │  wasRevisionOf              │
  │                      │  Complete lineage           │
  │                      │                             │
  └──────────────────────┴─────────────────────────────┘

  What doesn't exist anywhere:
  → Code-level enforcement at MCP tool call level
  → Continuous memory verification in a 53-tool server
  → Timeline + entities + lifecycle in a memory system for agents
  → What we're building is NEW.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PART F: THE TWO FILES THAT MATTER

  The system is configured in TWO places:

  1. opencode.json (~/config/opencode/opencode.json)
     ├── agents (17, with temperature 0.1)
     ├── providers (Z.AI, LMStudio, Mimo...)
     ├── MCP servers (which to connect)
     └── permissions (what's allowed)

  2. backpack-orchestrator.ts (~/config/opencode/plugins/)
     ├── hooks (chat.message, tool.execute.before/after, etc)
     ├── gates (6 enforcement rules)
     ├── BACKPACK_RULES (injected system prompt)
     └── L3_decisions integration (Go binary for decisions)

  PROBLEM FOUND TODAY:
  → The file in repo (adapters/opencode/) and the running one
    (plugins/) were OUT OF SYNC.
    The repo had v1.2 (538 lines). The running had v1.5 (690).
  → Must synchronize or it will happen again.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PART G: ONE-PAGE SUMMARY

  ┌───────────────────────────────────────────────────┐
  │  THE BACKPACK = Memory for programming agents     │
  │                                                   │
  │  HOW: 53 MCP tools + HTTP sidecar + TS hooks     │
  │                                                   │
  │  WHAT IT CAPTURES: events, decisions, conversations│
  │                                                   │
  │  HOW IT ORGANIZES: L0→L1→L2→L3→L4 (consolidation) │
  │                                                   │
  │  HOW IT SEARCHES: L5_routing (embeddings + ranking)│
  │                                                   │
  │  HOW IT PROTECTS: 6 code gates (block actions)    │
  │                                                   │
  │  WHAT FAILS: Qdrant down, conversations broken,   │
  │              entities asleep, tests = mocks        │
  │                                                   │
  │  NEXT: SQLite for storage + timeline +           │
  │        L5_routing for Qwen 1M + hive agents       │
  │                                                   │
  │  FILES:                                           │
  │  ROADMAP.md → plan by versions                    │
  │  THE-BACKPACK-4-YEARS.md → this explanation       │
  │  THE-BACKPACK-EXPLAINED.md → detailed version     │
  │  L3_decisions/issues/ → open problems             │
  │  L3_decisions/architecture/ → design decisions    │
  │  L3_decisions/golden-rules/ → temperature 0.1 forever│
  └───────────────────────────────────────────────────┘
