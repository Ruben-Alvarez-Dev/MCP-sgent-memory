# Tasks — adaptive-model-tier

- [ ] 1. `HardwareProfile` pydantic model + darwin/linux probes (sysctl / /proc, stdlib only)
- [ ] 2. Backend reachability checks (ollama /api/tags, llama_server /health, llama_cpp binary+gguf presence) with short timeouts
- [ ] 3. `TierResolver.resolve()` — thresholds T0-T4 + role→model map + env overrides
- [ ] 4. TTL cache + `force_refresh()`; reactive hook: `notify_backend_failure(backend)` → re-probe + downgrade
- [ ] 5. Atomic persistence `data/system/hardware-profile.json` + diff detection → log + L0 system event
- [ ] 6. Wire: `_ensure_initialized` (startup), heartbeat piggyback (periodic), `health_check` (fresh), LLM/embedding factories (consume map)
- [ ] 7. MCP tool `model_tier_status` + sidecar `GET /api/model-tier`
- [ ] 8. Task→model→outcome instrumentation (JSONL under data/system/)
- [ ] 9. Unit tests (tests/core/test_model_tier.py): boundaries, overrides, downgrade, no-services
- [ ] 10. Spec delta: `openspec/specs/model-stack/spec.md` + JSON Schema committed
