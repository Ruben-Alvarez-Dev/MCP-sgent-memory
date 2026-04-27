# ROADMAP — MCP-agent-memory

> The direction from here. Each release has a clear problem → solution → deliverable.

---

## Where We Came From: v1.3 — Smart Context Injection

**Status**: ✅ Shipped (superseded by v1.4)

v1.2 proved the sidecar pattern. v1.3 closes the loop: Capture → Store → Consolidate → **Retrieve → Inject**. On every user prompt, the plugin fetches relevant context from vk-cache and injects it into the system prompt. The agent starts every conversation aware of relevant past work.

Plus: **code-based enforcement** instead of text rules. The plugin blocks `write`/`edit` tools until memory context has been fetched for the session. No more "please remember to check memory" — it's enforced by code.

**What's proven**:
- `/api/request-context` endpoint proxies vk_cache.request_context via HTTP
- Context injection via `system.transform` hook (two-hook pattern with `chat.message`)
- 30-second cooldown on context fetches, 2000 token budget
- Enforcement gate: `write`/`edit` blocked without context verification
- Graceful degradation: if context fetch fails, agent proceeds after first attempt

**Research foundation**: See `docs/research/verificacion-continua-conocimiento.md` for the scientific basis.

---

## Where We Are: v1.4 — Continuous Knowledge Verification

**Status**: ✅ Shipped

v1.3 gave the agent context from memory. v1.4 makes the agent know **which context to trust**. Every memory now has a verification lifecycle: when it was last verified, how fast the underlying fact changes, and a freshness score that affects ranking. Stale memories get flagged in context injection, and background verification runs during idle time and dream cycles.

**What's proven**:
- `MemoryItem` extended with `verified_at`, `verification_status`, `change_speed`, `verification_source`, `access_count`
- Freshness scoring: `combined = (level_weight × score × 0.5) + (recency × 0.2) + (freshness × 0.3)`
- Freshness decay based on change_speed: never (999999h), slow (720h), fast (48h), realtime (1h)
- Context injection shows freshness tags: `✅ VERIFIED 2h ago`, `⚠️ STALE`, `❓ NEVER VERIFIED`, `🔒 UNVERIFIABLE`
- New endpoint: `POST /api/verify-memories` — verify specific memories or auto-discover stale ones
- Background verification: `session.idle` hook triggers verification of stale memories
- Dream cycle integration: `autodream.consolidate()` runs `_verify_stale()` during each consolidation pass

**Deliverables**:
- [x] Extend `MemoryItem` with `verified_at`, `verification_status`, `change_speed`, `verification_source`
- [x] Freshness scoring: `confidence × decay(change_speed, age)` in smart_retrieve ranking
- [x] Context injection shows freshness tags: `✅ VERIFIED 2h ago`, `⚠️ STALE 5d ago`, `❓ NEVER VERIFIED`
- [x] New endpoint: `POST /api/verify-memories` — verify specific memories against source of truth
- [x] Background verification: `session.idle` hook triggers verification of stale memories
- [x] Dream cycle integration: autodream verifies stale memories during consolidation

**Scientific basis**:
- Reconsolidation (Nader 2000): every recall is a verification opportunity
- Predictive Coding (Friston 2010): verify when prediction error is likely
- FreshQA (Vu 2023): classify facts by change speed — never/slow/fast/realtime
- CRAG (Yan 2024): evaluate retrieval quality, trigger corrective actions
- Metamemoria (Nelson & Narens 1990): dynamic confidence scores updated by verification

**Why this matters**: Without freshness tracking, the context injection from v1.3 can be counterproductive — injecting confident but wrong data. v1.4 ensures the agent knows **which memories to trust** and which need verification.

**Full research**: `docs/research/verificacion-continua-conocimiento.md`

---

## Where We Are Now: v1.5 — Expanded Enforcement

**Status**: ✅ Shipped

v1.4 gave the agent knowledge verification. v1.5 makes the agent **safe**. Six enforcement gates now block the most common agent mistakes before they happen. Each gate is individually configurable via environment variables.

**What's proven**:
- Gate 3: `.env` / secrets protection — blocks write/edit to `.env`, `.pem`, `.key`, `credentials.*`
- Gate 4: Long file read guard — blocks reading large files (>1000 lines) without `offset`/`limit`; verifies actual file size via `Bun.file().stat()` before blocking
- Gate 5: Context spiral prevention — blocks >5 consecutive non-memory tool calls without user interaction
- Gate 6: Blind write prevention — blocks `write`/`edit` without a prior `read` of the same file; paths normalized via `path.resolve()`
- Configurable: each gate can be enabled/disabled via `BACKPACK_GATE_*` env vars
- Memory leak fix: all session state cleaned up on `session.deleted`

**Configuration**:

| Env Var | Default | Controls |
|---------|---------|----------|
| `BACKPACK_GATE_ENV` | `true` | Block edits to .env/secrets files |
| `BACKPACK_GATE_READ` | `true` | Block reading large files without limits |
| `BACKPACK_GATE_SPIRAL` | `true` | Block >5 consecutive tool calls |
| `BACKPACK_GATE_BLIND` | `true` | Block writes without prior read |

**Deliverables**:
- [x] Block: edits to `.env` files (throw error with explanation)
- [x] Block: `read` on large files without `offset`/`limit` (verifies actual size first)
- [x] Block: more than 5 consecutive tool calls without user interaction (excludes memory tools)
- [x] Block: `write` without a prior `read` of the same file (normalized paths)
- [x] Configurable: enable/disable individual rules via env vars
- [x] Fix: memory leak in session tracking state
- [x] Fix: correct `input.args` vs `output.args` per OpenCode API spec
- [x] Fix: path normalization for cross-platform file comparison

---

## Next: v1.5.1 — Full Conversation Serialization

**Status**: 📋 Planned (PREREQUISITE for v1.6.1 Timeline)

**Problem**: Conversations are NOT being saved integrally. `conversation_store` fails silently ("All connection attempts failed"). `raw_events.jsonl` captures isolated events, not full threads. Engram Go captures prompts but not full responses or tool outputs. We are losing the PRIMARY source of truth — the actual conversations.

**Solution**: Every conversation thread must be serialized IN FULL with structured metadata.

**Each message must capture**:
| Field | What |
|-------|------|
| timestamp | When it was said |
| role | user / assistant / system |
| agent | Which agent was active |
| tool | What tool was invoked (if any) + output |
| user | Who (Ruben) |
| machine | Which machine |
| environment | Project, repo, context |
| content | Full text, NEVER truncated |
| summary | Semantic metadata for search |

**Deliverables**:
- [ ] Fix `conversation_store` — stop failing silently
- [ ] Serialize full message threads (not summaries, not samples — COMPLETE)
- [ ] Attach metadata: agent, tool, user, machine, environment per message
- [ ] Storage format: JSONL or SQLite — whatever preserves integrity
- [ ] Selectable: filter by date, project, agent, tool
- [ ] Visible: read any conversation thread in full
- [ ] Permanent: no TTL, no auto-cleanup
- [ ] No space concerns — integrity over compression

**Why this matters**: Without full conversations, the timeline (v1.6.1) has no raw material. Conversations are the events from which entities and relationships are born. Lose the conversation, lose the history.

---

## Next: v1.6 — VK Cache Quantization for Large Context Models

**Status**: 📋 Planned

**Problem**: Qwen 2.5/3.5/3.6 offer 1M token context windows but require KV cache quantization to be practical. Current vk-cache pipeline doesn't account for this. Without quantization, these models OOM on consumer hardware.

**Solution**: Externalize KV cache via vLLM with NVMe offloading. Keep the "hot" portion in RAM, page the "raw memory bucket" to NVMe transparently.

**Why this matters for agents**: A coordinator LLM with 1M context + paginated KV cache can maintain the entity graph actively and orchestrate specialized sub-agents. This is the foundation for the agent hive architecture (v2.0).

**Deliverables**:
- [ ] Research: quantization formats compatible with Qwen 1M context (GPTQ, AWQ, GGUF quirks)
- [ ] PoC: vLLM with KV cache offloading to NVMe
- [ ] Benchmark: RAM usage before/after, latency impact
- [ ] vk-cache pipeline adaptation: serve paginated context to coordinator model
- [ ] Config: NVMe path, hot/cold ratio, page size tunables

---

## Next: v1.6.1 — Timeline Backbone (The Guide Rope)

**Status**: 📋 Planned

**Problem**: We capture 3600+ raw events but they pile up without structure. `MemoryType.ENTITY` and `MemoryType.RELATION` are defined in the enum but have NO logic. `mem_timeline` exists in Engram Go but isn't integrated into our Python pipeline. There is no entity graph, no lifecycle tracking, no temporal ordering that connects events to the entities they affect.

**Solution**: Build the timeline as the backbone — the "guide rope" (cuerda guía) that threads through everything.

**What exists but is dormant**:
- `MemoryType.ENTITY` / `MemoryType.RELATION` — in enum, no logic
- `raw_events.jsonl` — 3600+ events with timestamps, actor_id, session_id — no connections
- `source_event_ids` in MemoryItem — designed for traceability, not populated correctly
- `mem_timeline` — Engram Go tool, not integrated in Python pipeline
- `MemoryScope` (global-core, domain, team, topic, personal, agent, session) — no real semantics

**What needs to be built**:
- [ ] Timeline as backbone: temporal ordering connecting ALL events to entities
- [ ] Entity lifecycle: birth → evolution → death tracking per entity
- [ ] Relationship serialization: bidirectional edges between entities
- [ ] Entity graph: nodes + edges + traversal API
- [ ] Integration: timeline populates entities, entities populate context injection
- [ ] `mem_timeline` bridge: connect Engram Go timeline to Python pipeline

**Why this matters**: Without the timeline, memories are a shapeless pile. The agent can't answer "what happened with X since we last saw it?" because there's no ORDER connecting events. The timeline is the column on which entities and relationships are built.

---

## Where We Are Now: v1.7 — Context Monitor

**Status**: ✅ Shipped

**Problem**: The agent doesn't know when it's running low on context. GSD has `gsd-context-monitor.js` that warns at 35% remaining and does emergency saves at 25%. We can't read context window size from OpenCode plugins (no API for it).

**Solution**: Heuristic token estimation based on message + tool output character counts. When estimated usage crosses thresholds, the plugin auto-saves conversations and injects emergency instructions.

**What's proven**:
- Token estimation: `(char_count × 0.25) + 500` per message/tool output — heuristic, good enough for thresholds
- At 65% used (35% remaining): auto-save conversation + trigger consolidation
- At 75% used (25% remaining): inject `⚠️ WRAP UP NOW` instruction via `system.transform`
- Configurable: `BACKPACK_CONTEXT_WINDOW` (default 200000), thresholds are constants
- Session-scoped: all tracking state cleaned up on `session.deleted`

**Configuration**:

| Env Var | Default | Controls |
|---------|---------|----------|
| `BACKPACK_CONTEXT_WINDOW` | `200000` | Estimated context window size in tokens |

**Deliverables**:
- [x] Track token estimation per session (char heuristic in `chat.message` + `tool.execute.after`)
- [x] Estimate context usage (heuristic: 0.25 tokens/char + 500 tokens/message overhead)
- [x] At estimated 35% remaining: auto-save conversation + auto-consolidate
- [x] At estimated 25% remaining: inject "WRAP UP NOW" instruction via system.transform

---

## Future: v1.8 — Embedding Pipeline Upgrade

**Problem**: BGE-M3 may be falling back to `all-minilm-l6-v2` silently. The embedding pipeline is critical for vector search quality.

**Solution**: Embedding integrity verification + model swap option.

**Deliverables**:
- [ ] Startup verification: embed a known string, check dimensions match config
- [ ] Health check: compare embedding against known reference vector (cosine similarity > 0.99)
- [ ] Support for alternative embedding backends (OpenAI, local Grpcire)
- [ ] Fallback chain: llama_server → openai_api → noop (with explicit logging)

---

## Future: v2.0 — Agent Hive Orchestration

**Problem**: The backpack is designed for a single agent. Multi-agent workflows (SDD orchestrator + subagents) need shared memory. More critically, we need a **coordinator** that can hold the full picture — entity graph, timeline, relationships — while specialized agents do focused work.

**Solution**: Agent hive with a coordinator LLM (1M context, KV cache paginated to NVMe via v1.6).

**Architecture — The Hive**:
```
                    ┌─────────────────────┐
                    │   COORDINATOR (1M)  │  ← Qwen 1M tokens
                    │   Entity Graph      │  ← Timeline backbone (v1.6.1)
                    │   Timeline active   │  ← KV cache hot in RAM
                    └────────┬────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐
        │ Coder     │ │ Tester    │ │ Explorer  │
        │ Sub-agent │ │ Sub-agent │ │ Sub-agent │
        │ L1 own    │ │ L1 own    │ │ L1 own    │
        │ L3/L4 ←→ │ │ L3/L4 ←→ │ │ L3/L4 ←→ │
        └───────────┘ └───────────┘ └───────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────┴────────────┐
                    │  SHARED MEMORY      │
                    │  L3 Semantic        │
                    │  L4 Consolidated    │
                    │  Entity Graph       │
                    └─────────────────────┘
```

**Deliverables**:
- [ ] Agent-scoped memories: each agent has its own L1 but shares L3/L4
- [ ] Cross-agent context injection: orchestrator can pull sub-agent memories
- [ ] Session trees: parent-child session relationships in conversation store
- [ ] Agent registry: track which agents exist, their roles, and capabilities
- [ ] Coordinator prompt: entity graph awareness + delegation logic
- [ ] NVMe-backed KV cache for coordinator (requires v1.6)

---

## Vision: "La Mochila"

```
CLI-agent-memory  ← active orchestration layer (the tractor head)
        │
        ├── MCP-agent-memory  ← passive memory services (53 tools)
        │     ├── automem (events + working memory)
        │     ├── autodream (consolidation + dreams)
        │     ├── vk-cache (smart retrieval + freshness scoring)
        │     ├── conversation-store (threads)
        │     ├── mem0 (semantic CRUD)
        │     ├── engram (decisions + vault)
        │     └── sequential-thinking (reasoning)
        │
        ├── agent-search  ← codebase indexing + semantic search
        │
        └── adapters/  ← CLI-specific integration layers
              ├── opencode/ (TypeScript plugins — backpack-orchestrator + engram)
              ├── claude-code/ (future)
              ├── aider/ (future)
              └── cursor/ (future)
                    │
                      └── backpack-orchestrator
                          ├── Auto-capture every event
                          ├── Auto-heartbeat every turn
                          ├── Auto-save on compaction
                          ├── Auto-consolidate on thresholds
                          ├── Auto-context injection (v1.3)
                          ├── Block writes without context (v1.3)
                          ├── Block bad commits (v1.2)
                          ├── Block .env/secrets edits (v1.5)
                          ├── Block large file reads without limits (v1.5)
                          ├── Block context spirals (v1.5)
                          ├── Block blind writes (v1.5)
                          ├── Context monitor + auto-save (v1.7)
                          └── Background freshness verification (v1.4)
```

The backpack hyperpowers the agent. The agent does the real work (writing code). The backpack makes sure the agent never forgets, never repeats mistakes, always has context, and **knows which context to trust**.

---

## Not Doing (Explicitly Out of Scope)

| Idea | Why Not |
|------|---------|
| Multi-user support | This is a single-developer tool, not a SaaS |
| Web dashboard | The agent is the interface, not a browser |
| Cloud storage | All data stays local (privacy-first) |
| Fine-tuning models | Embedding + vector search is sufficient |
| Real-time collaboration | Single-agent architecture by design |

---

## References That Inform Our Direction

| System / Paper | What We Learned |
|----------------|----------------|
| **GSD** (57K stars) | Hook-based enforcement, wave execution, context monitor |
| **agent-skills** (22.8K stars) | Anti-rationalization tables, verification checklists, red flags |
| **Gentle AI** (not-that-gente-ai) | SDD DAG, blocking rules, self-check protocol, judgment day |
| **Supermemory** (22K stars) | MCP server with built-in memory/recall/context tools |
| **Cognee** (17K stars) | Graph+vector hybrid, lifecycle hooks, 4 APIs |
| **Mem0** (54K stars) | Dominant memory system, mem0-cli for CLI agents |
| **CRAG** (Yan et al. 2024) | Evaluate retrieval quality, trigger corrective actions |
| **Self-RAG** (Asai et al. 2023) | Model learns when to retrieve, critique, generate |
| **FreshQA** (Vu et al. 2023) | Classify facts by change speed, verify accordingly |
| **Reconsolidation** (Nader 2000) | Every recall is a verification opportunity |
| **Predictive Coding** (Friston 2010) | Verify when prediction error is likely |
| **Metamemoria** (Nelson & Narens 1990) | Dynamic confidence scores, know what you know |
