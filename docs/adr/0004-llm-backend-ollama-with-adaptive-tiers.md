# ADR-0004 — LLM backend: Ollama first, adaptive per machine

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: `config/mcp.json` and `config/.env` were half-migrated to `LLM_BACKEND=ollama`, but `shared/llm/config.py` only accepted `llama_cpp`, raising `ValueError` → all LLM synthesis silently degraded. The dev box is a Hackintosh (Ryzen 5 5600G, 16 GB RAM, RX 570): llama.cpp Metal is unreliable on Polaris and Ollama runs CPU-only on macOS x86 — but it is already installed, running, and serving `bge-m3` + `qwen2.5:7b` on 127.0.0.1:11434. A second machine (Apple Silicon studio Mac) will run the same codebase with different capabilities.
- **Decision**:
  1. Implement `OllamaBackend` (`shared/llm/ollama.py`) as a first-class `LLMBackend`; factory accepts `ollama | llama_cpp`.
  2. Backend/model selection is **not hardcoded per install**: the adaptive model-tier resolver (`shared/model_tier.py`, see `openspec/changes/adaptive-model-tier/`) probes the machine and resolves tier + role→model map. `LLM_BACKEND` env remains as explicit override.
  3. Embeddings keep the existing `http` backend pointed at Ollama's OpenAI-compatible endpoint on this box; `llama_server` remains valid on machines where llama.cpp is compiled.
- **Consequences**: (+) unblocks LLM synthesis today with zero compilation; (+) same repo adapts to Hackintosh/Apple Silicon/CI; (+) `engine/` compilation becomes optional per machine; (−) adds Ollama as runtime dependency where chosen (mitigated: tier resolver degrades to T0 loudly, never silently); (−) two backends to test (covered by resilience suite).
- **Supersedes**: the implicit "llama_cpp only, compiled from source, no Homebrew" stance in README §Engine (README to be amended in Phase 0.6).
