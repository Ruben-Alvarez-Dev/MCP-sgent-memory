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

## Next: v1.5 — Expanded Enforcement

**Problem**: OpenCode doesn't support `additionalContext` like Claude Code. We have 2 enforcement gates (context verification + conventional commits). More patterns need blocking.

**Solution**: Expand the enforcement gate beyond context and commits. Add blocking rules for common agent mistakes.

**Deliverables**:
- [ ] Block: edits to `.env` files (throw error with explanation)
- [ ] Block: `read` on files over 1000 lines without `offset`/`limit` (wastes context)
- [ ] Block: more than 5 consecutive tool calls without user interaction (context spiral)
- [ ] Block: `write` without a prior `read` of the same file (blind edits)
- [ ] Configurable: enable/disable individual rules via env vars

**Reference**: GSD's `gsd-read-guard.js`, `gsd-prompt-guard.js`, `gsd-workflow-guard.js`

---

## Future: v1.6 — Context Monitor

**Problem**: The agent doesn't know when it's running low on context. GSD has `gsd-context-monitor.js` that warns at 35% remaining and does emergency saves at 25%. We can't read context window size from OpenCode plugins (no API for it).

**Solution**: Workaround via session message count estimation. OpenCode's SDK exposes message counts.

**Deliverables**:
- [ ] Track message count per session via `message.updated` events
- [ ] Estimate context usage (heuristic: ~500 tokens per message + tool output)
- [ ] At estimated 35% remaining: auto-save conversation + auto-consolidate
- [ ] At estimated 25% remaining: inject "WRAP UP NOW" instruction via system.transform

---

## Future: v1.6 — Embedding Pipeline Upgrade

**Problem**: BGE-M3 may be falling back to `all-minilm-l6-v2` silently. The embedding pipeline is critical for vector search quality.

**Solution**: Embedding integrity verification + model swap option.

**Deliverables**:
- [ ] Startup verification: embed a known string, check dimensions match config
- [ ] Health check: compare embedding against known reference vector (cosine similarity > 0.99)
- [ ] Support for alternative embedding backends (OpenAI, local Grpcire)
- [ ] Fallback chain: llama_server → openai_api → noop (with explicit logging)

---

## Future: v2.0 — Agent Orchestration

**Problem**: The backpack is designed for a single agent. Multi-agent workflows (SDD orchestrator + subagents) need shared memory.

**Solution**: Scope-aware memory with agent identity.

**Deliverables**:
- [ ] Agent-scoped memories: each agent has its own L1 but shares L3/L4
- [ ] Cross-agent context injection: orchestrator can pull sub-agent memories
- [ ] Session trees: parent-child session relationships in conversation store
- [ ] Agent registry: track which agents exist, their roles, and capabilities

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
                          ├── Block bad commits
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
