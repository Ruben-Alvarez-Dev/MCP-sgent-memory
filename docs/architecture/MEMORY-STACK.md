# The Memory Stack — Levels, Flows and Legend

> Source of truth: directory layout under `data/` and module wiring in
> `src/unified/server/backpack.py`, verified 2026-06-07. Every node in these
> diagrams exists on disk; status colors reflect the repair plan diagnosis
> (docs/plans/2026-06-07-MEMORY-REPAIR-PLAN.md).

## 1. The stack (8 levels)

Information enters at the bottom (senses) and crystallizes upward into
permanent, human-readable knowledge.

```mermaid
flowchart TB
    classDef ok fill:#1a7f37,color:#fff,stroke:#0d4f22
    classDef broken fill:#b91c1c,color:#fff,stroke:#7f1d1d
    classDef partial fill:#b45309,color:#fff,stroke:#78350f

    LXP["Lx-persistent — THE VAULT (Obsidian)<br/>Conocimiento / Decisiones / Entidades / Episodios<br/>storage: data/vault + data/Lx-persistent"]:::ok
    LXD["Lx-deliberative — PLANS & SESSIONS<br/>deliberate intentions, session state<br/>storage: data/Lx-deliberative/{plans,sessions}"]:::partial
    L5["L5-selective — ROUTING & REMINDERS<br/>intelligent search, what surfaces when<br/>storage: data/L5-selective/reminders + L5_routing module"]:::ok
    L4["L4-narrative — CONSOLIDATED NARRATIVE<br/>the story so far; consolidation checkpoints<br/>storage: data/L4-narrative/state.json"]:::partial
    L3["L3-semantic — FACTS & DECISIONS<br/>distilled knowledge, ADR-like decisions<br/>storage: data/L3-semantic/{facts,decisions}"]:::ok
    L2["L2-episodic — CONVERSATIONS & EPISODES<br/>threads + messages (FTS5) + episodes.jsonl<br/>storage: data/L2-episodic/conversations.db"]:::broken
    L1["L1-working — PER-AGENT WORKING MEMORY<br/>short-term scratch per agent<br/>storage: data/L1-working/agents/"]:::partial
    L0["L0-sensory — RAW EVENT CAPTURE<br/>everything seen, append-only<br/>storage: data/L0-sensory/events.jsonl"]:::broken

    L0 -->|"consolidation (L0_to_L4)"| L2 --> L3 --> L4
    L1 -.->|"context for"| L2
    L4 --> L5
    L5 --> LXD
    L3 -->|"vault sync"| LXP
    L4 -->|"vault sync"| LXP
```

**Color legend** — green: working today · red: BROKEN (no data since
2026-05-31; see repair plan D1-D3) · amber: partially wired (exists on disk,
weak producers/consumers).

## 2. Flow A — Capture (where information enters)

```mermaid
flowchart LR
    classDef ok fill:#1a7f37,color:#fff
    classDef broken fill:#b91c1c,color:#fff
    classDef planned fill:#6b7280,color:#fff,stroke-dasharray: 5 5

    subgraph producers [PRODUCERS]
        CLI["CLI agents<br/>(hooks)"]:::planned
        COWORK["Cowork/Claude<br/>memory bridge"]:::planned
        MCPT["MCP tools<br/>(53, direct calls)"]:::ok
    end

    INBOX[("inbox/<br/>EMPTY — no producers")]:::broken
    BP["backpack.py daemon<br/>crash-loop Errno 48"]:::broken
    L0J[("L0 events.jsonl")]:::broken
    CONV[("L2 conversations.db<br/>last write 2026-05-31")]:::broken
    LINK["entity linker<br/>(regex today → catalog-validated per repair plan)"]:::broken
    ET[("entity_timeline.db<br/>entities + events + relations + FTS5")]:::ok

    CLI -.-> INBOX
    COWORK -.-> INBOX
    INBOX --> BP
    MCPT --> ET
    BP --> L0J --> CONV
    CONV --> LINK --> ET
```

Reading: solid green path (MCP tools → entity timeline) is the ONLY live
entry today — it is how the 2026-06-07 mirrors were written. Everything
through inbox/backpack is red (repair plan Phases 0-1); dashed gray nodes
are the producers Phase 1 adds.

## 3. Flow B — Consolidation (L0 → L4, the dream cycle)

```mermaid
flowchart LR
    classDef ok fill:#1a7f37,color:#fff
    classDef partial fill:#b45309,color:#fff

    EV[("L0 events.jsonl")]:::partial
    EP["episode builder<br/>(consumed-marker, commit 3828208)"]:::ok
    EPJ[("L2 episodes.jsonl")]:::partial
    FACTS["fact distiller"]:::partial
    F3[("L3 facts/ + decisions/")]:::ok
    NARR["narrative consolidator<br/>(_load_state restored, commit 0a1aae5)"]:::ok
    N4[("L4 state.json")]:::ok
    VS["vault_entity_bridge<br/>entity_sync_all"]:::ok
    VAULT[("Lx-persistent VAULT<br/>52 entities synced 2026-06-07")]:::ok

    EV --> EP --> EPJ --> FACTS --> F3 --> NARR --> N4
    N4 --> VS --> VAULT
    F3 --> VS
```

Reading: the machinery was repaired in the May 31 - Jun 6 commit batch
(F-01 fix, consumed-markers) and works when fed — but it starves because
Flow A is dead upstream. Fix capture and this whole pipeline resumes.

## 4. Flow C — Recall (how an agent gets memory back)

```mermaid
flowchart LR
    classDef ok fill:#1a7f37,color:#fff
    classDef partial fill:#b45309,color:#fff

    Q["agent query<br/>(MCP tool call)"]:::ok
    ROUTE["L5 routing<br/>(intent → sources)"]:::ok
    FTS["SQLite FTS5<br/>entities + events + messages"]:::ok
    EMB["BGE-M3 embeddings<br/>llama-server :8081"]:::ok
    QD[("Qdrant<br/>collections sparse — underfed")]:::partial
    FUSE["fusion + ranking"]:::ok
    A["answer with provenance"]:::ok

    Q --> ROUTE
    ROUTE --> FTS --> FUSE
    ROUTE --> EMB --> QD --> FUSE
    FUSE --> A
```

## 5. Node legend (every box, one line)

| Node | What it does | Storage | Status |
|---|---|---|---|
| L0-sensory | Append-only raw event log; nothing is interpreted here | data/L0-sensory/events.jsonl | RED — starved |
| L1-working | Per-agent scratchpad for the current task | data/L1-working/agents/ | AMBER |
| L2-episodic | Conversations (threads/messages, FTS5) and episode summaries | data/L2-episodic/ | RED — last write 05-31 |
| L3-semantic | Distilled facts and decisions (the "what we know") | data/L3-semantic/ | GREEN |
| L4-narrative | Consolidated story + consolidation checkpoints | data/L4-narrative/state.json | AMBER |
| L5-selective | Routing: decides which memory surfaces for which query | memory/L5 modules + reminders | GREEN |
| Lx-deliberative | Plans and session intentions (future-facing memory) | data/Lx-deliberative/ | AMBER |
| Lx-persistent | The Obsidian vault — human-readable crystallization | data/vault/ | GREEN |
| inbox/ | File-drop ingestion point for external producers | inbox/ | RED — zero producers |
| backpack.py | The daemon orchestrating ingest + consolidation | src/unified/server/ | RED — port crash-loop |
| entity_timeline.db | Phone book + timelines + relations (ADR-001 metadata) | data/entity_timeline.db | GREEN |
| BGE-M3 + Qdrant | Semantic similarity for recall and dedup | :8081 + qdrant/ | AMBER — underfed |

> Update discipline: when a repair-plan phase lands, flip the affected node
> colors in the SAME commit. A diagram that lies is worse than no diagram.
