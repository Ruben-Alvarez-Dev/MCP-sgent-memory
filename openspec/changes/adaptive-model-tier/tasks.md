# Tasks — adaptive-model-tier

- [x] 1. `HardwareProfile` pydantic model + darwin/linux probes (sysctl / /proc, stdlib only)
      `src/shared/model_tier.py:104-124` (`HardwareProfile(BaseModel)`), `:158-176` (`_darwin_available_gb`, `vm_stat`), `:179-192` (`_linux_meminfo_gb`, `/proc/meminfo`), `:225-264` (`probe_hardware`, stdlib-only: `subprocess`/`os`/`platform`/`re`/`socket`).
- [x] 2. Backend reachability checks (ollama /api/tags, llama_server /health, llama_cpp binary+gguf presence) with short timeouts
      `src/shared/model_tier.py:46` (`REACHABILITY_TIMEOUT = 1.5`), `:269-309` (`_check_ollama`, `_check_llama_server`, `_check_llama_cpp_local`).
- [x] 3. `TierResolver.resolve()` — thresholds T0-T4 + role→model map + env overrides
      `src/shared/model_tier.py:314-340` (`decide_tier`), `:343-400` (`resolve_role_models`, `ROLE_MODEL_<ROLE>` overrides at `:390-398`), `:458-523` (`resolve`/`_build_profile`, `MODEL_TIER` override at `:494-500`).
- [x] 4. TTL cache + `force_refresh()`; reactive hook: `notify_backend_failure(backend)` → re-probe + downgrade
      `src/shared/model_tier.py:458-475` (TTL check in `resolve`), `:527-529` (`force_refresh`), `:531-545` (`maybe_refresh`), `:547-553` (`notify_backend_failure`). Downgrade path verified: `tests/core/test_model_tier.py:208-228` (`test_reactive_downgrade_to_t0`, green).
- [x] 5. Atomic persistence `data/system/hardware-profile.json` + diff detection → log + L0 system event
      `src/shared/model_tier.py:588-610` (`_persist`: tmp-write + `os.replace` at `:606-608`, diff logged at `:600-602`), `:557-573` (`_log_transition` emits L0 event on tier change), `:612-634` (`_emit_l0_event`). Roundtrip verified: `tests/core/test_model_tier.py:257-301`.
- [ ] 6. Wire: `_ensure_initialized` (startup), heartbeat piggyback (periodic), `health_check` (fresh), LLM/embedding factories (consume map)
      PARTIAL — 3 of 4 wiring points confirmed, 1 missing:
      - startup: `src/unified/server/main.py:137-143` (`model_tier.resolve()` in `_ensure_initialized`) — done.
      - heartbeat piggyback: `src/L0_capture/server/main.py:112-118` (`model_tier.maybe_refresh()` inside the `heartbeat` tool) — done.
      - `health_check` fresh re-probe: `src/unified/server/main.py:188-197` (`model_tier.force_refresh()`) — done.
      - LLM/embedding factories "consume map": NOT done. `src/shared/llm/config.py:167-179` (`_resolve_backend_name`) only consumes `preferred_llm_backend()` (backend name `ollama`/`llama_cpp`), never reads `role_models.primary`/`role_models.small` to pick the actual model — `get_llm()`/`get_small_llm()` still source model names from `LLM_MODEL`/`SMALL_LLM_MODEL` env vars only. `src/shared/embedding.py` never imports `shared.model_tier` at all (`grep -n "model_tier" src/shared/embedding.py` → no hits); the embedding model comes solely from the `EMBEDDING_MODEL` env var (`src/shared/embedding.py:50,132-143,308`), ignoring `role_models.embedding` (`qwen3-embedding:0.6b`). Left unchecked — not fabricating completion.
- [x] 7. MCP tool `model_tier_status` + sidecar `GET /api/model-tier`
      `src/unified/server/main.py:206-211` (`model_tier_status` MCP tool), `src/shared/api_server.py:229-236` (`GET /api/model-tier` handler, listed at `:219`).
- [ ] 8. Task→model→outcome instrumentation (JSONL under data/system/)
      NOT done as *wired* instrumentation. The mechanism exists (`src/shared/model_tier.py:636-645`, `record_outcome`, appends `data/system/routing-outcomes.jsonl`) and is exercised only by `tests/core/test_model_tier.py:302-311`. `grep -rn "record_outcome" src` shows zero production call sites (no module under `src/L0_capture`, `src/L0_to_L4_consolidation`, `src/L5_routing`, `src/Lx_reasoning` calls it). Confirmed by absence of the file: `data/system/` contains only `hardware-profile.json`, no `routing-outcomes.jsonl`. The "instrumentation from day one" acceptance criterion in the proposal is not met — the method is dead code outside tests. Left unchecked.
- [x] 9. Unit tests (tests/core/test_model_tier.py): boundaries, overrides, downgrade, no-services
      `tests/core/test_model_tier.py` (312 lines): `TestTierBoundaries` (10 tests), `TestRoleModels` (5), `TestOverrides` (5), `TestCacheAndTriggers` (5), `TestPersistence` (3) — 28 tests, no external services (hardware/backend probes monkeypatched via `_resolver` helper at `:60-69`). Verified green: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_model_tier.py -v` → 28 passed (see evidence/I01.md).
- [x] 10. Spec delta: `openspec/specs/model-stack/spec.md` + JSON Schema committed
      `openspec/specs/model-stack/spec.md` and `openspec/specs/model-stack/hardware-profile.schema.json` both exist and are committed (confirmed via `find`/`cat` on HEAD).
