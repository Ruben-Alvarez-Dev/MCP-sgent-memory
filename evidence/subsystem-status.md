# Subsystem Status Table

| Piece | State | Evidence | Notes |
|-------|-------|----------|-------|
| Gateway unified | OK | `src/unified/server/main.py:229` | 54 tools registered, 7/7 modules load |
| Identity boot (M4) | OK | `src/shared/identity.py:147-183` | fail-closed, constant-time token verify |
| Scope isolation (ISO-05/11) | OK | `src/shared/memory_db.py:119-165` | SQL WHERE bound params, no post-filter |
| Trunk gate (ISO-16) | OK | `src/shared/memory_db.py:195-215` | approved_by + provenance required |
| L0_capture ingest | OK | `src/L0_capture/server/main.py:95-115` | 4 tools working |
| L1 Working storage | OK | `src/L0_capture/server/main.py:40-70` | upsert to points table |
| L1->L2 promotion | WARN | `src/L0_to_L4_consolidation/server/main.py:88-112` | Code exists, NO TESTS verify it |
| L2->L3 promotion | FAIL | `src/L0_to_L4_consolidation/server/main.py:116-119` | Hardcoded NO-OP, never writes |
| L3->L4 promotion | FAIL | `src/L0_to_L4_consolidation/server/main.py:121-124` | Hardcoded NO-OP, never writes |
| Dream cycle | FAIL | `src/L0_to_L4_consolidation/server/main.py:272-275` | Zero writes, documented M2 decision |
| L2 conversations | OK | `src/L2_conversations/server/main.py:225` | SQLite + FTS5 for threads |
| L3 decisions | OK | `src/L3_decisions/server/main.py:197` | Filesystem markdown, scope-aware |
| L5 routing | OK | `src/L5_routing/server/main.py:202` | But depends on embedding availability |
| Embedding backend | FAIL | `config/.env:4` port 8091; `lsof` -> nothing | Falls back to hash_vector (degraded) |
| LLM model config | WARN | `src/shared/config.py:41` -> field exists | Zero use sites; dead code |
| Classification | OK | `src/shared/llm/config.py:39-159` | Deterministic keyword matcher, <5ms |
| Sanitization | OK | `src/shared/sanitize.py:729` | OWASP-aligned, Unicode-aware |
| Vault manager | OK | `src/shared/vault_manager/__init__.py:826` | Atomic writes, no sync with SQLite |
| API sidecar | OK | `src/shared/api_server.py:381` | ISO-17 token gate when configured |
| Compliance | OK | `src/shared/compliance/__init__.py:273` | Regex/AST checks; semantic=UNVERIFIED |
| Timeline | OK | `src/shared/timeline.py:277` | SQLite + FTS5; not actively used |
| Eval-40 | WARN | `scripts/run_eval.py:265` | R@5=0.425 (degraded mode) |
| Tests | OK | 321 passed / 6 skipped | Adversarial suite 95 passed |
| memory.db data | FAIL | `SELECT COUNT(*) FROM points` -> 0 | DB schema exists but empty |
| events.jsonl | WARN | 2 lines in data/L0-sensory/ | Minimal test data |
| hash_vector | FAIL | cosine diff text = -0.1009 | Actively harmful as fallback |
| FTS5 on points | FAIL | Schema `memory_db.py:55-75` has no FTS5 | Root cause of low code_lookup recall |
| Query expansion | FAIL | `classify_intent` flat keyword matching | No synonyms, no stemming |
| Consolidation tests | WARN | `tests/adversarial/test__M2__consolidation_noop.py` | Only tests NO-OPs, not working path |
