# ADR-0007 — Target architecture: hexagonal, SOLID, DRY, enterprise-grade

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: the 2026-07-12 audit found: `shared/` mixes domain and infrastructure in a flat package; 4 overlapping entrypoints with module loading duplicated 3×; `register_tools`/`main()` boilerplate copy-pasted across the 7 Lx modules; sidecar coupled to modules via `getattr` string lookups; 95 broad `except Exception`. Rubén mandates: most adequate architecture, SOLID, DRY, best practices, enterprise-grade normalization/standardization, refactoring/componentizing/abstracting as much as possible.

## Decision — target architecture (ports & adapters)

```
src/
├── domain/          # pure logic, zero I/O imports: memory model, consolidation policies,
│                    # ranking/freshness scoring, intent rules, tier policy
├── ports/           # ABCs/Protocols: VectorStore, ThreadStore, VaultStore, EmbeddingBackend,
│                    # LLMBackend, Reranker, EventSink, Clock, HardwareProbe
├── adapters/        # implementations: qdrant/, sqlite/, ollama/, llama_cpp/, fs_vault/,
│                    # http_sidecar/ (FastAPI), mcp/ (tool registration)
├── app/             # use-cases: the 7 Lx modules as thin application services over ports
└── runtime/         # ONE composition root: wiring, config, DI, lifecycle (stdio MCP + daemon)
```

Binding principles:

1. **All I/O behind a port** — no module outside `adapters/` may import httpx/sqlite3/filesystem paths directly. Every policy point (model choice, scoring, thresholds) is injectable.
2. **SOLID**: single responsibility per module; extension via new adapters, never by editing domain; Liskov-clean port contracts (typed, documented, exception taxonomy per port); interface segregation (small ports, no god-interfaces); dependencies point inward (domain imports nothing from app/adapters/runtime).
3. **DRY**: the 7× `register_tools`/`main()` boilerplate collapses into one factory in `runtime/`; `status()` reporting, retry/backoff, atomic-write, and logging setup become shared components; duplication found during any task is extracted, not copied.
4. **Enterprise normalization**: mypy strict on `domain/` and `ports/` (gradual elsewhere); structured JSON logging with correlation ids; typed exception hierarchy rooted per port; validated settings object (pydantic-settings style, no raw `os.getenv` outside runtime); versioned schemas for every persisted artifact; public functions documented; naming conventions enforced by ruff.
5. **Abstraction guardrail** (so "abstract everything possible" stays professional): abstract every I/O boundary, policy point, and anything with ≥2 real or planned implementations; do NOT abstract pure internals with a single consumer — that's speculative complexity, the enemy of SOLID, not its fulfillment.

## Migration strategy — strangler, not big-bang

- Executed as OpenSpec changes with numbered iterations (AGENTS.md protocol), starting Phase 3 with `composition-root` (single entrypoint, kills `main_http.py`/`gateway.py`) and `hexagonal-shared-split` (move `shared/` contents into domain/ports/adapters preserving import shims).
- **Boy-scout rule (binding)**: every change that touches a module migrates that module to the target layout in the same change. No new code outside the target layout from this ADR on.
- Existing strengths preserved: Lx modules already have no cross-imports (keep it: enforced by an import-linter contract in CI, Phase 1).

## Consequences

(+) testability (ports mocked only in tests/), swappable backends (Qdrant→other, Ollama→llama.cpp) with zero domain changes, one place to wire and observe everything. (−) transitional import shims and touch-cost per change (bounded by strangler approach); mypy strict will surface latent type debt (that's the point).
