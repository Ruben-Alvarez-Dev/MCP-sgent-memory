# MCP-agent-memory — Aggressive Testing Report

| | |
|---|---|
| **Date** | 2026-06-07 |
| **Target** | Live production daemon (`localhost:8890`) + Qdrant (:6333) + bge-m3 (:8081) + qwen2.5-7b (:9000) |
| **Authorization** | Live testing and live consolidation trigger explicitly approved by Rubén |
| **Safety** | Pre-test snapshot: `~/MCP-servers/backups/data-snapshot-20260607-022144.tar.gz` (data/, excluding logs) |

---

## 1. Methodology

1. **Service liveness** — process inventory, port probes, health endpoints.
2. **Model verification** — direct inference calls against both llama-server instances.
3. **End-to-end pipeline probes** — one real call per pipeline (ingest, retrieve, save-conversation, verify-memories, consolidate, dream).
4. **Suspicion-driven escalation** — every anomaly drilled until root cause was unequivocal (code line + runtime reproduction + data evidence).
5. **Contract fuzzing** — malformed JSON, empty bodies, missing fields, 5 MB payloads, unicode/null/injection strings, invalid types, negative budgets.
6. **Concurrency stress** — 40 parallel requests (30 ingests + 10 context fetches).
7. **Latency profiling** — 12 sequential `request-context` calls vs the plugin's 3 s timeout.
8. **Data-fidelity checks** — events read back from `events.jsonl`; conversations read back from SQLite.

---

## 2. Test Matrix and Results

### 2.1 Liveness and models

| Test | Result | Detail |
|---|---|---|
| `GET /api/health` | PASS | 7 endpoints advertised |
| Qdrant `/healthz` | PASS | |
| bge-m3 embedding inference | PASS | 1024-dim vector returned |
| qwen2.5-7b chat inference | PASS | Exact-match reply |
| Engram `:3100` | **FAIL** | Connection refused |
| deep-memory MCP `memory_health` | **FAIL** | sqlite-vec extension unsupported |

### 2.2 Pipeline probes

| Test | Result | Detail |
|---|---|---|
| `POST /api/ingest-event` (valid `system`) | PASS | `{"status":"ingested", "layer":"L0_RAW + L1_WORKING"}` |
| `POST /api/request-context` | PASS | Real context, scores 0.51 / 0.37 |
| `POST /api/save-conversation` + SQLite readback | PASS | Thread persisted, FTS row present, 71 threads total |
| `POST /api/verify-memories` (unknown ID) | PASS | Graceful `not found` error handling |
| `POST /api/heartbeat-dream` | **FAIL** | `{"error": "name '_load_state' is not defined"}` |
| `POST /api/consolidate` | **FAIL** | Same NameError — **D-01 reproduced on demand** |

### 2.3 Contract fuzzing

| Input | Expected | Actual | Verdict |
|---|---|---|---|
| Malformed JSON | 400 | 400 `invalid body` | PASS |
| Empty body | 400 | **500** `missing 3 required positional arguments` | WEAK (D-05) |
| Missing fields | 400 | **500** | WEAK (D-05) |
| 5 MB content | reject | 500 `content too long (max 100000)` | PASS (cap enforced) |
| Unicode + emoji + NUL + XSS + SQLi string | sanitize & accept | 200, sanitized | PASS |
| `event_type: "../../etc"` | reject | 500 whitelist error | PASS |
| Empty query (context) | reject | 500 `query cannot be empty` | PASS |
| Negative `token_budget` | reject/clamp | **200 accepted** | WEAK (D-05) |

### 2.4 Performance

| Metric | Value | Threshold | Verdict |
|---|---|---|---|
| `request-context` p50 | 14 ms | < 3,000 ms (plugin timeout) | PASS |
| `request-context` p95 | 38 ms | | PASS |
| `request-context` max | 171 ms | | PASS |
| 40 parallel requests | **37/40 OK** | 40/40 | **FAIL (D-04)** — 3 × `Errno 60` timeouts |

### 2.5 Data fidelity

| Test | Result |
|---|---|
| `terminal` event type preserved in JSONL | PASS (`type: terminal`, `subtype: terminal`) |
| Plugin `tool_call` event type preserved | **FAIL** — stored as `type: system` (D-02) |
| Conversation roundtrip (save → SQLite) | PASS |

---

## 3. Confirmed Defects

### D-01 — Consolidation pipeline dead (CRITICAL)

- **Reproduction:** `curl -X POST :8890/api/consolidate -d '{}'` → `{"error": "name '_load_state' is not defined"}`. Deterministic, 100% of calls.
- **Root cause:** the 2026-05-27 noise-filter refactor of `src/L0_to_L4_consolidation/server/main.py` deleted the `_load_state()` / `_save_state()` definitions while keeping 8 call sites (lines 341, 355, 367, 385, 394, 449, 452, 494). The definitions survive in the workspace copy (`~/Code/.../main.py` lines 30–36).
- **Blast radius (measured):** L1 = 5,298 points vs L2 = 29, L3 = 5, L4 = 2. `state.json` frozen at 2026-05-27 22:48 (`total_consolidated: 7`). Idle-trigger (`heartbeat-dream`), manual `consolidate`, and `dream` all dead. The new noise filter itself is unreachable code.
- **Why it went unnoticed:** the API wraps handler exceptions into HTTP 200-style JSON error bodies; the plugin's calls are fire-and-forget; errors only surface as WARN lines in `backpack.stderr.log`.
- **Fix plan:** restore the two functions (7 lines) in the live file; restart `com.agent-memory.backpack-api`; run staged `consolidate` to drain backlog; verify `state.json` mtime advances and L2/L3/L4 counts grow. Then add a startup self-test (`py_compile` + one dry-run heartbeat) to the launchd wrapper.

### D-02 — Event taxonomy silently degraded (HIGH)

- **Reproduction:** plugin events arrive `"type": "system"`; control ingest with `event_type: "terminal"` stores correctly.
- **Root cause:** `type_map` (`L0_capture/server/main.py:79`) omits `tool_call`, `user_prompt`, `file_edited`; `.get(x, RawEventType.SYSTEM)` hides the gap. The sanitize whitelist accepts these types, so validation passes and degradation is invisible.
- **Impact:** 100% of plugin traffic (1,506 events Jun 4–6) loses its type; importance fixed at 0.3; future type-aware consolidation and ranking neutered.
- **Fix plan:** map the three types explicitly (e.g. `tool_call → AGENT_ACTION`, `user_prompt → new USER_PROMPT` or `IDE_EVENT`, `file_edited → FILE_ACCESS`); add a log WARN when the fallback branch fires; backfill is optional (subtype field preserves truth retroactively).

### D-03 — Watchdog watches a ghost (MEDIUM)

- **Reproduction:** `scripts/watchdog.sh` restarts `com.agent-memory.gateway`; `launchctl list` shows no such service. Real `backpack-api` and `llama-llm` are unwatched.
- **Fix plan:** rename to `backpack-api`, add `llama-llm`; add `--status` output check to lifecycle docs; consider an alert when a restart target is missing.

### D-04 — Event loss under concurrency (MEDIUM)

- **Reproduction:** 40 parallel requests → 3 timeouts (7.5%). Server is stdlib `http.server` with a single persistent asyncio loop; bursts serialize and overflow.
- **Impact:** fire-and-forget plugin means lost events are unrecoverable — silent memory gaps during multi-agent or fast tool-loop sessions.
- **Fix plan:** short-term — plugin retry (1 retry, 500 ms backoff); medium-term — accept-then-queue ingestion (202 + async worker) or migrate api_server to `ThreadingHTTPServer` with a loop pool.

### D-05 — Contract weaknesses (LOW)

- Missing fields → 500 instead of 400; negative `token_budget` accepted. Fix: explicit argument validation before dispatch; clamp budgets.

---

## 4. Residual Test Data (cleanup pending)

| Artifact | Location |
|---|---|
| Events `source: cowork-verification`, `audit-stress` (×30), `fuzz` (×2 accepted) | `data/L0-sensory/events.jsonl` + Qdrant L1 |
| Thread `audit-roundtrip-001` | `conversations.db` + `L2_conversations` |
| Pre-existing synthetic data `synth-session-*` (April) | `events.jsonl` |

Recommend purging together with remediation step 8 (see AUDIT.md §7).

---

## 5. Conclusion

The system's nervous system (capture) and reflexes (retrieval) are healthy and fast; its sleep cycle (consolidation) has been clinically dead for 11 days due to a single bad refactor deployed without a smoke test (D-01), with a second silent defect (D-02) erasing event taxonomy at the front door. Both fixes are small, low-risk, and fully specified above. The deeper structural lesson is F-07 (AUDIT.md): two divergent copies of the codebase with no deploy gate is how a NameError reached production and stayed invisible — the remediation plan addresses the process, not just the bug.
