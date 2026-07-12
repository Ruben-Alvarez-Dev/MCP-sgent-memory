# Change: control-plane-ui

- **Status**: approved scope (Rubén, 2026-07-12) — scheduled Phase 3-bis (after FastAPI `/v1` lands) · **ADR**: 0008
- **Owners**: frontend (SPA), backend (API/ports), testing (contract + E2E Playwright/Textual pilot)

## Why

Rubén must manage all parameters, configurations and profiles, and monitor all relevant metrics/charts, from interfaces that are **always up automatically** — TUI and Web — instead of editing env files and running ad-hoc commands.

## What (summary — detailed tasks.md written when Phase 3 opens)

1. Ports: `ConfigService` (validated, audited, versioned profiles; per-machine overrides consumed by `model_tier`) + `MetricsCollector` (counters: ingest/consolidation/embedding latency+failures/`needs_reembedding`/tier changes/routing outcomes; capped SQLite history).
2. API: `/v1/config*`, `/v1/profiles*`, `/v1/metrics`, `/v1/metrics/stream` (SSE), `/v1/threads*` — OpenAPI committed, contract-tested.
3. Web SPA (Vite+Tailwind, served at `:8890/ui` by the daemon, localhost-only, charts bundled offline): tier/hardware live panel, per-layer counts, rates, embedding health, freshness distribution, routing-outcomes explorer, thread browser, config/profile editor with diff preview.
4. TUI (Textual, `amem` entrypoint): same API client, dashboards + sparklines, config/profile management, works remote; instant-on against the always-up daemon.
5. Auto-start: launchd `KeepAlive` service for the daemon (API+UI) installed by `app-install.sh`; degraded read-only mode at T0 showing exactly what's down.

## Acceptance (evidence per AGENTS.md)

- Fresh boot → no manual action → `http://127.0.0.1:8890/ui` serves the dashboard (launchd proof: `launchctl list` + HTTP 200 evidence).
- A profile edit via UI: validated, audited, visible in `GET /v1/config`, picked up by tier resolver without restart (dual validation: API response + resolver profile).
- Metrics charts show real counters moving under a scripted ingest (no fake/demo data anywhere — AGENTS.md §1).
- E2E: Playwright (web) + Textual pilot (TUI) suites green in CI.
