# SPEC-001: Adaptive Context Management & Caching Strategy

## 1. Problem Statement
### Current State
The existing `vk-cache` implementation uses a flat, score-based retrieval system with a restrictive token budget (8K-12K). While functional for basic queries, it suffers from three critical architectural flaws:
1.  **Prompt Instability:** Small changes in retrieval scores reorder the prompt segments, completely invalidating **Context Caching** (Zhipu AI / OpenAI / Anthropic). This results in unnecessary prefill latency and higher costs.
2.  **Attention Decay (Lost-in-the-Middle):** Based on research by Liu et al. (2023), LLMs lose information density in the middle of long contexts. Our current flat packing doesn't protect "Engineering Rules," which are often buried or pruned.
3.  **Under-utilization of Capacity:** GLM-5.1 supports 262K tokens. Our 8K budget is an artificial bottleneck that prevents the model from "seeing" the full project map and cross-file dependencies.

---

## 2. Research & Inspiration (The "Why")
This proposal is based on three foundational pillars:
- **X: "Lost in the Middle" (Stanford/UC Berkeley):** Proves that context placement is as important as content. We must move critical rules to the "Golden Zones" (Top/Bottom).
- **Y: Prefix Caching Optimization (vLLM / Google DeepMind):** Demonstrates that keeping the "prefix" of a prompt stable (static headers, rules, project maps) allows KV-cache reuse, reducing TTFT by up to 80%.
- **Z: Hierarchical Memory Systems (Computer Architecture):** Applying the principles of L1/L2/L3 cache to LLM context buffers.

---

## 3. Proposed Solution: "The Triple-Buffer Architecture"
We will refactor the `vk-cache` assembly pipeline into a **Stability-Sorted Segmented Buffer**.

### Segment 1: Static Buffer (Pinned Rules) - [Budget: 8K]
- **Content:** Project-wide engineering standards, style guides, and core patterns.
- **Stability:** Highest. Always placed at the beginning to maximize cache hits.
- **Retrieval:** Dedicated rule-pinning query.

### Segment 2: Structural Buffer (Repo Map) - [Budget: 16K]
- **Content:** Skeleton of the codebase, file trees, and high-level class definitions.
- **Stability:** High. Changes only on file system modifications.

### Segment 3: Dynamic Buffer (Task Context) - [Budget: 24K]
- **Content:** Recent code snippets, local decisions, and conversation history.
- **Stability:** Low. Changes every turn. Placed at the end to minimize cache invalidation of previous segments.

---

## 4. Implementation Roadmap (DDD + TDD)

### Phase 1: Laboratory Baseline (TDD)
- Create `tests/lab_context_bench.py` to measure:
    - **Retrieval Accuracy:** Can the model find a rule buried in 48K tokens?
    - **TTFT Latency:** Baseline with current 8K vs. New 48K.
    - **Cache Hit Rate:** Simulated prefix stability.

### Phase 2: Core Refactor
- Update `shared/retrieval/__init__.py`:
    - Refactor `RetrievalProfile` to support segmented budgets.
    - Implement `StabilitySort` in the context packer.
- Update `shared/retrieval/pruner.py`:
    - Move from "prune everything" to "segment-aware pruning".

### Phase 3: Zhipu Provider Integration
- Update `zai-provider` to send cache-control headers.
- Implement sliding TTL for the Static Buffer.

---

## 5. Expected Results & Metrics
- **Intelligence:** 4x increase in effective context window (12K -> 48K).
- **Performance:** <2s TTFT for 48K prompts (via Caching).
- **Reliability:** 100% "Rule Pinning" (Critical rules never pruned).

---

## 6. Rollback & Safety Plan
- Every commit will be atomic.
- The `v1_backup` of the retrieval logic will be kept as a decorator-switched fallback (`@fallback_to_v1`).
- Integration tests must pass 100% before any merge to `main`.
