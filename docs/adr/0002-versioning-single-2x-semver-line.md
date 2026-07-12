# ADR-0002 — Versioning: single 2.x SemVer line, hive renumbered v3.0.0

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: version identity crisis found by the 2026-07-12 audit (`docs/plan/IMPROVEMENT-PLAN.md` §1, headline finding 4): git tags reach `v2.0.0`, `pyproject.toml` declares `2.1.0`, README calls "v2.0" current, and `docs/ROADMAP.md` calls "v2.0" a future milestone (the agent hive). No `CHANGELOG.md` exists and no rule ties ROADMAP items to release numbers.

## Decision

1. **One SemVer 2.0 line, 2.x, going forward.** `pyproject.toml` is the single source of truth for the current version; git tags and README/ROADMAP mentions must match it.
2. **ROADMAP phases renumbered as releases** (plan §1 and §4):

   | Phase | Content | Release |
   |-------|---------|---------|
   | Phase 2 | Data integrity (12 P0 bugfix batch) | **v2.2.0** |
   | Phase 3 | Full conversation serialization (ROADMAP v1.5.1) | **v2.3.0** |
   | Phase 3-bis | Control plane: auto-started Web + TUI (ADR-0008) | **v2.3.5** |
   | Phase 4 | Timeline backbone (ROADMAP v1.6.1) | **v2.4.0** |
   | Phase 5 | Embedding pipeline upgrade (ROADMAP v1.8) | **v2.5.0** |
   | Phase 6 | Agent hive (ROADMAP v2.0, absorbing v1.6 KV-cache research) | **v3.0.0** |

3. **The agent hive is renumbered from ROADMAP's "v2.0" to v3.0.0.** It is a bounded-context change (multi-agent coordination, session trees, agent registry) large enough to warrant a major bump, and keeping it inside the 2.x line would collide with the already-issued `v2.0.0`/`v2.1.0` tags.
4. `CHANGELOG.md` (Keep a Changelog 1.1) is reconstructed once from tags `v1.0.0`→`v2.1.0`, then maintained per release from `v2.2.0` on (plan §3.2, §3.5).

## Consequences

(+) Ends the tag/`pyproject.toml`/README/ROADMAP disagreement with one authoritative source; every future release has an unambiguous number tied to a phase and a change set. (+) `docs/ROADMAP.md` becomes a thin index pointing at change proposals + release targets (plan §3.3), no longer a second source of version claims. (−) Existing external references to ROADMAP's "v2.0" (hive) must be understood as v3.0.0 from this ADR forward — flagged wherever it recurs in older docs rather than silently reinterpreted.
- **Related**: ADR-0001 (baseline), ADR-0003 (OpenSpec change→release mapping).
