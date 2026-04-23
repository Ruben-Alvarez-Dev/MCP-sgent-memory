# SOTA Context Management Strategy (2026)
## MCP-Memory-Server & Zhipu GLM-5.1

### 1. Executive Summary: The Hybrid Paradigm
In 2026, the debate between "RAG vs. Long Context" has been resolved in favor of a **Hybrid Paradigm**. While models like GLM-5.1 offer 262K+ windows, relying solely on a massive static context leads to high latency (TTFT) and "Lost-in-the-middle" attention decay.

**The Winner Strategy:** Use **Context Caching** for global project knowledge and **Dynamic RAG (VK-Cache)** for local task precision.

---

### 2. Research Findings (SOTA Analysis)
- **Attention Decay:** Even in 200K+ windows, models prioritize information at the extreme ends of the prompt. Critical engineering rules placed in the middle are often ignored.
- **Latency (TTFT):** Large contexts without caching increase Time-to-First-Token linearly. 128K tokens ≈ 5-10s delay per turn.
- **Context Caching:** Allows pre-processing of static prefixes (Docs, Rules, Repo Map). Reduces costs by up to 90% and latency by 80% for repeated prefixes.
- **Agentic RAG:** The SOTA approach involves the agent actively deciding which context "backpacks" to load based on the current intent.

---

### 3. Proposed Architecture: "The Triple-Buffer"
We will move from a flat 8K budget to a segmented 48K buffer:

| Segment | Size | Content | Priority |
|---------|------|---------|----------|
| **Buffer A: Pinned Rules** | 8K | Core Engineering Standards & Style Guides | High (Always First) |
| **Buffer B: Task Context** | 24K | Relevant code, recent decisions, timeline | Medium (Semantic) |
| **Buffer C: Repo Map** | 16K | High-level structure of the entire project | Low (Structural) |

---

### 4. Implementation Step-by-Step

#### Step 1: Upgrade VK-Cache Budget
Modify `vk-cache/server/main.py` to increase the default budget and implement segmented assembly.

#### Step 2: Implement Rule Prioritization (Rule Pinning)
Update the `smart_retrieve` logic to ensure that memories tagged with `type: "rule"` or `type: "pattern"` are never pruned and are placed at the top of the prompt.

#### Step 3: Enable Context Caching in Z.AI Provider
Update the `zai-provider` extension to support Zhipu’s `ttl` and `cache_control` headers.

#### Step 4: Metadata-Driven Retrieval
Enhance the embedding payload to include `category` (rule, decision, code, timeline) to allow the Triple-Buffer assembly.

---

### 5. Technical Specifications

**VK-Cache Configuration:**
- `MAX_TOKENS`: 48,000
- `MAX_ITEMS`: 30
- `MIN_SCORE`: 0.35 (to filter noise)

**Zhipu Provider Headers:**
- `X-Check-Cache: true`
- `Cache-Control: { "ttl": 3600 }` (1-hour sliding window for engineering rules)

---

### 6. Implementation Guide (The "Remate")

#### 1. Modify `vk-cache` constants:
```python
# MCP-servers/vk-cache/server/main.py
MAX_TOKENS = 48000
RULE_BUDGET = 8000
```

#### 2. Update Context Assembly Logic:
```python
async def assemble_context(memories):
    rules = [m for m in memories if m.category == 'rule'][:RULE_BUDGET]
    others = [m for m in memories if m.category != 'rule']
    return rules + others # Ensures rules are always at the top
```

#### 3. Update Pi Agent Extension:
Add the caching logic to the `fetch` call in `index.ts` to leverage the pre-filled context.
