# Change: ollama-backend

- **Status**: approved (Rubén, 2026-07-12) — implementation started
- **Owner**: backend · **Release**: v2.2.0 (pulled forward with Phase 0) · **ADR**: 0004

## Why

`config/.env`/`config/mcp.json` already declare `LLM_BACKEND=ollama` but no `OllamaBackend` exists — `get_llm()` raises `ValueError` and every LLM-dependent path silently degrades (consolidation summaries → truncation, ranking → unranked). Ollama is running on this machine with models pulled; llama.cpp Metal is unreliable on this GPU.

## What

1. `shared/llm/ollama.py`: `OllamaBackend(LLMBackend)` — native `/api/chat` + `/api/generate`, `is_available()` via `/api/tags`, model existence check, `OLLAMA_URL` (default `http://127.0.0.1:11434`), timeouts + typed errors (never swallow).
2. `shared/llm/config.py`: factory accepts `ollama`; when `LLM_BACKEND` unset, consult tier resolver (prefer ollama if reachable, else llama_cpp, else T0 degraded). Same for `get_small_llm` (`SMALL_LLM_MODEL`).
3. Align `config/.env.example` with real keys (`OLLAMA_URL`, `SMALL_LLM_MODEL`, `MODEL_TIER`).
4. Fix latent `_verify_stale` bugs in the uncommitted `L0_to_L4_consolidation/server/main.py` so the file is commit-safe (Qdrant filter syntax, unconditional status overwrite, `vector=None` upsert → payload-only update).

## Acceptance

- With Ollama up: `get_llm().ask("ping")` returns text; consolidation `_summarize` uses LLM (log proves backend=ollama).
- With Ollama down: typed `LLMUnavailableError` propagates to tier resolver → T0; **no silent truncation without a logged downgrade**.
- Unit tests with stubbed httpx transport (no network): chat parse, availability, model-missing error, factory routing.
