# MCP-agent-memory — Exhaustive System Audit

| | |
|---|---|
| **Audit date** | 2026-06-07 |
| **Audited deployment** | `/Users/ruben/MCP-servers/MCP-agent-memory` (live production) |
| **Code snapshot** | `audit/live-snapshot/` (rsync of live `src/`, `scripts/`, `etc/`, `bin/`, taken 2026-06-07 02:24) |
| **Method** | Static analysis of live code + runtime probing of live daemon + cross-verification against logs, state files, and data stores |
| **Auditor** | Claude (Cowork session), under direction of Rubén |

---

## 1. Executive Summary

MCP-agent-memory is a multi-layer persistent memory system ("the Backpack") for AI coding agents. It captures events automatically via editor-plugin hooks, stores them in a layered memory hierarchy (L0 raw → L1 working → L2 episodic → L3 semantic → L4 narrative), and serves retrieval through smart routing (L5) with token budgeting.

**Verdict:** the capture and retrieval halves of the system are healthy and fast (retrieval p95 = 38 ms). The **consolidation half is completely dead since 2026-05-27** due to a refactor that deleted two state-persistence functions while adding noise filtering (Finding F-01). Three additional defects degrade event typing, watchdog coverage, and concurrency resilience.

| Pipeline | Status | Evidence |
|---|---|---|
| Capture (plugin → L0/L1) | **WORKING** | 1,506 events ingested Jun 4–6; 5,298 L1 points in Qdrant |
| Consolidation (L1→L2→L3→L4) | **DEAD since 2026-05-27** | `NameError: name '_load_state' is not defined` on every call; L2=29, L3=5, L4=2 points frozen |
| Retrieval (L5 routing) | **WORKING** | Real context returned, p50=14 ms, p95=38 ms |
| Conversations (L2 SQLite+Qdrant) | **WORKING** | Roundtrip verified; 71 threads |
| Entities / Governance | **WORKING** | 45 entities, 9,850 timeline events |
| Models (bge-m3 :8081, qwen2.5-7b :9000) | **WORKING** | Both probed live, responding |
| Engram sidecar (:3100) | **DOWN** | Connection refused |
| deep-memory MCP (third-party) | **BROKEN** | sqlite-vec extension unsupported by Python build |

---

## 2. Deployment Topology

### 2.1 Two divergent copies of the codebase

| Copy | Path | Git head | Role |
|---|---|---|---|
| **Live** | `~/MCP-servers/MCP-agent-memory` | `c16c2c0` fix(bootstrap) | What actually runs |
| **Workspace** | `~/Code/MCP-agent-memory` | `98a2c25` feat(llm): GBNF grammars | Development copy |

The histories have **diverged**. The live copy is ahead on: noise filtering in consolidation, entity registry exports in `shared/__init__.py`, and the entire `src/governance/` module (absent from the workspace copy). The workspace copy is ahead on: LLM work (Gemma 4 E4B primary connection, dedicated small-LLM port, GBNF grammar support). Neither copy contains the other's changes. **This audit covers the live copy.**

### 2.2 Running processes (launchd-managed)

| Service (launchd label) | Process | Port | Status at audit |
|---|---|---|---|
| `com.agent-memory.backpack-api` | `python3 src/unified/server/backpack.py` | 8890 (HTTP) | Running (PID 1371) |
| `com.agent-memory.qdrant` | `bin/qdrant` | 6333 / 6334 | Running, healthy |
| `com.agent-memory.llama-embedding` | `llama-server --model bge-m3-q8_0.gguf --embedding` | 8081 | Running, verified |
| `com.agent-memory.llama-llm` | `llama-server --model qwen2.5-7b-instruct-Q4_K_M.gguf` | 9000 | Running, verified |
| `com.agent-memory.vault-watcher` | `vault_watcher.sh` → `vault_processor.py` | — | Registered, idle |

Additional MCP stdio processes are spawned per-client: `src/governance/server.py --mcp`, `src/shared/entity_mcp.py`, `engram-memory` (node).

### 2.3 Clients and senders

| Sender | Mechanism | What it sends |
|---|---|---|
| **backpack-orchestrator.ts** (`~/.config/opencode/plugins/`) | OpenCode plugin hooks → `fetch()` → `:8890` | Auto-captured events (user prompts, tool calls, file edits), heartbeats, idle-time `heartbeat-dream`, conversation saves on compaction, context fetch per prompt |
| **browseros-hook.sh** (`bin/`) | Shell wrapper → curl → `:8890` | Manual/external ingestion |
| **MCP clients** (Claude Code, Cowork, etc.) | stdio per `etc/mcp.json` | 53 MCP tools via `unified/server/main.py` |

---

## 3. Architecture: Layers and Modules

### 3.1 Memory layers

| Layer | Name | Physical storage | Written by | Promoted by |
|---|---|---|---|---|
| **L0** | Raw / sensory | `data/L0-sensory/events.jsonl` (append-only) | `ingest_event` | — (audit trail) |
| **L1** | Working | Qdrant `L0_L4_memory` (layer=1) | `ingest_event` (if content > 20 chars or diff) | `_promote_l1_l2` every 10 turns |
| **L2** | Episodic | Qdrant `L0_L4_memory` (layer=2) + `data/L2-episodic/` | consolidation | `_promote_l2_l3` every 3,600 s |
| **L3** | Semantic | Qdrant `L0_L4_memory` (layer=3); decisions as Markdown in vault (`L3_decisions`) | consolidation; `save_decision` | `_promote_l3_l4` every 86,400 s |
| **L4** | Narrative | Qdrant `L0_L4_memory` (layer=4) + `data/L4-narrative/state.json` | consolidation; `dream()` (7-day cooldown) | — |
| **L5** | Routing | — (read-only orchestrator) | — | — |
| **Lx** | Reasoning / persistent | `data/Lx-*` JSON files, vault Markdown | explicit tool calls | — |

### 3.2 Qdrant collections (verified live)

| Collection | Points | Purpose |
|---|---|---|
| `L0_L4_memory` | L1: 5,298 · L2: 29 · L3: 5 · L4: 2 | Layered memory, 1024-dim dense (bge-m3) + BM25 sparse |
| `L2_conversations` | (71 threads mirrored) | Semantic conversation search |
| `L3_facts` | — | Per-user semantic facts CRUD |

The 5,298 : 29 ratio between L1 and L2 is the measured signature of the consolidation stall (F-01).

### 3.3 SQLite databases

| DB | Tables | Purpose |
|---|---|---|
| `data/conversations.db` | `threads`, `messages`, `messages_fts` (FTS5) | Exact conversation storage + full-text search |
| `data/entity_timeline.db` | `entities`, `entity_events`, `entity_milestones`, relations, FTS5 | Entity registry (45 entities), timeline (9,850 events), relations (41) |
| `src/embedding_cache.db` | `embeddings` | Persistent embedding cache (SHA256-keyed) |

### 3.4 Module map (live `src/`)

```
unified/server/main.py      MCP stdio server — loads all 7 modules, 53 tools
unified/server/backpack.py  Standalone HTTP daemon (port 8890) — loads 4 modules:
                            L0_capture, L0_to_L4_consolidation, L5_routing, L2_conversations
shared/api_server.py        stdlib http.server — 8 endpoints, one persistent asyncio loop
shared/retrieval/           smart_retrieve: profiles, scoring, fusion, token packing
shared/embedding.py         HTTP backend → :8081, 2-tier cache (LRU + SQLite), safe_embed zero-vector fallback
shared/llm/                 LLM clients → :9000, graceful degradation
shared/entity_*.py          Entity registry, timeline, relations, vault bridge
shared/sanitize.py          Input validation, event-type whitelist, content cap 100 KB
governance/server.py        Entity lifecycle UI/API, health scoring, 30-day cleanup retention
L0_capture/                 ingest_event, heartbeat (embedding prefetch), memorize
L0_to_L4_consolidation/     heartbeat (promotions), consolidate, dream, verify_stale  ← BROKEN
L5_routing/                 request_context → smart_retrieve
L2_conversations/           save/search conversations (SQLite + Qdrant dual-write)
L3_facts/                   Qdrant-only CRUD
L3_decisions/               Markdown files + vault tools
Lx_reasoning/               Sequential thinking, plans, change sets (template-based, no LLM)
```

---

## 4. Information Flows (what, how, when, why)

### 4.1 Capture flow — WHEN: every user prompt, tool call, file edit

```
OpenCode hook fires (chat.message / tool.execute.after / file edited)
  → backpack-orchestrator.ts backpackPost("/api/ingest-event",
        {event_type: "user_prompt"|"tool_call"|"file_edited", source: "plugin", ...})
       [fire-and-forget, no retry]
  → api_server.py → L0_capture.ingest_event()
      1. validate_ingest_event()      — sanitize, whitelist, 100 KB cap
      2. type_map lookup              — ⚠ F-02: tool_call/user_prompt/file_edited NOT in map
                                         → silently degraded to RawEventType.SYSTEM
      3. _append_raw_jsonl(event)     — L0 audit trail (always)
      4. if len(content) > 20 or diff — MemoryItem → embed (bge-m3) → Qdrant L1
                                         importance: 0.3 default, 0.6–0.7 for diffs
```

WHY: zero-config capture without relying on the LLM to remember to save.

### 4.2 Consolidation flow — WHEN: idle sessions + turn thresholds — **DEAD**

```
Session idle → plugin → POST /api/heartbeat-dream {turn_count}
  → L0_to_L4_consolidation.heartbeat()
      state = _load_state()           ← ✗ F-01: NameError — function deleted in May 27 refactor
      ... never reached:
      _promote_l1_l2  (gate: turn_count ≥ +10; groups L1 by scope, ≥2 items, summarize → L2)
      _promote_l2_l3  (gate: ≥1 h elapsed; episodes → semantic facts, entity extraction → L3)
      _promote_l3_l4  (gate: ≥24 h elapsed; semantic → narrative synthesis → L4)
      _verify_stale   (freshness verification by change_speed half-lives)
      _save_state()   ← ✗ also deleted
```

State file `data/L4-narrative/state.json` frozen at 2026-05-27 22:48 (`total_consolidated: 7`).
The same refactor **added** `_is_noise()` / `NOISE_PREFIXES` (designed to discard junk like
`"edit: Edit applied successfully."`) — the filter is correct but unreachable.

WHY consolidation exists: compress working memory into durable episodic/semantic/narrative
knowledge so retrieval stays relevant as raw events accumulate.

### 4.3 Retrieval flow — WHEN: every user prompt (30 s cooldown) — WORKING

```
User prompt → plugin fetchContext(query) [timeout 3 s, budget 2,000 tokens]
  → POST /api/request-context → L5_routing.request_context()
      → smart_retrieve(query, session_type, token_budget, agent_scope)
          profiles: dev (L1-weighted) | docs (L3/L4-weighted) | default
          sources:  Qdrant layers 1–4 + L2_conversations + L3_facts + L3_decisions (filesystem)
          score = level_weight × vector_score × 0.5 + recency × 0.2 + freshness × 0.3
          packing: RULE_BUDGET 8k / STRUCT_BUDGET 16k / dynamic remainder; 2,048 tokens max per item
  → injection_text → injected into system prompt via system.transform
Enforcement gate: write/edit tools blocked until context fetch attempted for the session.
```

Measured: p50 = 14 ms, p95 = 38 ms, 0/12 over the plugin's 3 s timeout. **Context arrives on time.**

### 4.4 Conversation flow — WHEN: context compaction — WORKING

```
Compaction → plugin → POST /api/save-conversation
  → SQLite upsert (threads + messages + FTS5)   [authoritative]
  → Qdrant upsert (summary embedding, UUID5)    [best-effort, async]
Search: semantic (Qdrant) + FTS5, merged, deduplicated by thread_id.
Scope isolation: agent_scope + "shared" OR-filter.
```

### 4.5 Entity / vault / governance flow — WHEN: explicit MCP tool calls — WORKING

```
entity_register / entity_timeline_append / entity_relation_connect  → entity_timeline.db
vault_entity_bridge → Markdown sync → data/vault/Entidades/
vault_watcher.sh (launchd) → vault_processor.py → serializes vault notes
governance UI (FastAPI): health score = f(events, relations, status, summary, kind);
cleanup marking → 30-day retention → permanent delete
```

### 4.6 Model usage

| Model | Port | Used by | Degradation if down |
|---|---|---|---|
| bge-m3 (embeddings, 1024-dim) | 8081 | Every ingest ≥ 20 chars, every retrieval query, consolidation summaries | `safe_embed()` → zero-vectors: ingestion continues but items become semantically unfindable |
| qwen2.5-7b (LLM) | 9000 | Consolidation `_summarize`, dream synthesis, optional relevance ranking | Structured-summary fallback; ranking skipped; system stays functional |

Note: with consolidation dead, the qwen2.5-7b server is currently almost entirely idle —
it burns RAM for code paths that crash before reaching it.

---

## 5. Trigger & Timing Matrix

| Trigger | Source | Frequency | Action | Status |
|---|---|---|---|---|
| User prompt | plugin hook | every message | ingest `user_prompt` + heartbeat + context fetch (30 s cooldown) | WORKS (type degraded, F-02) |
| Tool call | plugin hook | every call | ingest `tool_call` | WORKS (type degraded, F-02) |
| File edit | plugin hook | every edit | ingest `file_edited` | WORKS (type degraded, F-02) |
| Session idle | plugin hook | on idle | `heartbeat-dream` → consolidation | **CRASHES (F-01)** |
| Context compaction | plugin hook | on compaction | save-conversation | WORKS |
| L1→L2 promotion | heartbeat | every 10 turns | episodes | **DEAD (F-01)** |
| L2→L3 promotion | heartbeat | ≥ 1 h | semantic facts | **DEAD (F-01)** |
| L3→L4 promotion | heartbeat | ≥ 24 h | narratives | **DEAD (F-01)** |
| Dream | manual/idle | 7-day cooldown | cross-layer synthesis | **DEAD (F-01)** |
| Watchdog | cron (intended 5 min) | — | restart unhealthy services | **MISCONFIGURED (F-03)** |
| Lifecycle | cron (intended weekly) | — | JSONL rotation, Qdrant backup | present, not verified as scheduled |

---

## 6. Findings Register

| ID | Severity | Finding | Evidence | Impact |
|---|---|---|---|---|
| **F-01** | **CRITICAL** | `_load_state()` / `_save_state()` called at 8 sites in `L0_to_L4_consolidation/server/main.py` (lines 341, 355, 367, 385, 394, 449, 452, 494) but **never defined**. Deleted by the 2026-05-27 noise-filter refactor; the definitions still exist in the workspace copy (lines 30–36). | Runtime probe: `POST /api/heartbeat-dream` and `POST /api/consolidate` both return `{"error": "name '_load_state' is not defined"}`; 374 heartbeat calls logged with state.json untouched since May 27. | Entire consolidation pipeline dead 11 days. 5,298 L1 items unpromoted. Long-term memory (L2/L3/L4) not forming. Dream never runs. Noise filter unreachable. |
| **F-02** | **HIGH** | `type_map` in `L0_capture/server/main.py:79` lacks `tool_call`, `user_prompt`, `file_edited` — exactly the three types the plugin sends. `type_map.get(x, RawEventType.SYSTEM)` silently degrades them. | JSONL inspection: plugin events arrive `"type": "system"` with the real type relegated to `event_subtype`; control test with `terminal` preserves type correctly. | Event taxonomy lost at the source of 100% of plugin traffic. Importance stuck at 0.3. Downstream ranking, filtering and noise heuristics degraded. |
| **F-03** | **MEDIUM** | `watchdog.sh` restarts `com.agent-memory.gateway`, which does not exist. Real services `backpack-api` and `llama-llm` are not watched. | `grep com.agent-memory scripts/watchdog.sh` vs `launchctl list`. | If the backpack daemon or LLM dies, nothing auto-recovers them. Watchdog silently fails its core purpose for 2 of 5 services. |
| **F-04** | **MEDIUM** | Concurrency loss: 3/40 parallel requests (7.5%) timed out (`Errno 60`). stdlib `http.server` + single persistent asyncio loop serializes async work; plugin client is fire-and-forget with no retry. | Stress battery: 30 parallel ingests + 10 context fetches. | Silent event loss under bursts (multi-agent sessions, fast tool loops). Memory has unrecorded gaps. |
| **F-05** | **LOW** | Contract weaknesses: missing fields → HTTP 500 (should be 400); negative `token_budget` accepted (200). | Fuzz battery. | Misleading diagnostics; benign but unclean. |
| **F-06** | **LOW** | Plugin captures low-value content (`"bash: DONE"`, `"edit: Edit applied successfully."`) with `actor_id: "system"` (never the real actor). The May 27 noise filter targets these strings but is dead (F-01). | JSONL inspection of Jun 4–6 events. | L1 polluted with junk vectors; embedding compute wasted; retrieval noise floor raised. |
| **F-07** | **MEDIUM** | Live and workspace repos have diverged (different heads, governance module only in live, LLM work only in workspace). READMEs outdated (known). | `git log` both copies; `diff -rq`. | Risk of deploying regressions or losing live-only code; F-01 is itself a symptom of uncontrolled deploy flow. |
| **F-08** | **INFO** | Synthetic test data in production store (April events with `session_id: synth-session-*`); audit test data added Jun 7 (sources `audit-*`, `fuzz`, thread `audit-roundtrip-001`). | JSONL inspection. | Inflates counts; should be purged by lifecycle rotation or manual cleanup. |
| **F-09** | **INFO** | Engram sidecar (:3100) down; `deep-memory` MCP broken (Python lacks sqlite-vec extension support). Both are independent of the Backpack core. | MCP probes. | Engram features unavailable to plugin (it degrades gracefully); deep-memory unusable. |
| **F-10** | **INFO** | Orphan/dead code: `unified/server/main_http.py`, `unified/server/gateway.py` unused; L3_facts/L3_decisions/Lx_reasoning have MCP tools but no HTTP endpoints (by design in backpack, undocumented). | Static analysis. | Maintenance confusion; the watchdog "gateway" name (F-03) likely stems from the abandoned gateway module. |
| **F-11** | **CRITICAL** | **Zero-vector plague in L1** (discovered 2026-06-07 by the panel's S9 sensor): 216 of 300 sampled L1 points (72%) carry an all-zero embedding — `safe_embed()`'s silent fallback (P3) has been firing chronically, with zero-vector dates spread across May 11 → June 6 (peaks on heavy-capture days, consistent with F-04 burst timeouts against :8081). | Direct Qdrant scroll with vectors, cross-verified twice (150-sample and 300-sample). | ~72% of working memory is semantically invisible: those points can never match a query by meaning. Retrieval quality silently amputated. Requires a re-embedding backfill (REMEDIATION_PLAN Phase 2-bis) plus marking/queueing failed embeds instead of storing zeros. |

---

## 7. Remediation Plan (prioritized)

| # | Fix | Addresses | Effort | Risk |
|---|---|---|---|---|
| 1 | Restore `_load_state()` / `_save_state()` in live consolidation module (port the 7-line definitions from the workspace copy, keep the live noise filter). Restart backpack. Run `consolidate` to drain the 5,298-item backlog. | F-01 | ~15 min | Low — additive restore |
| 2 | Add `tool_call`, `user_prompt`, `file_edited` to `type_map` (map to `AGENT_ACTION` / new enum values as appropriate); raise importance for `user_prompt`. | F-02 | ~30 min | Low |
| 3 | Fix watchdog service names (`gateway` → `backpack-api`); add `llama-llm` watch. | F-03 | ~10 min | Low |
| 4 | Unify the two repos: merge live-only commits (governance, noise filter) and workspace-only commits (LLM work) into one history; make the live deployment a checkout of it. Add a deploy script or CI gate that runs `python -m py_compile` + smoke test before restart. | F-07, prevents F-01 recurrence | 2–4 h | Medium |
| 5 | Concurrency: queue ingests (accept fast, process async) or move api_server to a threaded loop pool; add minimal retry (1 retry, 500 ms) to plugin `backpackPost`. | F-04 | 2–3 h | Medium |
| 6 | Return 400 for missing fields; clamp `token_budget ≥ 0`. | F-05 | ~20 min | Low |
| 7 | Move noise filtering to ingest time (reuse `_is_noise` before Qdrant write); send real `actor_id` from plugin. | F-06 | ~1 h | Low |
| 8 | Purge synthetic + audit test data (`synth-session-*`, `audit-*`, `fuzz`, `audit-roundtrip-001`); document lifecycle cron installation. | F-08 | ~30 min | Low |
| 9 | Repair or retire Engram and deep-memory integrations. | F-09 | separate track | — |

A pre-fix snapshot of `data/` exists at `~/MCP-servers/backups/data-snapshot-20260607-022144.tar.gz`.

---

## 8. Code Map & Permeability Analysis

Exact code units behind each stage (verified against `audit/live-snapshot/`). Interactive version: `audit/flow-map.html` — clicking a code zone illuminates every stage it permeates.

### 8.1 Code units per stage

| Stage | Code unit | Location |
|---|---|---|
| Plugin hooks | `chat.message` / `tool.execute.after` / idle / `fetchContext()` | `backpack-orchestrator.ts:359–385, 459–475, 330–344, 171–196` |
| HTTP intake | `_ApiHandler.do_POST` / `_run_async()` / `_verify_memories()` | `shared/api_server.py:211–310, 202–209, 42–199` |
| Boundary defense | `validate_*` / `sanitize_text` | `shared/sanitize.py:274, 659, 697, 714` |
| Capture | `ingest_event()` / `type_map` / `_append_raw_jsonl()` / `_store_memory()` / `memorize()` / `heartbeat()` | `L0_capture/server/main.py:76–94, 79–81, 52–58, 32–50, 60–74, 98–119` |
| Consolidation | `heartbeat()` / `consolidate()` / `_promote_l1_l2/_l2_l3/_l3_l4` / `_verify_stale()` / `_is_noise()` / `_summarize()` / `dream()` | `L0_to_L4_consolidation/server/main.py:339, 365, 117–232, 234–337, 55–69, 92–116, 390–458` — **`_load_state`/`_save_state` called at 341, 355, 367, 385, 394, 449, 452, 494 but undefined (F-01)** |
| Retrieval | `request_context()` / `retrieve()` / `_retrieve_L3_decisions()` / `_rank_and_fuse()` / `_pack_context()` / scoring | `L5_routing/server/main.py:28–37`; `shared/retrieval/__init__.py:170–228, 281–308, 309–350, 425–485, 351–424` |
| Embeddings | `get_embedding()` / `safe_embed()` / cache | `shared/embedding.py:645, 737–755`; `shared/embedding_cache.py:42–78` |
| Vector store client | `QdrantClient` (3× retry, payload validation) | `shared/qdrant_client.py:47–310` |
| Conversations | `save_conversation()` / `save_thread()` / `search_fts()` | `L2_conversations/server/main.py:36–93`; `shared/conversation_db.py:137–196, 255–320` |
| Entities / governance | `EntityRegistry` / `EntityTimeline` / `compute_health()` | `shared/entity_registry.py:52`; `shared/entity_timeline.py:24`; `governance/server.py:59–99` |
| Ops | module loader / watchdog | `unified/server/backpack.py:39–97`; `scripts/watchdog.sh:73–117` |

### 8.2 Permeability and contamination points

| # | Zone | Type | Assessment |
|---|---|---|---|
| P1 | `sanitize.py` shared gate | Convergence (clean) | All flows pass one fuzz-verified defense. Single point of failure by design. Its whitelist accepts types that `type_map` then drops — the F-02 seam lies between these two units. |
| P2 | `type_map` (L0_capture:79) | **Contamination** | Silent `.get()` fallback collapses 3 event types into `system`; scope grouping in `_promote_l1_l2` would then merge unrelated events into shared episodes. |
| P3 | `safe_embed()` (embedding.py:737) | **Contamination** | Permeates every flow. On embedding-server failure it stores unmarked zero-vectors — permanent, invisible poisoning of the vector space; the shared cache can freeze the poison. |
| P4 | `QdrantClient` + single collection `L0_L4_memory` | High permeability | All tiers + test + synthetic data share one collection, separated only by payload fields. A mis-tagged write is a tier escape (F-08 adjacency). |
| P5 | `_rank_and_fuse()` (retrieval:309) | Mixing chamber (by design) | Every source fuses into one ranked pack, including fixed-score 0.6 filesystem hits and freshness metadata maintained by dead code (F-01). Upstream contamination (P2, P3) exits to the LLM here. |
| P6 | `_run_async()` (api_server:202) | Temporal coupling | One asyncio loop serializes all flows — latency cross-contamination and the measured 7.5% burst loss (F-04). |
| P7 | `_load_state` call sites (consolidation) | **Severed channel** | The only write-path from working memory to long-term layers is cut (F-01) — the inverse of contamination: permeability that should exist and does not. |

---

## 9. What Works Well (credit where due)

- **Retrieval latency** is excellent (p50 14 ms) — context injection consistently beats the plugin's 3 s timeout.
- **Graceful degradation** is well designed: zero-vector embedding fallback, LLM-optional summarization, SQLite-authoritative conversation writes with best-effort Qdrant mirroring.
- **Input hygiene** is solid: sanitization, type whitelist, 100 KB content cap, control-character stripping (verified by fuzzing).
- **Scope isolation** (agent_scope + shared) is consistently applied across Qdrant filters and SQLite.
- **The enforcement gate** (write/edit blocked until context fetched) is a genuinely clever "right moment" mechanism.
