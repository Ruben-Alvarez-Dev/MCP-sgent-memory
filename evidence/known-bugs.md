# Known Bugs — MCP-agent-memory v2.1.0

## KNOWN-BUG-001: Embedding server not running -> retrieval degraded to hash-vectors
- **Symptom:** R@5 = 0.425; code_lookup R@5 = 0.15
- **Root cause:** `config/.env:4` port 8091; nothing listening (probe: `lsof -i :8091` empty)
- **Owner:** Operational (embedding infra)
- **Severity:** CRITICAL
- **Fix:** Start llama-server, OR remove embedding dependency entirely

## KNOWN-BUG-002: L2->L3 and L3->L4 consolidation is disabled by design (ISO-06)
- **Symptom:** L2, L3, L4 layers remain empty
- **Root cause:** `src/L0_to_L4_consolidation/server/main.py:116-124` hardcoded NO-OPs
- **Owner:** M2-storage (design decision)
- **Severity:** MEDIUM
- **Fix:** Implement L2->L3 (entity extraction) and L3->L4 (cluster summarization) without LLM

## KNOWN-BUG-003: hash_vector produces negative cosine for different text
- **Symptom:** Unrelated text gets penalized in ranking
- **Root cause:** `src/shared/memory_db.py:78-110` deterministic but not semantically meaningful
- **Owner:** M3-retrieval (accepted fallback)
- **Severity:** MEDIUM
- **Fix:** Replace with lexical fallback or fix embedding server

## KNOWN-BUG-004: No FTS5 on points table
- **Symptom:** Retrieval relies 100% on vector similarity
- **Root cause:** `src/shared/memory_db.py:55-75` schema has no FTS5
- **Owner:** M2-storage (omission)
- **Severity:** HIGH
- **Fix:** Add FTS5 to points table with trigger sync

## KNOWN-BUG-005: `llm_model` config field is dead code
- **Symptom:** Config.llm_model set but never read
- **Root cause:** Leftover from pre-M5 codebase
- **Owner:** M5-troncal (incomplete cleanup)
- **Severity:** LOW
- **Fix:** Remove `llm_model` from Config

## KNOWN-BUG-006: No query expansion or synonym support
- **Symptom:** "authentication" query misses "JWT" content
- **Root cause:** `src/shared/llm/config.py` flat keyword matching
- **Owner:** M3-retrieval (out of scope)
- **Severity:** MEDIUM
- **Fix:** Add synonym dictionary + query expansion

## KNOWN-BUG-007: L1->L2 consolidation has no tests
- **Symptom:** Code exists but untested
- **Root cause:** Test suite focuses on NO-OP verification only
- **Owner:** M2-storage (test gap)
- **Severity:** MEDIUM
- **Fix:** Add integration tests for L1->L2 promotion

## KNOWN-BUG-008: Port configuration inconsistency
- **Symptom:** Default 8081 in code, 8091 in .env, mixed in install scripts
- **Root cause:** Multiple authors adjusted ports without standardization
- **Owner:** Operational
- **Severity:** MEDIUM
- **Fix:** Standardize to single port (recommend 8081)
