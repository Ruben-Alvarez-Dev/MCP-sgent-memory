# ADR-0006 — 2026 model stack & embedding integrity policy

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: the 2024-era stack (BGE-M3 + qwen2.5-7B + inexistent `qwen3.5:2b` micro) exceeds this machine's RAM budget (5.9 GB resident) and underperforms current 0-12B models. The database audit found embedding-integrity P0s: texts >200 chars embedded truncated, cache keyed without model/dim, zero-vectors persisted on failure. HF review (2026-07-12) identified strictly better per-role models manageable on CPU.
- **Decision — role→model matrix** (defaults for tier T2 "standard"; the tier resolver adapts per machine):

| Role | Model | Why |
|------|-------|-----|
| Embeddings | **Qwen3-Embedding-0.6B** (GGUF) | dim 1024 = drop-in for existing collections; 32k ctx; multilingual ES/EN; corpus empty → free migration window |
| Reranker | **Qwen3-Reranker-0.6B** (alt: bge-reranker-v2-m3; evaluate naver/xprovence for pruning) | replaces fragile prompt-ranking with cross-encoder scores |
| Primary | **Qwen3.5-4B** | ≥ qwen2.5-7B quality at ~½ RAM, ~2× CPU speed; Apache-2.0; multimodal headroom |
| Micro | **Qwen3.5-2B** (alt: MiniCPM5-1B) | verify_stale, entity extraction (JSON via grammar), routing aid |
| Coordinator (T4 only) | long-context Qwen3.5 class | enabled exclusively by tier resolver (v3.0) |

- **Embedding integrity policy** (binding):
  1. Embed full text — never a truncated surrogate (fixes `get_embedding` P0).
  2. Cache key = `sha256(text) + model + dim`; changing model invalidates; eviction policy required.
  3. **Zero-vectors must never be persisted**: embedding failure → typed error → caller stores with `needs_reembedding=true` or rejects.
  4. Startup probe: embed a reference string, assert dimension == config, log backend+model+dim; `health_check` compares against reference vector (cosine > 0.99).
  5. Licenses: prefer Apache-2.0/MIT; CC-BY-NC models (jina-v5, zerank-2) excluded from defaults.
- **Consequences**: (+) ~4.1 GB resident stack, better quality; (+) integrity gates make silent degradation impossible; (−) one-time re-pull of models (`install/pull-models.sh`); (−) old cached vectors invalid — acceptable now (corpus empty), purge script included in `fix-embedding-truncation`.
- **Related**: ADR-0004 (backends), `openspec/changes/adaptive-model-tier/`, ROADMAP v1.8 (absorbed by this ADR + Phase 2 changes).
