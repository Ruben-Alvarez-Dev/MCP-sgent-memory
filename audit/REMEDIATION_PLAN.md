# MCP-agent-memory — Surgical Remediation Plan

| | |
|---|---|
| **Date** | 2026-06-07 |
| **Scope** | Findings F-01…F-08 from `audit/AUDIT.md` / defects D-01…D-05 from `audit/TESTING.md` |
| **Target** | Live deployment `~/MCP-servers/MCP-agent-memory` |
| **Doctrine** | Snapshot-first · one atomic change per step · verification gate after every step · instant rollback path · nothing advances without a green gate |

**A note on "infallible":** no plan is infallible; what this plan guarantees is that **no failure can be silent and no step is irreversible**. Every phase has a pre-verified patch, a machine-checkable gate, and a rollback that restores the exact prior state. The worst possible outcome of any phase is "we rolled back and nothing changed."

**Patch compatibility — pre-verified (2026-06-07):** the live module already contains `import json` (line 9), `_state_path = DREAM_PATH / "state.json"` (line 30), and uses exactly the 7 state keys that the restored functions initialize (`last_promote_l1_l2`, `last_promote_l2_l3`, `last_promote_l3_l4`, `last_dream`, `turn_count`, `total_consolidated`, `total_dreams`). `consolidate(force: bool)` exists in the live code for controlled backlog draining.

---

## Phase 0 — Freeze & Baseline (no mutations)

**Goal:** a complete, restorable picture of "before".

| Step | Action | Command |
|---|---|---|
| 0.1 | Fresh data snapshot (excl. logs) | `tar -czf ~/MCP-servers/backups/data-pre-remediation-$(date +%Y%m%d-%H%M%S).tar.gz -C ~/MCP-servers/MCP-agent-memory --exclude='data/logs' data` |
| 0.2 | Code snapshot of the file under surgery | `cp ~/MCP-servers/MCP-agent-memory/src/L0_to_L4_consolidation/server/main.py ~/MCP-servers/backups/consolidation-main.py.pre-fix` |
| 0.3 | Baseline metrics → save to `audit/baseline.json` | Layer counts via Qdrant `points/count` (L1/L2/L3/L4), `state.json` content + mtime, `wc -l events.jsonl`, log byte offset (`wc -c backpack.stderr.log`) |
| 0.4 | Confirm services green | `curl :8890/api/health`, `curl :6333/healthz`, embedding + LLM probes |

**Gate G0:** snapshot exists and is non-empty (`tar -tzf | head`); all four services respond. ❌ → stop, fix environment first.
**Rollback:** n/a (read-only).

---

## Phase 1 — F-01: Restore the consolidation state functions (THE fix)

**Change (7 lines, additive, after line 31 `_state_path.parent.mkdir(...)`):**

```python
def _load_state() -> dict:
    if _state_path.exists():
        return json.loads(_state_path.read_text())
    return {"last_promote_l1_l2": 0, "last_promote_l2_l3": 0, "last_promote_l3_l4": 0, "last_dream": 0, "turn_count": 0, "total_consolidated": 0, "total_dreams": 0}

def _save_state(state: dict) -> None:
    _state_path.write_text(json.dumps(state, indent=2))
```

Source of truth: workspace copy `~/Code/MCP-agent-memory/src/L0_to_L4_consolidation/server/main.py:30–36` (verified identical key-set to live usage). **Nothing else in the file is touched** — the noise filter and all live-only code stay exactly as they are.

| Step | Action | Gate |
|---|---|---|
| 1.1 | Insert the two functions into the live file | — |
| 1.2 | **Static gate:** `cd ~/MCP-servers/MCP-agent-memory && .venv/bin/python3 -m py_compile src/L0_to_L4_consolidation/server/main.py` | exit 0 |
| 1.3 | **Isolated runtime gate (zero production impact):** run the module against a TEMP copy of the data dir — `MEMORY_SERVER_DIR=$(mktemp -d)` + copy `data/L4-narrative` into it → python one-liner: import module, call `_load_state()`, `_save_state(...)`, assert temp `state.json` written | NameError gone; file written in temp dir only |
| 1.4 | Restart daemon: `launchctl kickstart -k gui/$(id -u)/com.agent-memory.backpack-api` | `curl :8890/api/health` returns 200 within 10 s |
| 1.5 | **Live no-op probe:** `POST /api/heartbeat-dream {"agent_id":"remediation","turn_count":0}` | HTTP 200, **no** `error` key, no NameError in log tail |

**Gate G1:** all of 1.2–1.5 green. ❌ at any point → Rollback: `cp ~/MCP-servers/backups/consolidation-main.py.pre-fix <live path>` + kickstart. Total rollback time < 30 s.

---

## Phase 2 — Controlled backlog drain (5,298 L1 items)

Do **not** fire one giant consolidation blindly. Drain in observed stages:

| Step | Action | Gate |
|---|---|---|
| 2.1 | Dry observation: `POST /api/consolidate {"force": false}` (thresholds decide; turn_count is already 7+374 behind, L2/L3 timers expired long ago) | 200; `results[]` non-empty; `state.json` mtime advances — **first state write since May 27** |
| 2.2 | Verify quality of what was produced: scroll 3 newest L2 episodes; confirm noise filter actually dropped `bash: DONE`-class content | episodes contain signal, not junk |
| 2.3 | If L1 backlog remains large, repeat `consolidate {"force": true}` in max 3 passes, checking layer counts between passes | L2/L3 counts grow monotonically; daemon stays responsive (request-context p95 < 500 ms during drain) |
| 2.4 | Record post-drain metrics into `audit/baseline.json` (after section) | L2 ≥ 30, state.json `total_consolidated` > 7 |

**Gate G2:** consolidation runs end-to-end, state persists, episodes are clean.
**Rollback:** Phase 1 rollback + restore data snapshot 0.1 (only if data corruption is observed — additive writes make this near-impossible).

---

## Phase 2-bis — F-11: Re-embed the zero-vector plague (added 2026-06-07)

The panel's S9 sensor measured **72% of sampled L1 points carrying all-zero embeddings** (chronic `safe_embed()` fallback, dates May 11 → June 6). These memories are semantically invisible.

| Step | Action | Gate |
|---|---|---|
| 2b.1 | Census: scroll ALL L1 points with vectors, build the exact list of zero-vector point IDs + contents → `audit/zero-vector-census.json` | count known precisely |
| 2b.2 | Verify :8081 healthy and returning non-zero vectors (panel sensor green) | embedding probe non-zero |
| 2b.3 | Re-embed in batches of 50 (content → bge-m3 → Qdrant `points/vectors` update; do NOT touch payloads), pausing 1 s between batches; monitor retrieval p95 during the run | each batch: vectors updated ≠ 0; daemon p95 < 500 ms |
| 2b.4 | Re-run S9 scan (300 samples) | zero-vector rate < 2% |
| 2b.5 | Root-cause guard (Phase 6 item): change `safe_embed()` semantics — on failure, tag the point `embedding_status: pending` and enqueue for retry instead of storing zeros; panel alarm already covers regression | code review |

**Rollback:** vector updates are reversible only via snapshot 0.1 — but a re-embedded vector strictly dominates a zero vector, so risk is one-directional. Run AFTER Phase 1-2 (so consolidation sees good vectors).

---

## Phase 3 — F-02: Fix the event-type taxonomy

**Change (single dict literal, `src/L0_capture/server/main.py:79`):** add three mappings —
`"tool_call": RawEventType.AGENT_ACTION, "user_prompt": RawEventType.IDE_EVENT, "file_edited": RawEventType.FILE_ACCESS`
plus one `logger.warning` in the fallback branch so any future unmapped type screams instead of hiding. (Adding a dedicated `USER_PROMPT` enum value is deferred to Phase 6 — enum changes ripple into `shared/models` and deserve the unified repo.)

| Step | Gate |
|---|---|
| 3.1 Edit + `py_compile` | exit 0 |
| 3.2 Kickstart daemon | health 200 |
| 3.3 **Fidelity probe:** ingest one event of each of the 3 types → read back last 3 JSONL lines | `type` field ≠ `system` for all 3; matches expected enums |

**Gate G3:** all three types preserved. ❌ → restore file from git/backup, kickstart. Backfill of historical events is NOT needed: `event_subtype` preserved the truth retroactively.

---

## Phase 4 — F-03: Watchdog watches real services

**Change (`scripts/watchdog.sh`):** replace both `com.agent-memory.gateway` references with `com.agent-memory.backpack-api`; add a `llama-llm` health+restart block mirroring the embedding one.

| Step | Gate |
|---|---|
| 4.1 Edit + `bash -n scripts/watchdog.sh` | syntax OK |
| 4.2 `./scripts/watchdog.sh --status` | reports all 5 real services, no ghost |
| 4.3 Controlled fire-drill: `launchctl kill TERM gui/$(id -u)/com.agent-memory.backpack-api` → run watchdog | watchdog restarts it; health 200 |

**Gate G4:** fire-drill passes. ❌ → restore script from backup (it's also in git history).

---

## Phase 5 — Hygiene: purge test & synthetic data (F-08)

All deletions filter-scoped, never wholesale:

| Step | Action |
|---|---|
| 5.1 | `events.jsonl`: rewrite excluding `source ∈ {audit-stress, fuzz, cowork-verification, verificacion-e2e}` and `session_id LIKE synth-session-%` → write to `.tmp`, `wc -l` diff must equal counted matches, then atomic `mv` |
| 5.2 | Qdrant: `points/delete` by filter on the same sources (collection `L0_L4_memory`) |
| 5.3 | Conversations: delete thread `audit-roundtrip-001` from SQLite + `L2_conversations` point |
| 5.4 | Re-count layers; append to `audit/baseline.json` |

**Gate G5:** deleted counts match pre-counted matches exactly; no other rows changed (`wc -l` arithmetic).
**Rollback:** snapshot 0.1 contains every byte deleted here.

---

## Phase 6 — Structural cure: repo unification + deploy gate (F-07 — prevents recurrence)

This is what makes the fix *stay* fixed. Separate approval, ~2–4 h:

1. In `~/Code/MCP-agent-memory`: create branch `unify/live-2026-06-07`; import live-only deltas as granular commits (governance module, noise filter + restored state functions, entity exports) — each commit 2–4 sentences, English, per house style.
2. Reconcile with workspace-only LLM work (Gemma 4 / GBNF / port split) — review conflicts file by file.
3. Make `~/MCP-servers/MCP-agent-memory` a checkout of the unified branch (or rsync-deploy from it) — **one** source of truth.
4. Add `scripts/smoke.sh` (the launchd wrapper runs it before starting the daemon): `py_compile` over `src/**` + import test of the 4 backpack modules + one no-op heartbeat against a temp dir. **A deleted function can never reach production silently again.**
5. Watchdog addition: alert (log + optional notification) if `state.json` mtime > 48 h — the exact symptom that went unnoticed for 11 days.
6. Optional (F-04/F-05/F-06, same branch): plugin retry (1×, 500 ms), HTTP 400 for missing fields, clamp `token_budget`, noise filter invoked at ingest, real `actor_id` from plugin.

**Gate G6:** smoke.sh green on deploy; one repo; CI-style check documented in README.

---

## Execution & Abort Matrix

| Phase | Risk | Time | Abort consequence |
|---|---|---|---|
| 0 Freeze | none | 5 min | — |
| 1 F-01 fix | low (additive, pre-verified) | 15 min | rollback < 30 s, zero residue |
| 2 Drain | low (additive writes) | 15–30 min | layers keep pre-drain content; snapshot covers all |
| 3 F-02 types | low | 10 min | file restore |
| 4 F-03 watchdog | low | 10 min | script restore |
| 5 Purge | medium (deletions) | 15 min | snapshot 0.1 restores everything |
| 6 Unification | medium (structural) | 2–4 h | branch work — live untouched until final deploy step |

**Sequencing rule:** phases 1→2 are a unit (fix then drain). 3, 4, 5 are independent and can run in any order after G2. 6 is a separate work session.

**Post-remediation watch (48 h):** `state.json` mtime advances on idle sessions; L2/L3/L4 counts grow; no new WARN lines in `backpack.stderr.log`; plugin events arrive with correct types.
