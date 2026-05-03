# Continuous Knowledge Verification in AI Agent Memory Systems

## Research Document — MCP-agent-memory

**Last Updated**: 2026-05
**Authorship**: MCP-agent-memory / CLI-agent-memory Architecture
**Status**: Active Research — Integration Phase
**Classification**: Internal — Roadmap Development

---

## Abstract

This document analyzes the problem of **knowledge obsolescence** in persistent memory systems for AI agents. When an agent stores information about a project, repository, or architectural decision, that information has a limited useful lifetime. Files change, decisions are reversed, repositories are restructured. If the agent operates with outdated data without verifying it, it makes erroneous decisions with undeserved confidence.

The research is structured around three axes: (1) the mechanisms the human brain uses to maintain the reliability of its memories, (2) the state-of-the-art (SOTA) techniques developed by the AI community to address this problem, and (3) a concrete algorithmic proposal that integrates both approaches into the MCP-agent-memory system.

**Key conclusion**: The optimal process is not to verify everything constantly, but to apply **selective verification based on relevance, confidence, and rate of change** — exactly as the brain does. The act of remembering itself should be an opportunity for verification (reconsolidation), not a simple read operation.

---

## 1. Introduction — The Problem

### 1.1 Problem Definition

A memory system for AI agents faces a fundamental tension:

- **It needs to remember** to operate with context and coherence.
- **It cannot blindly trust** what it remembers because reality changes.
- **It cannot verify everything** because the computational and temporal cost would be prohibitive.

This problem manifests in our MCP-agent-memory system concretely: we have 53 MCP tools, L5_routing injects context automatically on every turn, and L0_to_L4_consolidation consolidates memories periodically. But **no mechanism verifies that what is stored remains true**.

### 1.2 Concrete Example

The system stores: *"CLI-agent-memory is at `/tmp/CLI-agent-memory/`"* (confidence 0.74).

The reality at query time: CLI-agent-memory is at `~/CLI-agent-memory/`, has tags up to v1.0.0, and has an `adapters/` structure that didn't exist when that fact was stored.

If the agent operates with the old data without verifying, its actions will be incorrect. This is not a theoretical problem — it happened in this very session.

### 1.3 Research Scope

This document investigates:
- How the human brain solves this problem (Section 3)
- What techniques the AI community has developed (Section 4)
- What concrete algorithmic proposal we implement (Section 5)
- How it integrates into the system roadmap (Section 6)

---

## 2. Methodology

### 2.1 Approach

Structured narrative review with comparative analysis. This is not a formal systematic review (PRISMA criteria were not applied), but a directed synthesis of relevant literature to support an architectural decision.

### 2.2 Sources

- Primary literature: cognitive neuroscience and NLP/IR papers (1990–2026)
- Reference implementations: Self-RAG, CRAG, HippoRAG, FreshQA
- System architecture: MCP-agent-memory and CLI-agent-memory source code

---

## 3. Theoretical Framework — Neuroscience of Verifiable Memory

### 3.1 Memory Reconsolidation (Nader, 2000; Przybyslawski & Sara, 1997)

**Central finding**: When the brain accesses a long-term memory, that memory becomes temporarily labile (unstable, modifiable) before being re-stored. This process is called **reconsolidation**.

**Implication for AI**: The act of RETRIEVING a memory should not be a read-only operation. It should be an opportunity for verification and updating. Every time L5_routing retrieves context, it is accessing memories that may be outdated. The system should leverage that access for verification.

**Experimental evidence**: Nader (2000) demonstrated that rats administered a protein synthesis inhibitor immediately after reactivating a fear memory lost that memory permanently. This proves that reconsolidation is an active rewriting process, not a simple re-read.

**Critique**: Reconsolidation in humans is more nuanced than in animal models. Some studies (Chan et al., 2009) suggest that not all memories are reconsolidated every time they are accessed — reconsolidation appears to be gated by factors such as error prediction and novelty.

### 3.2 Predictive Coding and Prediction Error Minimization (Friston, 2010)

**Central finding**: The brain operates as a prediction machine. It constantly generates predictions, compares them against reality, and updates its internal model when it detects prediction errors. This framework is known as **Predictive Coding** or the **Free Energy Principle**.

**Implication for AI**: The memory system should generate predictions based on what it knows and compare them against the current state. If the file I remember having 100 lines now has 200, there is a prediction error — and that should trigger an update.

**Derived algorithmic principle**: Verification does not need to be exhaustive. It only needs to occur when there is **potential for surprise** — that is, when reality could differ significantly from what is stored.

### 3.3 Metamemory — Monitoring One's Own Knowledge (Nelson & Narens, 1990)

**Central finding**: The brain has a **metamemory** system — the ability to monitor and control its own memory processes. This includes:
- Knowing **what** you know (and what you don't)
- Knowing **how confident** you are in each memory
- Knowing **when** a memory needs verification
- Deciding **how much effort** to invest in retrieval or verification

**Implication for AI**: Our system already has `confidence` in MemoryItem, but it's a static value assigned at storage time that is never updated. Metamemory requires that value to be **dynamic** — adjusted with each verification, failed access, or passage of time.

**Nelson & Narens Model**: The model proposes two levels:
1. **Object level**: the memories themselves
2. **Meta level**: the monitoring and control of those memories

In our system, the object level is the data in Qdrant. The meta level does not yet exist formally — we need a system that monitors the reliability of memories and decides when to verify.

### 3.4 Forgetting Curve and Spaced Repetition (Ebbinghaus, 1885; Wozniak, 1985)

**Central finding**: Memories decay exponentially over time unless reinforced. Spaced repetition schedules reinforcements at increasing intervals just before forgetting becomes significant.

**Modern algorithms**: SM-2 (SuperMemo, 1987), FSRS (Anki, 2023) — calculate the optimal review interval based on item difficulty and user response history.

**Implication for AI**: Each type of data has a different "decay speed":
- `2 + 2 = 4` → never decays (never-changing)
- `"The president is X"` → decays in years (slow-changing)
- `"file X has function Y"` → decays in hours/days (fast-changing)
- `"the server is running"` → decays in minutes (real-time)

The system should apply different verification intervals based on data category, not a uniform interval for everything.

### 3.5 Source Monitoring (Johnson, Hashtroudi & Lindsay, 1993)

**Central finding**: The brain not only stores memories but tags their **origin** (source monitoring): did I see it directly? was I told? did I infer it? did I dream it? This source attribution is critical for reliability.

**Implication for AI**: Our memories should have a `verification_source` field indicating how they were last verified:
- `direct_observation` — the agent verified it by reading the file/repo directly
- `user_assertion` — the user stated it, without independent verification
- `inference` — the agent deduced it from other data
- `unverified` — never verified against a source of truth

A fact verified by direct observation carries more weight than one inferred or unverified.

### 3.6 Neuroscience Synthesis

The human brain handles knowledge reliability with a **5-phase** process that is selective, non-blocking, and adaptive:

```
RECALL → PREDICT → VERIFY → UPDATE → CONSOLIDATE
```

Key principles:
1. **Selectivity**: Does not verify everything. Prioritizes by relevance, confidence, and risk.
2. **Non-blocking**: Uses available information while verifying in parallel.
3. **Categorization**: Classifies facts by rate of change and adjusts verification frequency.
4. **Reconsolidation**: Every access is an update opportunity.
5. **Metamemory**: Continuous monitoring of the certainty level of each piece of knowledge.

---

## 4. State of the Art — AI Techniques

### 4.1 Evolution of the RAG Paradigm

The Retrieval-Augmented Generation paradigm (Lewis et al., 2020) solved the problem of **access** to external knowledge, but introduced the problem of the **quality** of what is retrieved. The evolution from RAG to current techniques reflects a clear progression:

```
RAG (2020)         → Retrieves documents, injects into prompt. No verification.
CRAG (2024)        → Evaluates retrieval quality. Corrective actions if poor.
Self-RAG (2023)    → Model decides when to retrieve, critique, generate.
FreshQA (2023)     → Classifies facts by rate of change. Verifies by category.
HippoRAG (2024)    → Knowledge graph as hippocampal index.
MemoRAG (2024)     → Memory as bridge between query and answer.
MemoryLLM (2024)   → Self-updatable memory within the model.
```

### 4.2 Corrective RAG — CRAG (Yan et al., 2024)

**Principle**: A lightweight evaluator analyzes the quality of retrieved documents and returns a confidence grade. Based on that grade, different actions are triggered:

- **High confidence**: Use documents directly.
- **Medium confidence**: Refine with additional web search.
- **Low confidence**: Discard and search completely anew.

**Key algorithm**: `decompose-then-recompose` — decomposes retrieved documents into information units, filters irrelevant ones, and recomposes only the relevant ones.

**Application to our system**: L5_routing already performs smart_retrieve with confidence scoring. But it lacks the **post-retrieval evaluation** phase. When we inject context, we never ask: *"are these data still valid?"*

### 4.3 Self-RAG — Self-Reflective RAG (Asai et al., 2023)

**Principle**: The model learns to generate reflection tokens that allow it to:
- Decide whether it needs to retrieve information (`retrieve`)
- Evaluate whether the retrieval was relevant (`is_relevant`)
- Evaluate whether its generation is supported by the retrieval (`is_supported`)
- Evaluate whether the answer is useful (`is_useful`)

**Innovation**: The model does not always retrieve — it retrieves **on demand** when it detects the need.

**Application to our system**: Our v1.3 injects context automatically on every turn (like classic RAG). Self-RAG suggests it would be more efficient to retrieve only when the agent detects uncertainty. However, for a system with automatic context like ours, proactive retrieval is preferable — the improvement would come from the **critique phase** post-retrieval.

### 4.4 FreshQA — Freshness-Aware QA (Vu et al., 2023)

**Principle**: Classifies questions (and their answers) into three freshness categories:

| Category | Example | Verification Frequency |
|---|---|---|
| **Never-changing** | "What is 2+2?" | Never |
| **Slow-changing** | "Who is the president of Argentina?" | Monthly/yearly |
| **Fast-changing** | "What Python version does this project use?" | Every use |

**Key finding**: LLMs tend to answer fast-changing questions with outdated data with the same confidence as never-changing data. They do not discriminate between fact types.

**Application to our system**: Each MemoryItem should have a `change_speed` field (`never` | `slow` | `fast` | `realtime`) that determines verification frequency. A fact about a repo's location is slow-changing. A fact about a file's content is fast-changing.

### 4.5 HippoRAG (2024)

**Principle**: Replicates the brain's hippocampal indexing system. The hippocampus does not store complete memories — it stores **indices** that point to the location of complete memories in the neocortex.

**Implementation**: Uses a Knowledge Graph as a hippocampal index. Nodes are entities/concepts. Edges are relationships. When information is retrieved, the graph is traversed from relevant nodes until complete passages are found.

**Application to our system**: Our system uses Qdrant (vector search) as the primary retrieval mechanism. This is more like the neocortex than the hippocampus. An entity graph on top of Qdrant would improve relational retrieval.

### 4.6 Comparative Analysis of Approaches

| Technique | Solves | Does not solve | Complexity |
|---|---|---|---|
| Basic RAG | Access to external knowledge | Obsolescence, quality | Low |
| CRAG | Post-retrieval quality | Temporal freshness | Medium |
| Self-RAG | When and how much to retrieve | Source verification | Medium-High |
| FreshQA | Freshness classification | Automatic verification | Medium |
| HippoRAG | Relational retrieval | Veracity of relationships | High |

**Conclusion**: No single technique solves the complete problem. A **combination** of CRAG (evaluation), FreshQA (temporal classification), and source-of-truth verification is needed.

---

## 5. Algorithmic Proposal — Continuous Knowledge Verification

### 5.1 Design Principles

Based on neuroscience (Section 3) and the state of the art (Section 4), the principles are:

1. **Memory-first**: Always consult memory first. Do not assume, do not ignore.
2. **Selective verification**: Only verify what is relevant to the current action.
3. **Non-blocking**: The agent proceeds with what it has. Verification runs in the background.
4. **Temporal categorization**: Each data type has its rate of change and verification frequency.
5. **Reconsolidation**: Every access to a memory is an update opportunity.
6. **Dynamic metamemory**: Confidence scores are updated with each verification.

### 5.2 Extended Data Model

The existing `MemoryItem` field needs extensions:

```python
class VerificationStatus(str, Enum):
    NEVER_VERIFIED = "never_verified"     # Never verified against source of truth
    VERIFIED = "verified"                 # Recently verified
    STALE = "stale"                       # Verified but too long ago
    DISPUTED = "disputed"                 # Verification failed — data possibly incorrect

class ChangeSpeed(str, Enum):
    NEVER = "never"       # 2+2=4 — never verifies
    SLOW = "slow"         # Decisions, architecture — verifies monthly
    MEDIUM = "medium"     # Repo state, structure — verifies weekly
    FAST = "fast"         # File contents — verifies per use
    REALTIME = "realtime" # Server running — always verifies

class MemoryItem(BaseModel):
    # ... existing fields ...
    verified_at: Optional[str] = None           # Last verification against source of truth
    verification_source: Optional[str] = None    # How it was verified (file_read, git_log, web, user)
    verification_status: VerificationStatus = VerificationStatus.NEVER_VERIFIED
    change_speed: ChangeSpeed = ChangeSpeed.MEDIUM  # Expected verification frequency
    last_accessed_at: Optional[str] = None       # Last access (for reconsolidation)
    access_count: int = 0                         # Times accessed (for prioritization)
```

### 5.3 Freshness Score

The freshness score combines confidence, age, and rate of change:

```python
def freshness_score(memory: MemoryItem) -> float:
    """Calculates the 'freshness' of a memory. 1.0 = perfect, 0.0 = completely stale."""
    
    base = memory.confidence  # 0.0 - 1.0
    
    # If never verified, reduce significantly
    if memory.verification_status == VerificationStatus.NEVER_VERIFIED:
        return base * 0.5
    
    # If disputed, reduce drastically
    if memory.verification_status == VerificationStatus.DISPUTED:
        return base * 0.2
    
    # If verified, calculate temporal decay
    if memory.verified_at:
        age_hours = (now() - parse(memory.verified_at)).total_seconds() / 3600
        
        # Half-life by rate of change (hours until confidence drops to half)
        half_lives = {
            ChangeSpeed.NEVER:    float('inf'),  # Never decays
            ChangeSpeed.SLOW:     720,            # 30 days
            ChangeSpeed.MEDIUM:   168,            # 7 days
            ChangeSpeed.FAST:     24,             # 1 day
            ChangeSpeed.REALTIME: 0.5,            # 30 minutes
        }
        
        half_life = half_lives[memory.change_speed]
        if half_life == float('inf'):
            return base  # Never decays
        
        decay = 2 ** (-age_hours / half_life)  # Exponential decay (Ebbinghaus model)
        return base * decay
    
    return base * 0.4  # STALE without recent verified_at
```

### 5.4 Continuous Verification Pipeline

The complete process has 5 phases, mapped to the existing architecture:

#### PHASE 1: RECALL — Enhanced Retrieval

**Location**: `L5_routing/smart_retrieve()`  
**Change**: Add freshness_score to result ranking.

```python
# In smart_retrieve, when sorting results:
# BEFORE: sort by confidence only
# AFTER: sort by freshness_score (confidence × temporal decay)
results.sort(key=lambda r: freshness_score(r), reverse=True)
```

**Impact**: Recently verified memories rise. Stale ones sink. Injected context prioritizes freshness.

#### PHASE 2: PREDICT — Confidence Labeling in ContextPack

**Location**: `ContextPack.to_injection_text()`  
**Change**: Include freshness indicators in injected text.

```
BEFORE:
[L0_capture] (conf=0.75): CLI-agent-memory is at /tmp/CLI-agent-memory

AFTER:
[L0_capture] (conf=0.75, ✅ VERIFIED 2h ago): CLI-agent-memory is at ~/CLI-agent-memory
[L0_capture] (conf=0.80, ⚠️ STALE 5d ago): The project uses ollama for embeddings
[L0_capture] (conf=0.70, ❓ NEVER VERIFIED): The opencode adapter is in the MCP repo
```

**Impact**: The agent sees which data are reliable and which need verification. It can prioritize actions accordingly.

#### PHASE 3: VERIFY — Selective Background Verification

**Location**: New endpoint `/api/verify-memories` + `session.idle` hook  
**Trigger**: During idle time, after each significant action, or when the agent requests it.

```python
async def verify_memories(session_id: str, memory_ids: list[str]) -> list[VerificationResult]:
    results = []
    for mid in memory_ids:
        memory = await fetch_memory(mid)
        
        # Generate verification query by type
        if memory.change_speed == ChangeSpeed.FAST:
            # Verify against filesystem
            if memory.scope_type == MemoryScope.DOMAIN:
                actual = read_file_or_repo(memory.content)
                match = compare(memory.content, actual)
        
        elif memory.change_speed == ChangeSpeed.SLOW:
            # Verify against docs/git
            if memory.type == MemoryType.DECISION:
                actual = check_decision_still_valid(memory)
                match = compare(memory.content, actual)
        
        # Update memory based on result
        if match:
            memory.verification_status = VerificationStatus.VERIFIED
            memory.verified_at = now()
            memory.confidence = min(1.0, memory.confidence + 0.05)  # Reinforcement
        else:
            memory.verification_status = VerificationStatus.DISPUTED
            memory.confidence = max(0.0, memory.confidence - 0.2)   # Penalty
        
        results.append(VerificationResult(memory_id=mid, status=memory.verification_status))
    return results
```

#### PHASE 4: ACT — Action with Labeled Knowledge

**Location**: Agent (LLM)  
**Change**: The agent receives context with freshness tags and can make informed decisions about what to trust.

Expected behavior:
- **VERIFIED**: Use directly as a reliable source.
- **STALE**: Use but verify if the action critically depends on it.
- **NEVER VERIFIED**: Verify before using for critical decisions.
- **DISPUTED**: Do not use. Seek updated information.

#### PHASE 5: CONSOLIDATE — Reinforcement in the Dream Cycle

**Location**: `L0_to_L4_consolidation` consolidation  
**Change**: Integrate verification into the existing consolidation cycle.

```python
# In the existing dream cycle, add verification step:
async def dream_cycle():
    # Existing step: memory consolidation
    await consolidate_memories()
    
    # New step: verify stale memories
    stale_memories = await find_stale_memories(threshold=0.5)
    for memory in stale_memories[:10]:  # Limit to 10 per cycle
        await verify_memory(memory)
```

### 5.5 Verification System Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │           AGENT (LLM)                       │
                         │  Sees context with freshness tags           │
                         │  ✅ VERIFIED  ⚠️ STALE  ❓ UNKNOWN         │
                         └──────────────────┬──────────────────────────┘
                                            │ uses context
                         ┌──────────────────▼──────────────────────────┐
                         │         L5_routing (smart_retrieve)         │
                         │  Sorts by freshness_score                   │
                         │  confidence × decay(change_speed, age)     │
                         └──────────────────┬──────────────────────────┘
                                            │ retrieves memories
              ┌─────────────────────────────▼─────────────────────────────┐
              │                    Qdrant (vector store)                   │
              │  MemoryItem with: verified_at, verification_status,        │
              │  change_speed, access_count, last_accessed_at              │
              └─────────────────────────────┬─────────────────────────────┘
                                            │
           ┌────────────────────────────────┼────────────────────────────────┐
           │                                │                                │
  ┌────────▼─────────┐        ┌────────────▼──────────┐       ┌────────────▼──────────┐
  │  session.idle     │        │  L0_to_L4_consolidation│       │  /api/verify-memories  │
  │  hook             │        │  dream cycle            │       │  (manual endpoint)    │
  │  → verify stale   │        │  (consolidation +       │       │  → verify on           │
  │  → update status  │        │   verification)         │       │    demand             │
  └──────────────────┘        └───────────────────────┘       └───────────────────────┘
```

---

## 6. Argued Conclusions

### 6.1 The Central Problem

Memory systems for AI agents that only store and retrieve information without verifying it are building **confidence on sand**. The confidence of a fact should not be static — it should decay over time and be reinforced through verification, as occurs in the human brain.

### 6.2 The Neuroscience Solution Is Correct

The brain solves this problem elegantly:
- It does not verify everything (selectivity)
- It does not block while verifying (non-blocking)
- It adapts frequency to data type (temporal categorization)
- It uses every access as an update opportunity (reconsolidation)

We argue this approach is superior to exhaustive verification for three reasons:
1. **Efficiency**: Verifying only what is relevant reduces computational cost by orders of magnitude.
2. **Fluency**: The agent does not wait for verifications. It acts with what it has and improves in the background.
3. **Adaptability**: Fast-changing data are verified frequently; never-changing data never waste resources.

### 6.3 Implementation Is Incremental

We do not need to rebuild the system. The proposed extensions integrate into the existing architecture:

- `MemoryItem` is extended with 5 new fields (backward compatible)
- `smart_retrieve` adds freshness scoring to the existing ranking
- `ContextPack.to_injection_text()` adds visual tags
- `L0_to_L4_consolidation` adds a verification step to the existing cycle
- New endpoint `/api/verify-memories` for on-demand verification

### 6.4 Empirical Validation Is Necessary

This document presents a well-founded proposal, not a validated solution. Next steps include:
1. Implement the extended data model
2. Measure the impact of freshness scoring on retrieved context quality
3. A/B testing: agent with vs. without freshness tags
4. Measure the error rate from stale data before and after verification

### 6.5 Limitations

- **Automatic change_speed classification**: Determining whether a fact is fast or slow-changing requires heuristics that may fail. An architectural decision misclassified as fast-changing would be verified unnecessarily.
- **Verification cost**: Verifying against filesystem/repos/APIs has a cost. Thoroughness must be balanced with efficiency.
- **False negatives**: A matching verification does not guarantee the fact is correct — only that the partial check found no discrepancies.

---

## 7. References

### Neuroscience

1. Nader, K. (2000). *Memory traces unbound*. Trends in Neurosciences, 26(2), 65-72.
2. Nader, K., Schafe, G. E., & Le Doux, J. E. (2000). *Fear memories require protein synthesis in the amygdala for reconsolidation after retrieval*. Nature, 406(6797), 722-726.
3. Przybyslawski, J., & Sara, S. J. (1997). *Reconsolidation of memory after its reactivation*. Behavioural Brain Research, 84(1-2), 241-246.
4. Friston, K. (2010). *The free-energy principle: a unified brain theory?* Nature Reviews Neuroscience, 11(2), 127-138.
5. Nelson, T. O., & Narens, L. (1990). *Metamemory: A theoretical framework and new findings*. The Psychology of Learning and Motivation, 26, 125-173.
6. Ebbinghaus, H. (1885). *Über das Gedächtnis*. Leipzig: Duncker & Humblot.
7. Baddeley, A. D., & Hitch, G. (1974). *Working memory*. The Psychology of Learning and Motivation, 8, 47-89.
8. Johnson, M. K., Hashtroudi, S., & Lindsay, D. S. (1993). *Source monitoring*. Psychological Bulletin, 114(1), 3-28.
9. Stickgold, R., & Walker, M. P. (2013). *Sleep-dependent memory consolidation: a guide for the perplexed*. Nature Reviews Neuroscience, 14(7), 492-502.
10. Chan, T. C., et al. (2009). *Reactivation-induced memory instability: is reconsolidation an epiphenomenon?* Neuroscience, 164(4), 1373-1379.

### Artificial Intelligence

11. Lewis, P., et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS 2020.
12. Yan, S. Q., Gu, J. C., Zhu, Y., & Ling, Z. H. (2024). *Corrective Retrieval Augmented Generation*. ICML 2024. arXiv:2401.15884.
13. Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2023). *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*. arXiv:2310.11511.
14. Vu, T., et al. (2023). *FreshLLMs: FreshQA, FreshPrompt, FreshRL*. EMNLP 2023.
15. Wozniak, P. A. (1985). *SuperMemo: Optimization of learning*. Technical Report.
16. Graves, A., et al. (2016). *Hybrid computing using a neural network with dynamic external memory*. Nature, 538(7626), 471-476.
17. HippoRAG (2024). *HippoRAG: Retrieval-Augmented Generation with Hippocampal Indexing*.
18. Wang, Y., et al. (2024). *MemoryLLM: Training Large Language Models with Self-Updatable Memory*.

---

## A. Appendix — Mapping to MCP-agent-memory Architecture

| Neuroscience Concept | MCP-agent-memory Component | Status |
|---|---|---|
| Working Memory | Context window + injected ContextPack | ✅ Implemented (v1.3) |
| L0 Raw Events | `L0_capture.ingest_event` | ✅ Implemented |
| L1 Working Memory | `L3_facts` + `L0_capture.memorize` | ✅ Implemented |
| L2 Episodic Memory | `L2_conversations` + L0_to_L4_consolidation L2 | ✅ Implemented |
| L3 Semantic Memory | `L3_decisions` decisions + L0_to_L4_consolidation L3 | ✅ Implemented |
| L4 Consolidated | `L0_to_L4_consolidation` L4 summaries | ✅ Implemented |
| L5 Context Assembly | `L5_routing` smart_retrieve | ✅ Implemented |
| Reconsolidation | Post-retrieval verification | 🔜 Proposed |
| Metamemory | freshness_score + verified_at | 🔜 Proposed |
| Predictive Coding | Background verification on session.idle | 🔜 Proposed |
| Forgetting Curve | change_speed + temporal decay | 🔜 Proposed |
| Source Monitoring | verification_source field | 🔜 Proposed |
| Hippocampal Index | Knowledge Graph over Qdrant | 🔜 Future |
