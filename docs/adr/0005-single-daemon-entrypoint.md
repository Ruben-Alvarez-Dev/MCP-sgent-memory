# ADR-0005 — Single daemon entrypoint: `backpack.py` owns `:8890`

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: the 2026-07-12 architect/backend audit found four overlapping entrypoints — `unified/server/main.py`, `backpack.py`, `main_http.py`, `gateway.py` — with module loading duplicated three times across them; `gateway.py` additionally requires an undeclared `aiohttp` dependency and contains dead code (`docs/plan/IMPROVEMENT-PLAN.md` §2.2, P1 finding, backend/architect). This is exactly the kind of entrypoint sprawl ADR-0007's target architecture (`runtime/` as the *one* composition root) is designed to eliminate.

## Decision

**`backpack.py` becomes the sole owner of port `:8890`.** It is the single composition root shared with the stdio MCP entrypoint (ADR-0007 `runtime/` layer): one place that wires ports to adapters, loads configuration, and starts the HTTP sidecar. `main_http.py` and `gateway.py` are deleted or absorbed into `backpack.py`/`runtime/` — whichever preserves behavior that is still needed; anything neither test-covered nor referenced by a spec is deleted, not carried forward silently.

This ADR records the **decision only**. Implementation is out of scope here and is tracked as the `composition-root` OpenSpec change opening Phase 3 (plan §4, "Phase 3" and §3.5 "Production standards"), which must itemize what each of the three retired entrypoints uniquely does before deleting it, per the strangler migration rule in ADR-0007.

## Consequences

(+) Kills the 3× duplicated module-loading logic and the undeclared `aiohttp` dependency in one move. (+) One process, one port, one place to observe (`/v1/health` reports per-subsystem status per plan §3.5) — no ambiguity about which entrypoint is "the real one" in production or in docs. (+) Directly unblocks ADR-0008's control-plane requirement of "one API, two thin clients" over a single FastAPI sidecar. (−) Requires careful audit of `main_http.py`/`gateway.py` before deletion so no in-use behavior is silently dropped — that audit and its test coverage is a `composition-root` task, not assumed here. (−) Until `composition-root` lands, the four-entrypoint state persists; this ADR does not itself change runtime behavior.
- **Related**: ADR-0007 (hexagonal architecture, `runtime/` composition root, strangler migration), ADR-0008 (control plane consuming the single sidecar this ADR consolidates onto).
