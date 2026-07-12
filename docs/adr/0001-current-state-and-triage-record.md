# ADR-0001 — Current-state & triage record (2026-07-12 audit baseline)

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: four specialist audits (architect, backend, database, testing — read-only) ran against the working tree at commit `c16c2c0` (+5 uncommitted files) and found that the repo no longer tells the truth about itself: a plugin the README depends on is missing, the embedding pipeline silently corrupts data, a save path reports success on failure, versioning is inconsistent, and nothing runs the test suite automatically. Full detail: `docs/plan/IMPROVEMENT-PLAN.md` §2 ("Consolidated Audit Findings"), which this ADR treats as source material, not something to re-derive.

## Decision — record the baseline, exempt Phase 0 from spec-driven gating

1. **12 P0 findings** (data loss, corruption, or broken truth) are accepted as the triage baseline for all subsequent work:

   | # | Finding | Owner |
   |---|---------|-------|
   | P0-1 | `backpack-orchestrator.ts` plugin absent from repo; README install step broken | architect |
   | P0-2 | Embedding truncation: text >200 chars embedded from first 200 chars only | database |
   | P0-3 | Embedding cache keyed without model/dimension; model swap serves stale vectors | database |
   | P0-4 | `safe_embed` persists `[0.0]*1024` zero-vectors on failure | database |
   | P0-5 | L2 conversations: Qdrant failures swallowed, `status="saved"` returned regardless | backend |
   | P0-6 | Qdrant writes never `raise_for_status()`; collection dimension never validated | database |
   | P0-7 | Logging tree broken: only `"agent-memory"` root configured; L2/shared loggers lost | backend |
   | P0-8 | Uncommitted Ollama migration incoherent: `LLM_BACKEND=ollama` rejected at runtime | backend |
   | P0-9 | `_verify_stale` inert: status always overwritten, `vector=None` upsert, bad filter syntax | backend |
   | P0-10 | Vault re-serialization loop: `is_serialized()` regex never matches, infinite renames | database |
   | P0-11 | `bootstrap.sh` diagnostics lie: warning counter never increments, wrong error attribution | architect |
   | P0-12 | No CI, no gates; `tests/app/` skips silently when services are down | testing |

   P1 (architecture/reliability debt) and P2 (hygiene) findings are likewise accepted as recorded in plan §2.2/§2.3 and drive Phase 1+ change proposals; they are not repeated here.

2. **Phase 0 spec-less exemption**: `docs/plan/IMPROVEMENT-PLAN.md` §4 "Phase 0" explicitly allows triage/local-recovery items (0.1–0.6: OllamaBackend, `_verify_stale` fixes, committing the 5 modified files, `bootstrap.sh` fixes, deleting `VAULT_PATCHES.json`/`etc/`, README truth pass) to land without an `openspec/changes/` proposal, on the grounds that OpenSpec did not exist yet and these are recovery of already-broken behavior, not new capability. This ADR is the retroactive record of that one-time exemption. It sets no precedent: from Phase 1 onward every change goes through OpenSpec (ADR-0003).

## Consequences

(+) One immutable reference point for "what was wrong and why" — later specs/ADRs cite this instead of re-auditing the repo (binding per `openspec/AGENTS.md` §2 dual-validation: this document is the first of the two independent sources for any P0-derived claim). (+) Makes the Phase 0 exemption explicit and bounded instead of an implicit precedent. (−) This record goes stale as P0s close; it is not updated in place (MADR: superseded, not edited) — closure status lives in `openspec/changes/*/tasks.md` and `docs/plan/IMPROVEMENT-PLAN.md` Phase 2, not here.
