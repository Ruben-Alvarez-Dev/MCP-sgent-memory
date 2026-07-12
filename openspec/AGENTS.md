# AGENTS.md — Binding verification protocol (Rubén's rules)

> These rules OVERRIDE convenience. Violating them invalidates the work, even if tests pass. They apply to every agent (orchestrator and subagents) in every session.

## 1. Absolute realness — no mockups, no demos, no fakes, no lies

- Nothing simulated outside `tests/`: no mocks, stubs, fakes, canned/demo data, placeholder implementations, or hardcoded "sample" responses in production code paths.
- Never claim something works without executable proof (see §3). If it cannot be proven, report it as **UNVERIFIED** — explicitly, in those terms. Presenting unverified work as working is the worst possible failure, worse than reporting a blocker.
- No silent degradation: every fallback must log loudly and surface in `health_check`/result payloads.

## 2. Dual validation — two different sources, always

No assumption is actionable until validated by **two independent sources**. "I remember", "it should", "typically" are not sources. Valid source pairs (examples):

| Claim type | Source 1 | Source 2 |
|---|---|---|
| Code behavior | reading the actual code | executing it (test/REPL/command) |
| API/tool syntax | official docs | live probe against the real endpoint |
| Model availability | registry/docs (HF, Ollama library) | `GET /api/tags` on the target machine |
| Data shape | schema/spec file | real sample read from storage |
| Bug diagnosis | reproducing it | locating the causal line(s) in code |
| Machine capability | probe command output | `shared/model_tier.py` resolver profile |

Both sources must be named in the evidence (§3). If the two sources disagree → stop, report the discrepancy, do not proceed on either.

## 3. TDD with unequivocal proof of success

Every step follows red → green → refactor:

1. Write the failing test FIRST. Capture the **red** run (command + output).
2. Implement the minimum to pass. Capture the **green** run (targeted test, then full `tests/core` once per change, then `ruff check`).
3. Proof = verbatim command + exit code + output pasted into the evidence file — never a paraphrase like "tests pass". Machine, date and git HEAD included.

Evidence lives at `openspec/changes/<id>/evidence/I<NN>.md` and is committed with the iteration.

## 4. Numbered, controlled, granular iterations (OpenSpec)

- Work advances ONLY as numbered iterations `I01, I02, …` inside an approved `openspec/changes/<id>/`, mapping 1:1 to its `tasks.md` items (split tasks if an iteration isn't the smallest verifiable unit).
- Iteration Definition of Done: red evidence → green evidence → ruff clean → assumptions dual-validated (§2) → evidence file written → granular English commit referencing `[<change-id>/I<NN>]` → `tasks.md` box ticked.
- No iteration may start while the previous one is not DONE. No code outside an iteration. Changes archive into `openspec/specs/` only when all iterations are DONE.

## 5. Reporting

Per iteration, report to Rubén (in Spanish) exactly one line: `I<NN> <change-id> — <qué se probó> — VERDE (evidencia: <ruta>)` or the failure with cause. No verbose narration. Any deviation from this protocol must be flagged, never hidden.
