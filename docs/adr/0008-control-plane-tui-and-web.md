# ADR-0008 — Control plane: auto-started Web dashboard + TUI

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: Rubén requires TUI **and** Web interfaces, started automatically (never manually), to manage every parameter/config/profile and to monitor all relevant metrics with charts. This overrides the old ROADMAP "Not doing: web dashboard" entry (recorded here; plan §"Not Doing" amended).

## Decision

1. **One API, two thin clients (ADR-0007 compliant)**: both UIs are adapters over the same FastAPI sidecar `/v1` (Phase 3). No privileged backdoors — anything the UI does must exist as a versioned, validated endpoint. Domains: config/profiles CRUD (`ConfigService` port: pydantic-validated, audited writes, versioned profiles with per-machine overrides feeding `model_tier` — never raw file edits), metrics read (`MetricsCollector` port: in-proc counters + persisted history), health/tier live view.
2. **Web dashboard**: SPA (Vite + Tailwind — jart standard stack, owner dev-frontend-specialist) served statically by the daemon at `http://127.0.0.1:8890/ui` (localhost-only, same bind policy). Live updates via SSE from `/v1/metrics/stream`; charts self-hosted in the build (no CDN at runtime). Panels: hardware tier + profile live, per-layer memory counts, ingest/consolidation rates, embedding latency + failure/`needs_reembedding` counts, freshness distribution, routing-outcomes explorer (from `data/system/routing-outcomes.jsonl`), thread browser, config/profile editor with validation + diff preview.
3. **TUI**: Python **Textual** (new dependency — sanctioned by this ADR per the no-new-deps rule) as `agent-memory tui` console entrypoint; same `/v1` API client as the web (works against remote machines too); dashboards with textual widgets + sparkline charts; full config/profile management with the same validation path.
4. **Auto-start (the "never manual" requirement)**: the Web UI rides the backpack daemon — one launchd service (`install/launchd/`, `KeepAlive=true`, installed by `app-install.sh`) keeps API+UI permanently up per machine; browser reachable at any time without action. The TUI is interactive by nature: it auto-launches via a provided terminal profile/alias (`amem` command) and connects instantly to the always-up daemon — zero setup at use time. A degraded read-only mode must work even when Qdrant/models are down (T0), showing exactly what is broken.
5. **Scope guard**: UIs contain **zero business logic** — pure presentation + API calls. Any logic temptation goes to `app/` behind the API first.

## Consequences

(+) Single audited config path ends env-file drift; observability becomes first-class (metrics port feeds health, UIs, and future alerting); remote management of the studio Mac from any box. (−) Textual dependency + SPA build step in `install/` (pinned, offline-capable); metrics history storage (SQLite, capped) — sized in the change proposal `control-plane-ui`.
