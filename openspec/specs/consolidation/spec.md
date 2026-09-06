# Capability: consolidation (current truth, pre-change)

## Purpose
How memories move L1→L2→L3→L4 and how dream works today, with the generative
LLM permanently absent.

## Requirements

### Requirement: MEM-01 Extractive fallback summarization
`_summarize` SHALL attempt `get_llm().ask()` and, on any failure, SHALL return
extractive concatenation `[n] text[:200]`. (LLM permanently unavailable:
fallback is the effective behavior.)

### Requirement: MEM-02 Threshold promotion
`heartbeat`/`consolidate` SHALL promote L1→L2 by scope grouping (≥2 items),
L2→L3 and L3→L4 by time thresholds, and run `_verify_stale` on L2+ memories.

### Requirement: MEM-03 Background dream with cooldown
`dream` SHALL schedule background summarization with cooldown
`consolidation_promote_L4` and persist narratives as L4 items.

### Requirement: MEM-04 Overwrite semantics (TO BE REPLACED)
Consolidation SHALL upsert derived items without validity windows or
provenance links to source episodes. M4 replaces this with ADD-only +
bi-temporal validity + `superseded_by` chains.
