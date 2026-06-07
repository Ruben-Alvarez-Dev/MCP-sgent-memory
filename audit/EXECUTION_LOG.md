# Remediation Execution Log — 2026-06-07 (04:23–05:0x local)

Executed per `REMEDIATION_PLAN.md`. All gates machine-verified live.

## Phase 0 — Freeze ✅ (G0 green)
- Snapshot: `~/MCP-servers/backups/data-pre-remediation-20260607-042317.tar.gz` (6.5 MB)
- Code copy: `consolidation-main.py.pre-fix`
- Baseline (`audit/baseline.json`): L1 5,327 · L2 29 · L3 5 · L4 2 · events 9,119 · total_consolidated 7
- Services: backpack, Qdrant, bge-m3, qwen2.5-7b all green.

## Phase 1 — F-01 fix ✅ (G1 green)
- `_load_state()`/`_save_state()` restored into live `L0_to_L4_consolidation/server/main.py`.
- 1.2 `py_compile` OK · 1.3 isolated temp-dir runtime gate OK (state path resolved to temp; load/save verified) · 1.4 daemon restart OK · 1.5 live no-op `heartbeat-dream` → no NameError.
- **`state.json` written 04:25:05 — first state persistence since 2026-05-27.** total_consolidated 7→9 (L2→L3 and L3→L4 timers fired immediately).
- Committed in live repo: `0a1aae5` (note: commit also captured the previously-uncommitted May-27 refactor that was live on disk).

## Phase 2 — Backlog drain ✅ (G2 green) — with one operational incident
- **Incident:** first `consolidate {force:true}` fired through the HTTP API hung the single-loop daemon (listener backlog overflow → port refused; no state corruption — state writes only at completion). Confirms F-04/P6 in production. Recovered via `launchctl kickstart`; capture verified working after recovery.
- **Tactic change:** drain executed OUT-OF-BAND (same module, separate process, same stores) — API stayed live throughout (ctx probes 74–108 ms, HTTP 200).
- Pass 1 (560 s): **“Created 35 episodes (23 noise filtered)”** — the May-27 noise filter working for the first time — plus 50 episodes → 1 semantic memory, and 1 new narrative.
- Post: L2 64 · L3 7 · L4 4 · total_consolidated 11 · turn_count 11.
- Quality gate 2.2: 35 new episodes are coherent per-session LLM summaries; **0/64 episodes contain known junk strings**.
- **Stopped force passes after pass 1 by design:** L1 promotion has no “consumed” marker → repeat force passes risk duplicate episodes. Organic heartbeats (every 10 turns) now continue the drain safely. Dedup marker → Phase 6 backlog.

## Phase 2-bis — F-11 zero-vector re-embed ✅ (gate <2% green)
- Census (full L1 scroll, 5,328 points): **3,795 zero vectors (71.2%)** → `audit/zero-vector-census.json`.
- Re-embed wave 1 (batches of 50): 3,345 fixed in 131 s; 450 failed (HTTP 500 — batch token overflow on the embedding server).
- Wave 2 (batches of 10, 3 retries): +330. Wave 3 (one-by-one): +107.
- **Final S9 scan: 13/5,328 = 0.24% zero vectors (gate <2% PASS).** The 13 残 are deterministic embedding-server failures on long terminal dumps → `audit/toxic-embeddings.json`, deferred to Phase 6 (chunk-before-embed).
- Verification demo: semantic retrieval for a May-era topic now returns 4 sources (top score 0.51).

## Phase 3 — F-02 type_map ✅ (G3 green, ~05:00)
- `tool_call → AGENT_ACTION`, `user_prompt → IDE_EVENT`, `file_edited → FILE_ACCESS` added; fallback branch now logs a WARNING.
- Fidelity probe: all three types preserved end-to-end in JSONL. Live repo commit `055f8ee`.

## Phase 4 — F-03 watchdog ✅ (G4 green) — scope grew, justified
- `watchdog.sh`: ghost `gateway` label → `backpack-api` (2 sites); direct probes added for :8890 and :9000; **state.json staleness alert (>48 h)** — the exact silent symptom of F-01.
- **Discovered during the fire-drill:** `shared/health.py` was also misaligned — probed the abandoned 1MCP gateway on :3050 (2 sites) and filtered `launchctl` output by stale substring `memory-server`, so the launchd check always reported zero services. All fixed; health now 6/6 green (launchd 4/4 core).
- Fire-drill: killed backpack → launchd KeepAlive resurrected it in <2 s (layer 1); watchdog covers hangs (layer 2). Live repo commit `20d5aa0`.

## Phase 5 — F-08 purge ✅ (G5 green, exact arithmetic)
- `events.jsonl`: 9,123 → 8,536 lines (587 test/synthetic purged: audit-*, fuzz, cowork-verification, verificacion-e2e, panel-selftest, cowork-claude, synth-session-*). Race-guarded atomic replace.
- Qdrant L1: 34 test points deleted by scope_id. Conversations: `audit-roundtrip-001` removed from SQLite + `L2_conversations`.
- Post-purge: L1 5,297 · L2 64 · L3 7 · L4 4.

## Phase 7 — Resilience & corpus hygiene quick-wins ✅ (~05:10)
- **Context:** no crontab and no launchd timers existed — watchdog and lifecycle had NEVER run automatically (last Qdrant snapshots: May 3, manual).
- 7.1 `_save_state` now atomic (tmp+rename); verified in isolated gate, daemon healthy after restart.
- 7.2 New `scripts/backup-data.sh`: daily verified tar of data/ (excl. logs), 7-archive retention; first run produced a verified 6.5 MB archive.
- 7.3 Three launchd timers installed and verified firing: `com.agent-memory.watchdog` (every 5 min), `.lifecycle` (Sunday 03:00, `L1_MAX_AGE_DAYS=60`), `.backup` (daily 04:00). Plists versioned in `etc/launchd/`.
- **NEW FINDING F-12 (CRITICAL, latent):** lifecycle's Qdrant purge compared the integer `layer` payload against legacy strings (`'L3_SEMANTIC'`), so L2/L3/L4 were unprotected and everything older than 30 days was deletable. Had lifecycle ever been scheduled, it would have erased consolidated memory monthly. Fixed before scheduling; dry-run gate shows 0 purgable with protections active. Its JSONL rotation also pointed at a nonexistent file (`raw_events.jsonl`) — repointed to `L0-sensory/events.jsonl`.
- Live repo commit `b6b1191`.

## Phase 2-ter — Auxiliary-collection zero-vector sweep ✅ (2026-06-07, later session)
- **Live re-check found the F-11 census incomplete:** it only covered `L0_L4_memory`. Auxiliary collections were never scanned.
- Re-census (live): `L0_L4_memory` 5,372 pts **0 zero-vectors** — the 13 "toxic" items had already been re-embedded organically since the morning run (`toxic-embeddings.json` is now obsolete; chunk-before-embed backlog item can be dropped). But `L2_conversations` **16/22 (72.7%)** and `L3_facts` **1/10** were zero — same chronic `safe_embed` fallback pattern.
- Backup of affected points (payload+vector): `audit/zero-vector-aux-backup.json`.
- Re-embed one-by-one via `POST :8081/v1/embeddings` (newlines stripped — llama-embedding splits on `\n`), vectors written via `PUT /collections/{c}/points/vectors?wait=true` (note: Qdrant 404s on POST to that path).
- **Result: 17/17 re-embedded, 0 failures. Final census: 0 zero-vectors across all three collections.**
- Retrieval probe on a repaired L2 point: self-hit score 1.000, neighbors 0.856/0.829 — episodic search over conversations works again.

## Pending
- Phase 6 (separate session): repo unification + deploy smoke gate, L1 consumed-marker (dedup), `safe_embed` pending-tag semantics, dedicated USER_PROMPT enum, restore-drill runbook, SQLite `PRAGMA integrity_check` in lifecycle. (Chunk-before-embed for the 13 toxic items: no longer needed — see Phase 2-ter.)

## Notable live-fire lessons fed back into the plan
1. Synchronous heavy consolidation through the API takes the whole daemon down (F-04 in production) — consolidation must run out-of-band or queued until Phase 6 re-architecture.
2. Embedding server rejects large batches (n_tokens > batch limit) — collector/backfill must embed in small batches; daemon code embeds one-at-a-time so it was never affected.
3. The live working tree contained an uncommitted refactor — reinforcing Phase 6 (deploy gate).
