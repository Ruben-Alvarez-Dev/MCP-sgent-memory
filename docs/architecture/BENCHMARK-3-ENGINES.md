# Comparative Benchmark: 3 Engines × 20 Tests

**Date:** 2026-04-27
**Machine:** MacBook Pro M1, 32 GB RAM, macOS
**Models:** qwen2.5-7b-instruct (LLM) + bge-m3 / nomic-embed-text (Embeddings)

---

## 1. Test Configuration

| Engine | LLM | Embeddings | LLM Port | EMB Port |
|---|---|---|---|---|
| **llama.cpp** (Metal) | qwen2.5-7b-instruct-Q4_K_M.gguf | bge-m3-q8_0.gguf | 8080 | 8081 |
| **Ollama** | qwen2.5:7b | nomic-embed-text | 11434 | 11434 |
| **LM Studio** | qwen2.5-7b-instruct | text-embedding-nomic-embed-text-v1.5 | 1234 | 1234 |

All use the same base model (Qwen 2.5 7B instruct) in GGUF format.
Embeddings: bge-m3 (1024-dim) vs nomic-embed-text (768-dim) — different families.

---

## 2. LLM Results (10 tests per engine)

### 2.1 Latency and Throughput

| Test | Description | llama.cpp | Ollama | LM Studio |
|---|---|---|---|---|
| LLM-01 | Simple ES response | **364ms** (19.3 t/s) | 17,458ms (0.4 t/s) | 17,811ms (0.4 t/s) |
| LLM-02 | Summary | **1,639ms** (42.7 t/s) | 1,738ms (40.9 t/s) | 1,747ms (41.8 t/s) |
| LLM-03 | Python code | **2,697ms** (49.7 t/s) | 4,193ms (47.7 t/s) | 4,198ms (47.6 t/s) |
| LLM-04 | Forced JSON | **1,609ms** (49.7 t/s) | 1,929ms (42.0 t/s) | 1,788ms (45.3 t/s) |
| LLM-05 | Long input (737 tok) | **312ms** (48.0 t/s) | 1,832ms (9.3 t/s) | 1,974ms (8.6 t/s) |
| LLM-06 | Long generation (256 tok) | **5,193ms** (49.3 t/s) | 5,287ms (48.4 t/s) | 5,310ms (48.2 t/s) |
| LLM-07 | Logical reasoning | **3,020ms** (49.7 t/s) | 3,214ms (46.7 t/s) | 3,201ms (46.9 t/s) |
| LLM-08 | Consistency (3×, temp=0) | **231ms** ✅ identical | 298ms ✅ identical | 242ms ✅ identical |
| LLM-09 | Intent classification | **71ms** ✅ correct | 255ms ✅ correct | 203ms ✅ correct |
| LLM-10 | Benchmark 10× avg | **31.8 tok/s** (σ=0.3) | 22.1 tok/s (σ=1.6) | 28.5 tok/s (σ=2.4) |

### 2.2 LLM Findings

- **Cold start**: llama.cpp 48× faster (364ms vs 17,458ms). Ollama and LM Studio load model on demand.
- **Long input**: llama.cpp 6× faster (312ms vs 1,832ms). Other engines process input more slowly.
- **Warm generation**: comparable across all three (~48 tok/s for long generation).
- **Quality**: identical across all three (same base Qwen 2.5 7B model).
- **Consistency**: all three produce identical results with temp=0.
- **Classification**: all three correctly classify as `decision_recall`.

---

## 3. Embedding Results (10 tests per engine)

### 3.1 Latency and Quality

| Test | Description | bge-m3 (llama.cpp) | nomic (Ollama) | nomic-v1.5 (LM Studio) |
|---|---|---|---|---|
| EMB-01 | Basic ("Hello world") | **47ms**, dim=1024 | 13,278ms, dim=768 | 11,138ms, dim=768 |
| EMB-02 | High similarity (ES) | **cos=0.8043**, 27ms | cos=0.7543, 178ms | cos=0.6554, 106ms |
| EMB-03 | Low similarity | **cos=0.5314**, 43ms | cos=0.7222, 37ms | cos=0.5796, 22ms |
| EMB-04 | Cross-lingual EN→ES | **cos=0.9186**, 39ms | cos=0.4418, 49ms | cos=0.5838, 18ms |
| EMB-05 | Single word | **19ms** | 38ms | 91ms |
| EMB-06 | Long text (~300 words) | **58ms** | 99ms | 140ms |
| EMB-07 | Empty text | **15ms** ✅ | 34ms ✅ | 8ms ✅ |
| EMB-08 | Batch 5 texts | 90ms (18ms/t) | 83ms (17ms/t) | **34ms** (7ms/t) |
| EMB-09 | Benchmark 20× avg | 33.3/s (30ms) | 51.5/s (19ms) | **96.8/s** (10ms) |
| EMB-10 | Determinism (3×) | **✅ 1.000000** | **✅ 1.000000** | ❌ NOT deterministic |

### 3.2 Semantic Gap (key metric for search quality)

| Model | High Similarity | Low Similarity | Gap | Cross-lingual |
|---|---|---|---|---|
| **bge-m3** | 0.8043 | 0.5314 | **0.2729** | **0.9186** |
| nomic (Ollama) | 0.7543 | 0.7222 | 0.0321 | 0.4418 |
| nomic (LM Studio) | 0.6554 | 0.5796 | 0.0758 | 0.5838 |

### 3.3 Embedding Findings

- **bge-m3 has 8.5× more semantic separation** than nomic (Ollama). This means much more precise searches.
- **bge-m3 is the ONLY truly cross-lingual**: 0.9186 EN↔ES vs 0.44 of nomic. Nomic doesn't understand Spanish directly.
- **LM Studio embeddings are NOT deterministic**: same text produces slightly different vectors. Unacceptable for memory.
- **Cold start**: bge-m3 282× faster (47ms vs 13,278ms). Others load model on demand.
- **Warm throughput**: LM Studio wins on pure speed (96.8/s) but loses on quality and determinism.

---

## 4. Resource Usage

| Engine | RAM LLM | RAM Embeddings | RAM Total | Notes |
|---|---|---|---|---|
| **llama.cpp** | 4,886 MB | 344 MB | **5,230 MB** | Always loaded, Metal GPU |
| Ollama | ~4,700 MB (lazy) | ~274 MB (lazy) | ~5,000 MB | Loads on demand |
| LM Studio | ~4,700 MB (lazy) | ~300 MB (lazy) | ~5,000 MB | Loads on demand |

Note: Ollama and LM Studio free RAM after keep_alive (5min default). llama.cpp keeps model always loaded.

---

## 5. Conclusion

For the MCP-agent-memory system, **llama.cpp + bge-m3 is the right choice**:

1. **48× faster cold start** — critical for real-time responses
2. **8.5× better semantic separation** — precise searches vs garbage
3. **Real cross-lingual** (0.92) — nomic doesn't work in Spanish (0.44)
4. **Perfect determinism** — LM Studio fails here
5. **Always-loaded** — no on-demand load latency

Ollama and LM Studio are better for interactive human use (load/unload models, GUI) but inferior as a backend for an automatic memory system that needs consistent and fast responses.
