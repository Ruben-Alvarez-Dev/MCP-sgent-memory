# The Backpack — Explained for Real

> Last Updated: 2026-05-03
> Status: HONEST DOCUMENT — shows what works AND what doesn't

---

## 1. What is The Backpack?

Imagine you're a programmer who works all day. You have an assistant who:
- Listens to everything you say
- Notes every decision you make
- Reminds you what you did yesterday, last week, last month
- ALERTS you if you're about to make a mistake

**That's The Backpack.** A memory system for AI-powered programming assistants (agents).

It's not a chatbot. It's the **memory** of the chatbot.

---

## 2. The System Pieces

```
┌─────────────────────────────────────────────────┐
│                    YOU                           │
│           (Ruben, the programmer)                │
│                                                  │
│              ┌──────────┐                        │
│              │ OpenCode │  ← Your AI-enabled IDE │
│              └─────┬────┘                        │
│                    │                             │
└────────────────────┼────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│              CLI-agent-memory                    │
│         (The tractor — directs everything)       │
│                                                  │
│   ┌──────────────────────────────────────┐       │
│   │     MCP-agent-memory                 │       │
│   │     (The engine — 53 tools)          │       │
│   │                                      │       │
│   │  ┌──────────┐  ┌──────────┐         │       │
│   │  │L0_capture│  │L0_to_L4_ │         │       │
│   │  │(events)  │  │consolida-│         │       │
│   │  │          │  │tion      │         │       │
│   │  └──────────┘  └──────────┘         │       │
│   │  ┌──────────┐  ┌──────────┐         │       │
│   │  │L5_routing│  │L3_facts  │         │       │
│   │  │(intelli- │  │(semantic │         │       │
│   │  │gent      │  │memories) │         │       │
│   │  │search)   │  │          │         │       │
│   │  └──────────┘  └──────────┘         │       │
│   │  ┌──────────┐  ┌──────────┐         │       │
│   │  │L3_decisi-│  │L2_conver-│         │       │
│   │  │ons       │  │sations   │         │       │
│   │  │(decision  │  │(threads) │         │       │
│   │  │+vault)   │  │          │         │       │
│   │  └──────────┘  └──────────┘         │       │
│   │  ┌──────────┐                       │       │
│   │  │Lx_reason-│                       │       │
│   │  │ing       │                       │       │
│   │  │(reasoning)│                      │       │
│   │  └──────────┘                       │       │
│   └──────────────────────────────────────┘       │
│                                                  │
│   ┌──────────────────────────────────────┐       │
│   │  backpack-orchestrator (plugin)      │       │
│   │  (Automates everything possible)     │       │
│   └──────────────────────────────────────┘       │
│                                                  │
└─────────────────────────────────────────────────┘
```

### What does each piece do?

| Piece | Function | REAL Status |
|-------|---------|-------------|
| **L0_capture** | Captures events, heartbeats, working memory | ✅ Works |
| **L0_to_L4_consolidation** | Consolidates memories, dreams, promotes between layers | ✅ Works |
| **L5_routing** | Intelligent search with ranking and freshness | ⚠️ Partial — Qdrant down |
| **L3_facts** | Semantic CRUD of memories | ⚠️ Depends on Qdrant |
| **L3_decisions** | Architecture decisions + Obsidian vault | ✅ Works |
| **L2_conversations** | Saves conversation threads | ❌ BROKEN — ISSUE-002 |
| **Lx_reasoning** | Reasoning chains | ✅ Works |
| **backpack-orchestrator** | Automates everything via hooks | ✅ Works (gates off) |

---

## 3. The Memory Layers

```
  TIME ──→

  L0           L1            L2           L3          L4
  RAW ────→ WORKING ────→ EPISODIC ──→ SEMANTIC ──→ CONSOLIDATED
  (raw)      (work)      (episodes)   (concepts)  (summaries)

  "git       "fixed      "Debugging  "Decision:  "v1.5 shipped
   commit    bug in      session     use SQLite   with 6 security
   abc123"   auth.py"    auth.py"    for conv."   gates"

  Every 1    Every 5     Every 1h     Every night  Permanent
  second     minutes
```

### REAL status of each layer

| Layer | Storage | Status |
|------|---------|--------|
| L0 Raw | JSONL (flat file) | ✅ Works — 3600+ events |
| L1 Working | Qdrant | ⚠️ Qdrant down |
| L2 Episodic | Qdrant | ⚠️ Qdrant down |
| L3 Semantic | Qdrant | ⚠️ Qdrant down |
| L4 Consolidated | Qdrant | ⚠️ Qdrant down |

**Problem: Layers L1-L4 all use the same Qdrant. If Qdrant goes down, everything goes down.**
**Decision: Separate. L0→JSONL, L1/L2→SQLite, L3/L4→Qdrant.**

---

## 4. What Really Works

```
  ┌─────────────────────────────────────────────┐
  │           ✅ WORKS (verified)                 │
  │                                              │
  │  • Event capture (raw_events.jsonl)          │
  │  • Automatic heartbeats                      │
  │  • Engram decisions + vault                  │
  │  • Sequential thinking                       │
  │  • Backpack hooks (auto-capture)             │
  │  • Sidecar HTTP (port 8890)                  │
  │  • Code gates (when active)                  │
  │  • Event ingest (user_prompt/tool_call)      │
  └─────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────┐
  │           ⚠️ PARTIAL (conditional)            │
  │                                              │
  │  • L5_routing search (if Qdrant is alive)    │
  │  • L3_facts CRUD (if Qdrant is alive)        │
  │  • Context injection (if L5_routing works)   │
  │  • Freshness scoring (exists, no data)       │
  │  • Background verification (hook exists,     │
  │    but consolidate ≠ verify)                 │
  └─────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────┐
  │           ❌ DOESN'T WORK                    │
  │                                              │
  │  • L2_conversations (ISSUE-002)              │
  │  • Entity graph (ISSUE-005)                  │
  │  • Timeline backbone (ISSUE-006)             │
  │  • Relationships (ISSUE-005)                 │
  │  • Integration tests (ISSUE-003)             │
  │  • Anything touching Qdrant                 │
  │    (ISSUE-001)                               │
  └─────────────────────────────────────────────┘
```

---

## 5. The Issues (Real Problems)

```
  FIX PRIORITY:

  1. ISSUE-001  Qdrant down          ┐
  2. ISSUE-002  Conversations broken  │ First — without this
  3. ISSUE-004  Storage by layers     ┘ nothing else works
  4. ISSUE-003  Tests are mocks     ── After — know the truth
  5. ISSUE-006  Timeline backbone    ┐
  6. ISSUE-005  Entities + Relations │─ The guiding thread
  7. ISSUE-009  Complete conversations┘
  8. ISSUE-008  VK Cache Quantization ┐ Future
  9. ISSUE-010  Agent Hive            ┘
```

---

## 6. How We Know If Something Works

### TODAY: We don't know
- Tests are mocks → always green
- Qdrant down → nobody notices
- Conversation_store fails → silent error

### TOMORROW (what we need):

```
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ SMOKE    │    │INTEGRA-  │    │  UNIT    │
  │ TEST     │    │ TION     │    │  TEST    │
  │          │    │ TEST     │    │  (mocks) │
  │ Alive?   │    │ Complete  │    │ Logic    │
  │          │    │ cycle?    │    │ ok?      │
  │ ping     │    │ save→     │    │ function │
  │ Qdrant   │    │ search→   │    │ isolated │
  │ ping     │    │ retrieve  │    │          │
  │ SQLite   │    │          │    │          │
  │ ping     │    │ REAL     │    │          │
  │ API      │    │ SERVICES  │    │          │
  └──────────┘    └──────────┘    └──────────┘
      30s             5min            1min
   On start        On deploy       On commit
```

---

## 7. The Path (Roadmap)

```
  WE'RE HERE                          WE'RE GOING
       │                                    │
       ▼                                    ▼
  v1.5 (gates)  →  v1.5.1  →  v1.6  →  v1.6.1  →  v1.7  →  v2.0
  (done)         (conv     (VK      (timeline   (ctx    (hive
                 integrated)cache)   backbone)  monitor) agents)

                 ISSUE-002  ISSUE-008  ISSUE-006          ISSUE-010
                 ISSUE-004             ISSUE-005
```

---

## 8. The Truth About Tests

```
  WHAT WE HAVE:                      WHAT IT LOOKS LIKE:

  mock_client = AsyncMock()          80 tests ✅✅✅
  mock_client.put = AsyncMock()
  test: assert mock.called           ALL GREEN!

  → Doesn't touch real Qdrant         → "Perfect" system
  → Doesn't touch real files          → False confidence
  → Doesn't touch real network
  → The mock ALWAYS returns OK

  WHAT WE NEED:

  qdrant = QdrantClient(REAL_URL)
  qdrant.upsert(REAL_DATA)
  result = qdrant.search(REAL_QUERY)
  assert result != []
  → Fails if Qdrant is down           ← THAT'S a real test
```

---

## 9. State of the Art Research (Summary)

From research conducted on 2026-04-27, key findings:

| Approach | What it does | Applicable? |
|---------|--------------|-------------|
| **Claude Code Hooks** | PreToolUse blocks with exit code 2 | ✅ We already have this (backpack gates) |
| **CRAG** | Trained evaluator scoring → corrective action | ✅ Applicable to memory |
| **Self-RAG** | Reflection tokens: IsRel, IsSup, IsUse | ✅ Memory verification tokens |
| **Chain-of-Verification** | Draft → plan verification → execute independently | ✅ Verify memories independently |
| **TMS (Truth Maintenance)** | Dependency graph + justification tracking | ✅ EACH memory needs justification |
| **Agent-as-Judge (2026)** | Judge with tools that verifies against sources | ✅ Judge that executes MCP tools |
| **FreshQA** | Classify facts by change speed | ✅ We already have change_speed (v1.4) |
| **Promptfoo MCP Proxy** | Red teaming against MCP servers | ✅ Test our 53 tools |
| **FActScore** | Decompose into atomic facts, verify each one | ✅ Verify memories atomically |

**Main finding: No system exists that combines code enforcement + continuous verification + 53 MCP tools. What we're building is new.**

---

*Living document. Update every time something is fixed or an issue is found.*
*Honesty is the system's first tool.*
