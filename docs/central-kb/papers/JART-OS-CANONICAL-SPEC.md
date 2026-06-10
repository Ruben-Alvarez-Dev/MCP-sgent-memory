# Jart-OS — Canonical Specification
# Single Source of Truth for Team & CLI Onboarding

**Version:** 3.0.0
**Date:** 2026-04-11
**Status:** CANONICAL — Overrides all prior variants (Jart-OS 1-4, XP, UNO, UPDATE, OPENCLAW-system)
**Author:** Rubén Álvarez Dianez + Architecture Sessions
**Languages:** Everything in **English** — code, structure, docs, comments, prose. No exceptions.

---

## Table of Contents

1. [Principles](#1-principles)
2. [Hardware & Users](#2-hardware--users)
3. [Goal](#3-goal)
4. [The 10 Tiers](#4-the-10-tiers)
5. [Directory Convention](#5-directory-convention)
6. [Port Convention](#6-port-convention)
7. [Root Compose Pattern](#7-root-compose-pattern)
8. [Naming & ID Convention](#8-naming--id-convention)
9. [Network Topology](#9-network-topology)
10. [LLM Routing Strategy](#10-llm-routing-strategy)
11. [Agent Architecture](#11-agent-architecture)
12. [Communication Backbone (NATS)](#12-communication-backbone-nats)
13. [Memory Architecture](#13-memory-architecture)
14. [Policy Gates & Governance](#14-policy-gates--governance)
15. [Domain Map](#15-domain-map)
16. [Chief Map](#16-professor--chief-map)
17. [Tri-Unit Pattern](#17-tri-unit-pattern)
18. [Study Domain — 5 Blocks](#18-study-domain--5-blocks)
19. [Service Inventory (Live)](#19-service-inventory-live)
20. [Stack Summary](#20-stack-summary)
21. [Boot & Operations](#21-boot--operations)
22. [Open Decisions](#22-open-decisions)
23. [Changelog](#23-changelog)

---

## 1. Principles

```
P1 — Make it work first, make it perfect later.
P2 — THIS document is the single source of truth.
     All prior docs (Jart-OS 1-4, XP, UNO, UPDATE, OPENCLAW-system, 9-Levels)
     are HISTORICAL. Conflicts are resolved by THIS file.
P3 — Only build what gets used.
P4 — Nothing in production without tests.
P5 — Document decisions with WHY, not just WHAT.
P6 — Every app is AUTOCONTAINED.
     Own compose, own image, own config, own data, own logs.
     If it breaks, the neighbour does not burn.
P7 — Everything in ENGLISH: folder names, file names, variables,
     function names, config keys, documentation, comments, prose.
     No Spanish anywhere in the repository.
P8 — No external disk. Everything lives on internal SSD.
     Bind mounts only. No Docker named volumes.
```

---

## 2. Hardware & Users

| Item | Value |
|------|-------|
| Server | Mac Mini M1, 16GB RAM |
| Disk | 228GB internal (~55GB free) |
| OS | macOS (Apple Silicon) |
| Docker | v29.3.1, Compose v5.1.1 |
| Server user | `$JART_OS_USER` — runs all services |
| Admin user | `$AGENT_USER` — sudo access, design docs |
| Tailscale | VPN mesh between Macs |
| Second machine | MacBook Pro M1 Max 32GB (`$AGENT_USER`) |
| LM Studio + LM Link | Connects $JART_OS_USER ↔ $AGENT_USER via Tailscale |

### File Ownership Rules

- `$JART_OS_HOME/` → owned by `$JART_OS_USER`
- `$STUDY_DATA_DIR/PROJECT-Jart-OS/` → owned by `$AGENT_USER` (design docs, historical)
- Agent running as `$AGENT_USER` **must use `sudo`** to write files owned by `$JART_OS_USER`
- All writes to Jart-OS project files should go through `sudo` commands or run as `$JART_OS_USER`

---

## 3. Goal

> **Build a production-grade agentic operating system.**
> Focus: Technical excellence, scalable architecture, and maintainable code.
> Timeline: Iterative development with continuous deployment.

---

## 4. The 10 Tiers

```
 ┌────────────────────────────────────────────────────────────────────┐
 │                                                                    │
 │   TIER-00 — METAL          Host-level. No Docker.                  │
 │                              llama.cpp, drivers, port monitor.     │
 │                                                                    │
 │   TIER-01 — SECURITY       fail2ban, antivirus, reverse proxy.    │
 │                              pf firewall, Infisical (future).      │
 │                                                                    │
 │   TIER-02 — GATEWAY        Proxies, bridges, MCP servers.         │
 │                              LiteLLM (:10201), OpenClaw (:10202).  │
 │                                                                    │
 │   TIER-03 — SERVICES       Redis, NATS. Comms inside Docker.      │
 │                              Redis (:10301), NATS (:10302-04).     │
 │                                                                    │
 │   TIER-04 — AGENTS         Tri-units, Chiefs, Council.             │
 │                              Domains: study, dev, infra...   │
 │                                                                    │
 │   TIER-05 — FRAMEWORKS     Hermes runtime, OpenClaw.               │
 │                              Agent OS, skill execution.             │
 │                                                                    │
 │   TIER-06 — PROCESSES      Pipelines, workflows, automations.      │
 │                              OCR, PDF, Video, RAG pipelines.       │
 │                                                                    │
 │   TIER-07 — INTERFACES     Apps with UI.                           │
 │                              Mission Control, Grafana.             │
 │                                                                    │
 │   TIER-08 — KNOWLEDGE      RAG, LlamaIndex, Obsidian, Affine.     │
 │                              Vector DBs, document stores.          │
 │                                                                    │
 │   TIER-09 — CONTROL        Metrics, alerts, wrap-up.              │
 │                              Prometheus, audit logs.               │
 │                                                                    │
 │   00 ─ host ──→ ── Docker boundary ──→ ── wrap ── 09              │
 └────────────────────────────────────────────────────────────────────┘
```

### Boundary Rules

- **TIER-00 is OUTSIDE Docker.** Bare metal host. Port monitor, local models.
- **Docker boundary** sits between TIER-00 and TIER-01.
- **TIER-01** defends the boundary. **TIER-09** wraps everything.
- Each app = one folder. Self-contained compose + image + config + data.
- **No shared services. No shared volumes. Isolation absolute.**

### Tier → Number Reference

| Tier | Name | Number Range | Purpose |
|------|------|-------------|---------|
| 00 | METAL | 100YY | Host-level, no Docker |
| 01 | SECURITY | 101YY | Firewalls, policies, secrets |
| 02 | GATEWAY | 102YY | LLM proxy, MCP, bridges in-out |
| 03 | SERVICES | 103YY | Messaging buses (Redis, NATS) |
| 04 | AGENTS | 104YY | Agent processes |
| 05 | FRAMEWORKS | 105YY | Agent runtimes |
| 06 | PROCESSES | 106YY | Pipelines and automation |
| 07 | INTERFACES | 107YY | Web UIs, dashboards |
| 08 | KNOWLEDGE | 108YY | RAG, vector DBs, document stores |
| 09 | CONTROL | 109YY | Metrics, monitoring, alerts |

---

## 5. Directory Convention

### Root Structure

```
$JART_OS_HOME/
├── docker-compose.yml          # Root compose (include: pattern)
├── .env                        # All secrets and API keys
├── README.md
├── documentation/
│   ├── JART-OS-CANONICAL-SPEC.md  # THIS FILE (v3, overrides all)
│   ├── ARCHITECTURE.md           # System architecture
│   └── ...                       # See documentation/ for full list
├── scripts/
│   └── boot.sh                 # start|stop|status|logs|restart
├── agents/
│   ├── core/
│   │   └── base.py             # AgentBase class (all agents inherit)
│   ├── runtime/
│   │   └── main.py             # Agent runner skeleton
│   ├── Dockerfile.agent        # Generic agent Docker image
│   └── domains/                # Domain-specific agent configs
├── TIERS/                      # All 10 tiers
│   ├── TIER-00-METAL/
│   ├── TIER-01-SECURITY/
│   ├── TIER-02-GATEWAY/
│   ├── TIER-03-SERVICES/
│   ├── TIER-04-AGENTS/
│   ├── TIER-05-FRAMEWORKS/
│   ├── TIER-06-PROCESSES/
│   ├── TIER-07-INTERFACES/
│   ├── TIER-08-KNOWLEDGE/
│   └── TIER-09-CONTROL/
├── data/                       # Shared data (if any)
├── logs/                       # Application logs
├── control/                    # Mission plan, control files
├── pipelines/                  # Pipeline configs and scripts
└── .secrets/                   # Secrets ready for Infisical
```

### App Autocontained Pattern (MANDATORY)

Every app in every tier follows this structure:

```
TIERS/TIER-XX-NAME/1XXYY-category-appname/
├── docker-compose.yml          # Self-contained, standalone
├── Dockerfile                  # If custom image needed
├── config/                     # App configuration files
├── data/                       # App persistent data (bind mount)
├── db/                         # Sub-service data (bind mount, NOT Docker volumes)
├── engine/                     # Dependencies outside container (models, etc.)
└── logs/                       # App-specific logs
```

### Rules

- **Nothing shared between apps.** Each brings its own subservices.
- **Bind mounts only.** All data lives in the app folder. No Docker named volumes.
- **Ports:** Format `1XXYY` (XX=TIER, YY=sequence within tier).
- **Container names:** `jart-os-<appname>` (all lowercase, hyphens).

---

## 6. Port Convention

### Format

```
1XXYY
││└└── Sequence within tier (01-99)
│└──── Tier number (00-09)
└────── Always starts with 1 (Jart-OS range: 10000-19999)
```

### Live Port Map

| Port | Tier | Category | App | Container | Status |
|------|------|----------|-----|-----------|--------|
| 10201 | 02 | proxy | litellm | jart-os-litellm | ✅ Running |
| 10202 | 02 | proxy | openclaw | (jart-os-openclaw) | ⬜ Planned |
| 10301 | 03 | msg | redis | jart-os-redis | ✅ Running (healthy) |
| 10302 | 03 | msg | nats (client) | jart-os-nats | ✅ Running |
| 10303 | 03 | msg | nats (cluster) | jart-os-nats | ✅ Running |
| 10304 | 03 | msg | nats (monitor) | jart-os-nats | ✅ Running |
| 10701 | 07 | web | mission_control | jart-os-mc | ✅ Running |
| 10702 | 07 | web | grafana | jart-os-grafana | ✅ Running |
| 10901 | 09 | metrics | prometheus | jart-os-prometheus | ✅ Running |

### Planned Ports (Not Yet Running)

| Port | Tier | Category | App | Notes |
|------|------|----------|-----|-------|
| 10401 | 04 | agent | director | Study tri-unit Director |
| 10402 | 04 | agent | executor | Study tri-unit Executor |
| 10403 | 04 | agent | guardian | Policy gate validator |
| 10404 | 04 | agent | council | Voting consensus |
| 10501 | 05 | runtime | hermes | Hermes Agent runtime |
| 10801 | 08 | rag | ragflow | RAG engine for PDFs |
| 10802 | 08 | rag | anythingllm | Alternative RAG |
| 10803 | 08 | rag | llamaindex | RAG toolkit |
| 10804 | 08 | kg | obsidian | Knowledge vault |
| 10805 | 08 | rag | r2r | RAG pipeline |
| 10806 | 08 | collab | affine | Collaborative docs |

### Agent HTTP Ports (Pattern)

```
104YY — Agent HTTP health/metrics endpoints
         YY = sequence per domain
         Example: 10411 = study director, 10412 = study executor
```

---

## 7. Root Compose Pattern

### docker-compose.yml (Root)

```yaml
name: jart-os

include:
  # TIER-03 — SERVICES
  - TIERS/TIER-03-SERVICES/10301-msg-redis/docker-compose.yml
  - TIERS/TIER-03-SERVICES/10302-msg-nats/docker-compose.yml

  # TIER-02 — GATEWAY
  - TIERS/TIER-02-GATEWAY/10201-proxy-litellm/docker-compose.yml

  # TIER-07 — INTERFACES
  - TIERS/TIER-07-INTERFACES/10701-web-mission_control/docker-compose.yml
  - TIERS/TIER-07-INTERFACES/10702-web-grafana/docker-compose.yml

  # TIER-09 — CONTROL
  - TIERS/TIER-09-CONTROL/10901-metrics-prometheus/docker-compose.yml

networks:
  jart-os-net:
    name: jart-os-net
    driver: bridge
```

### Conventions

- **`include:` pattern** — each app has its own compose, root just includes them.
- **Shared network:** `jart-os-net` (bridge). All containers join it.
- **No `version:` key** — deprecated in modern Docker Compose.
- **Restart policy:** `unless-stopped` on all services.
- **Environment:** All secrets from root `.env` via `${VAR}` interpolation.
- **Volumes:** Bind mounts only. `./relative/path:/container/path`.

---

## 8. Naming & ID Convention

### ID Format (OPENCLAW-system inherited)

```
LLL-DDD-TTT-SSS-descriptive_name
│││ │││ │││ │││  └── name: lowercase with underscores
│││ │││ │││ └───── SSS: Sequence (001-999)
│││ │││ └──────── TTT: Type (3 letters, UPPERCASE)
│││ └──────────── DDD: Domain code (3 letters, UPPERCASE)
└─────────────── LLL: Level code (3 letters, UPPERCASE)
```

### Level Codes (LLL)

| Code | Level | Number |
|------|-------|--------|
| SIS | System | 0 |
| JEF | Chief (Leadership) | 1 |
| ESP | Specialist | 2 |
| SUB | Sub-agent (ephemeral) | 3 |

### Domain Codes (DDD)

| Code | Domain | Namespace | Chief |
|------|--------|-----------|-------------|
| SMA | System | /system | — |
| BIB | Library | /library | — |
| CON | Knowledge | /academic, /general | CKO |
| ING | Engineering | /dev, /infra | CEngO |
| OPE | Operations | /domain_subject | COO |
| RHU | Human Resources | /fitness | CHO |
| REX | External Relations | /crypto, /investments | CSRO |
| COM | Communications | /languages | CCO |

### Specialist Domain Codes

| Code | Domain | Namespace | Chief |
|------|--------|-----------|------|
| DES | Development | /dev | ING |
| INF | Infrastructure | /infra | ING |
| HOS | Domain Subject | /domain_subject | OPE |
| ACA | Academic | /academic | CON |
| GEN | General | /general | CON |
| CRI | Cryptocurrency | /crypto | REX |
| FIN | Finance | /investments | REX |
| DEP | Sports | /fitness | RHU |
| IDI | Languages | /languages | COM |

### Type Codes (TTT)

| Code | Type | Extension |
|------|------|-----------|
| CFG | Configuration | .yaml |
| UNI | Unit | .yaml |
| DIR | Director | .yaml |
| EJE | Executor | .yaml |
| ARC | Archivist | .yaml |
| CNO | Knowledge | .md |
| MEM | Memory | .db |
| HER | Tools | .yaml |
| PRO | Protocol | .md |
| PLA | Template | .yaml |
| REG | Registry | .yaml |

### Example IDs

```
SIS-SMA-CFG-001-system                    # System config
JEF-ING-UNI-001-engineering                 # CEngO chief unit
ESP-DES-UNI-001-development                 # Dev specialist
ESP-HOS-DIR-001-domain_subject_director        # Domain Subject tri-unit director
ESP-ACA-EXE-001-academic_executor         # Academic tri-unit executor
ESP-OP2-ARC-001-study_archivist      # Study archivist
SUB-DES-HER-001-code_generator             # Ephemeral sub-agent
SIS-BIB-PRO-001-validation                 # Validation protocol
```

### NATS Subject Convention

```
jart-os.<tier>.<domain>.<agent>.<action>

Examples:
  jart-os.04.study.director.command
  jart-os.04.study.director.events
  jart-os.04.study.executor.command
  jart-os.04.study.guardian.checks
  jart-os.04.study.guardian.verdicts
  jart-os.04.study.council.proposals
  jart-os.04.study.council.votes
  jart-os.04.dev.director.command
  jart-os.06.pipeline.ocr.command
  jart-os.06.pipeline.rag.events
```

### Container Naming

```
jart-os-<descriptive_name>

Examples:
  jart-os-redis
  jart-os-nats
  jart-os-litellm
  jart-os-mc
  jart-os-grafana
  jart-os-prometheus
  jart-os-director-opo
  jart-os-executor-opo
  jart-os-guardian
```

---

## 9. MCP Repository Taxonomy

> **Authority:** [MCP-REPOSITORY-TAXONOMY.md](MCP-REPOSITORY-TAXONOMY.md) — Full specification.
> This section is a summary. The linked document is the source of truth.

### Naming Format

```
MCP-{domain}[-{subdomain}]-{suffix}
```

- `MCP-` prefix: **UPPERCASE**. Ecosystem membership.
- `{domain}`: lowercase, hyphenated functional area
- `-{subdomain}`: optional, max 1 level, for disambiguation only
- `-{suffix}`: **mandatory** — one of the 4 registered categories

### Category Registry (4 categories — amendment required for expansion)

| Suffix | Category | Runtime? | Backpack? |
|--------|----------|:--------:|:---------:|
| `-server` | MCP Server — exposes tools/resources/prompts | ✅ | ✅ |
| `-lib` | Shared Library — importable code | ❌ | ❌ |
| `-template` | Scaffolding — generates new repos | ❌ | ❌ |
| `-bridge` | Protocol Bridge — translates between systems | ✅ | ❌ |

### Active Repositories

| Canonical Name | Category | Stack | Status |
|---|---|---|---|
| `MCP-memory-server` | server | Python | Active |
| `MCP-search-server` | server | TypeScript | Active |
| `MCP-core-lib` | lib | TypeScript | Active |
| `MCP-blueprint-template` | template | Python | Active |
| `MCP-gateway-bridge` | bridge | TypeScript | Planned |

### `.jart-os-manifest` Requirement

Every repo MUST include a `.jart-os-manifest` with a `category` field matching its suffix:

```json
{
  "version": "x.y.z",
  "category": "server|lib|template|bridge",
  "stack": "python|typescript|go",
  "compliance": ["mcp", "a2a", "mcp-apps"],
  "depends": ["mcp-core-lib"]
}
```

---

## 10. Network Topology

```
                         ┌──────────────────┐
                         │     INTERNET      │
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │  macOS pf Firewall│  TIER-01
                         │  Tailscale VPN    │
                         └────────┬─────────┘
                                  │
    ┌─────────────────────────────▼─────────────────────────────────┐
    │                    Docker Engine                               │
    │                                                                │
    │   ┌──────────────┐    ┌──────────────┐                       │
    │   │  LiteLLM      │    │  OpenClaw GW  │  TIER-02 GATEWAY     │
    │   │  :10201       │    │  :10202       │                       │
    │   └──────┬───────┘    └──────┬───────┘                       │
    │          │                    │                                │
    │   ┌──────▼───────────────────▼──────┐                        │
    │   │         jart-os-net (bridge)       │                       │
    │   │                                   │                       │
    │   │  ┌────────┐   ┌─────────┐        │                       │
    │   │  │ Redis   │   │  NATS   │        │  TIER-03 SERVICES     │
    │   │  │ :10301  │   │ :10302  │        │                       │
    │   │  └────────┘   └─────────┘        │                       │
    │   │                                   │                       │
    │   │  ┌─────────────────────────────┐  │                       │
    │   │  │      AGENT LAYER            │  │  TIER-04 AGENTS       │
    │   │  │                              │  │                       │
    │   │  │  Director ←→ NATS           │  │                       │
    │   │  │  Executor ←→ NATS           │  │                       │
    │   │  │  Guardian ←→ NATS           │  │                       │
    │   │  │  Council  ←→ NATS           │  │                       │
    │   │  │                              │  │                       │
    │   │  │  All agents ←→ LiteLLM      │  │                       │
    │   │  │  All agents ←→ Redis (state) │  │                       │
    │   │  └─────────────────────────────┘  │                       │
    │   │                                   │                       │
    │   │  ┌────────┐   ┌─────────┐        │                       │
    │   │  │  MC     │   │ Grafana │        │  TIER-07 INTERFACES   │
    │   │  │ :10701  │   │ :10702  │        │                       │
    │   │  └────────┘   └─────────┘        │                       │
    │   │                                   │                       │
    │   │  ┌─────────────────────────────┐  │                       │
    │   │  │       Prometheus            │  │  TIER-09 CONTROL      │
    │   │  │       :10901                │  │                       │
    │   │  └─────────────────────────────┘  │                       │
    │   └───────────────────────────────────┘                       │
    └────────────────────────────────────────────────────────────────┘
                                  │
    ┌─────────────────────────────▼─────────────────────────────────┐
    │                     HOST (TIER-00 METAL)                       │
    │                                                                │
    │   Ollama (:11434)  →  phi4, phi3:mini, qwen2.5:0.5b          │
    │   LM Studio (:1234) →  Models from $AGENT_USER via LM Link         │
    │   pf rules  →  Jart-OS port range allowed via Tailscale       │
    └────────────────────────────────────────────────────────────────┘
```

### Communication Flows

```
1. Agent → LLM:          Agent → LiteLLM (:10201) → Provider (Z.AI/OpenRouter/Ollama)
2. Agent → Agent:        Agent A → NATS (:10302) → Agent B
3. Agent → State:        Agent → Redis (:10301/10301) → Key/Value + PubSub
4. Dashboard → Agent:    Mission Control → NATS → Agent
5. External → Agent:     Telegram/Discord → OpenClaw GW (:10202) → Agent
6. Metrics:              Agent → Prometheus (:10901) ← Grafana (:10702)
```

---

## 10. LLM Routing Strategy

### 3-Layer Model Strategy

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — THINK (20% of usage)                         │
│  Architecture, specs, code review, complex reasoning     │
│                                                          │
│  Models: glm-5, glm-4.7                                  │
│  Provider: Z.AI via api.z.ai/api/coding/paas/v4          │
│  Through: LiteLLM :10201                                  │
│  Cost: ~$160/month (Coding Plan)                          │
├─────────────────────────────────────────────────────────┤
│  LAYER 2 — DO (80% of usage)                           │
│  Execute specs, TDD, bulk generation, pipelines           │
│                                                          │
│  Models: free-gemma4-31b, free-llama33-70b,              │
│          free-nemotron-super, free-qwen3-coder            │
│  Provider: OpenRouter (free tier)                         │
│  Fallback: phi3-local (Ollama offline)                    │
│  Through: LiteLLM :10201                                  │
│  Cost: $0 (free tier, 50 req/day without credit)          │
├─────────────────────────────────────────────────────────┤
│  LAYER 3 — VALIDATE                                        │
│  Pass/fail tests, spec compliance, quick checks           │
│                                                          │
│  Models: mimo-flash, phi3-local                           │
│  Providers: Xiaomi MiMo / Ollama local                    │
│  Through: LiteLLM :10201                                  │
│  Cost: ~$0.09/M tokens (MiMo) / $0 (local)                │
└─────────────────────────────────────────────────────────┘
```

### Model → Role Mapping

| Role | Model | Temperature | Reason |
|------|-------|-------------|--------|
| Director (plan) | glm-5 | 0.7 | Creative decomposition |
| Executor (code) | glm-4.7 / OpenRouter free | 0.3 | Precise execution |
| Guardian (validate) | mimo-flash / phi3-local | 0.1 | Deterministic checks |
| Council (vote) | 3 different models | 0.2 | Diversity of opinion |

### LiteLLM Config Location

```
$JART_OS_HOME/TIERS/TIER-02-GATEWAY/10201-proxy-litellm/config/litellm.yaml
Master key: $LITELLM_MASTER_KEY (set via env var)
Endpoint: http://localhost:10201
```

---

## 11. Agent Architecture

### Base Class

All agents inherit from `AgentBase` in `agents/core/base.py`:

| Feature | Implementation |
|---------|---------------|
| HTTP server | Health (`/health`), metrics (`/metrics`), state (`/state`) |
| LLM calls | Via LiteLLM proxy (`call_llm()` method) |
| Messaging | Redis PubSub (`publish()` / `subscribe()`) → migrating to NATS |
| Metrics | Prometheus format via `/metrics` endpoint |
| Lifecycle | `boot()` → HTTP thread + `run()` abstract method |

### Agent Roles in Tri-Unit

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   DIRECTOR   │───►│   EXECUTOR   │───►│   GUARDIAN   │
│              │     │              │     │              │
│  Plans   │     │  Executes     │     │  Validates      │
│  Decomposes  │     │  Generates      │     │  Verifies    │
│  Delegates      │     │  Reports     │     │  Approves/    │
│  Supervises   │     │              │     │   Rejects    │
│              │     │              │     │              │
│  GLM-5       │     │  GLM-4.7 /   │     │  MiMo Flash  │
│  temp: 0.7   │     │  OpenRouter   │     │  / phi3      │
│              │     │  temp: 0.3    │     │  temp: 0.1   │
└──────────────┘     └──────────────┘     └──────────────┘
         │                   │                     │
         └───────────────── NATS ──────────────────┘
```

### Flow: Task Lifecycle

```
1. Task arrives → NATS subject: jart-os.04.<domain>.director.command
2. Director plans → Publishes N sub-tasks to executor.command
3. Executor executes each sub-task → Sends output to guardian.checks
4. Guardian validates → Returns verdict: PASS ✅ or FAIL ❌
5. If FAIL → Executor retries with feedback (max 3 retries)
6. If PASS ×3 → Director assembles final result
7. Director publishes completion event
```

---

## 12. Communication Backbone (NATS)

### Why NATS (not just Redis)

| Feature | Redis PubSub | NATS JetStream |
|---------|-------------|-----------------|
| Persistence | No (fire & forget) | Yes (replay, durable) |
| Request/Reply | Manual | Built-in |
| Wildcards | No | Yes (`>`, `*`) |
| Backpressure | No | Yes (flow control) |
| Monitoring | Manual | Built-in dashboard |

### NATS Subject Taxonomy

```
jart-os.<tier>.<domain>.<role>.<action>

Tiers: 02 (gateway), 03 (services), 04 (agents), 06 (pipelines), 07 (ui), 09 (control)
Domains: study, dev, infra, domain_subject, academic, languages, fitness, crypto, general
Roles: director, executor, guardian, council, pipeline, system
Actions: command, event, query, verdict, vote, proposal, check, status

Wildcards:
  jart-os.04.>               → All agent messages
  jart-os.04.study.>   → All study domain messages
  jart-os.*.director.command → All director commands across domains
```

### Message Envelope (Standard)

```json
{
  "task_id": "OP2-2026-TEM3-001",
  "from": "director-study",
  "to": "executor-study",
  "timestamp": "2026-04-11T12:00:00Z",
  "priority": "normal",
  "retry_count": 0,
  "max_retries": 3,
  "timeout_seconds": 120,
  "payload": {
    "objective": "Generate summary for topic 3",
    "spec": { ... },
    "success_criteria": [ ... ],
    "model_hint": "glm-4.7",
    "context": { ... }
  }
}
```

### Redis Role (State, Not Messaging)

| Use | Key Pattern | Example |
|-----|-------------|---------|
| Task state | `jart-os:task:<task_id>` | `{status, agent, started_at, ...}` |
| Agent heartbeat | `jart-os:agent:<role>` | `{status, uptime, tasks_completed}` |
| Locks | `jart-os:lock:<resource>` | Distributed mutex |
| Cache | `jart-os:cache:<query_hash>` | LLM response cache |
| Rate limit | `jart-os:ratelimit:<agent>` | Token bucket counter |

---

## 13. Memory Architecture

```
┌─────────────────────────────────────────────────────┐
│                 MEMORY STACK (5 layers)              │
│                                                      │
│  1. AGENT       → LanceDB (per-agent context)        │
│  2. UNIT        → SQLite (tri-unit session history)   │
│  3. DOMAIN      → Qdrant "opo" (domain knowledge)    │
│  4. GLOBAL      → Qdrant "global" (ADRs, lessons)    │
│  5. RAG         → Qdrant "study" (ingested PDFs)│
│                                                      │
│  Query order: Agent → Domain → Global → RAG → LLM   │
└─────────────────────────────────────────────────────┘
```

| Layer | Backend | Scope | Content |
|-------|---------|-------|---------|
| Agent | LanceDB | Single agent | Decisions, context, preferences |
| Unit | SQLite | Tri-unit session | Collaboration history, outputs |
| Domain | Qdrant collection | One domain | Domain-specific knowledge |
| Global | Qdrant collection | System-wide | ADRs, architecture lessons, protocols |
| RAG | Qdrant collection | Ingested docs | 872 PDFs, 1695 photos, 18 video transcripts |

---

## 14. Policy Gates & Governance

### 3 Enforcement Layers

```
┌─────────────────────────────────────────────────────────┐
│  LAYER A: Spec Gate (Pre-execution)                      │
│  Every task MUST have: task_id, objective, criteria,     │
│  max_retries, timeout. No ambiguous terms.               │
│  Location: agents/policies/spec-gate.yaml                │
├─────────────────────────────────────────────────────────┤
│  LAYER B: Quality Gate (Post-execution)                  │
│  Guardian validates: completeness ≥ 0.8, accuracy ≥ 0.9, │
│  format = 1.0. On fail: retry with feedback (max 3).     │
│  Escalation to council after max retries.                 │
│  Location: agents/policies/quality-gate.yaml              │
├─────────────────────────────────────────────────────────┤
│  LAYER C: Audit Trail (Always)                           │
│  Every task logged: agent, model, tokens, duration,      │
│  verdict, retry_count, timestamps. Stored in Redis/PG.   │
│  Location: Redis keys jart-os:audit:<task_id>             │
└─────────────────────────────────────────────────────────┘
```

### Consensus Rules

| Type | Threshold | When |
|------|-----------|------|
| Normal | 66% (2/3) | Regular tasks |
| Critical | 100% (3/3) | Exam answers, legal compliance, production deploys |
| Guardian veto | 1/1 | Can block ANY task regardless of consensus |

### Council (Tri-Unit Review)

| Reviewer | Domain | Rejects when |
|----------|--------|-------------|
| Legal | Regulatory framework | Missing regulation reference |
| Standards | Quality guidelines | Misaligned with standards |
| Technical | Hospitality | Factually wrong content |

---

## 15. Domain Map

### Active Domains

| Domain | Namespace | Chief | Primary Use |
|--------|-----------|-------------|-------------|
| **Study** | `/study` | CKO | Technical learning and documentation (PRIORITY #1) |
| **Development** | `/dev` | CEngO | Jart-OS self-maintenance |
| **Infrastructure** | `/infra` | CEngO | System ops, DevOps |

### Dormant Domains

| Domain | Namespace | Chief | Wake When |
|--------|-----------|-------------|-----------|
| Domain Subject | `/domain_subject` | COO | Practical exam prep starts |
| Academic | `/academic` | CKO | Parallel study needed |
| Languages | `/languages` | CCO | Active language study |
| Fitness | `/fitness` | CHO | Health integration |
| Crypto | `/crypto` | CSRO | Finance management |
| Investments | `/investments` | CSRO | Portfolio management |
| General | `/general` | CKO | Default fallback |

---

## 16. Chief Map

| Chief | Code | Leadership ID | Active Domains | Model |
|-------------|------|-------------|----------------|-------|
| CKO (Chief Knowledge Officer) | `CKO` | JEF-CON-UNI-001 | /study, /academic, /general | GLM-5 |
| CEngO (Chief Engineering Officer) | `CEngO` | JEF-ING-UNI-001 | /dev, /infra | GLM-5 |
| COO (Chief Operations Officer) | `COO` | JEF-OPE-UNI-001 | /domain_subject | GLM-5 |
| CCO (Chief Communications Officer) | `CCO` | JEF-COM-UNI-001 | /languages | Dormant |
| CHO (Chief Health Officer) | `CHO` | JEF-RHU-UNI-001 | /fitness | Dormant |
| CSRO (Chief Strategy & Risk Officer) | `CSRO` | JEF-REX-UNI-001 | /crypto, /investments | Dormant |

---

## 17. Tri-Unit Pattern

### Structure (from OPENCLAW-system, canonicalized)

Every specialist domain has one or more **tri-units** (Director + Executor + Archivist/Guardian):

```yaml
# Template: ESP-{DDD}-UNI-001-{name}.yaml
id: ESP-OP2-UNI-001-study
name: "Study Unit"
namespace: /study

tri-agent:
  pattern: triumvirate
  director: ESP-OP2-DIR-001-director
  executor: ESP-OP2-EXE-001-executor
  archivist: ESP-OP2-ARC-001-archivist

director:
  role: "Strategic Planner"
  model: glm-5
  temperature: 0.7
  
executor:
  role: "Technical Executor"
  model: glm-4.7
  temperature: 0.3

archivist:
  role: "Validator and Archivist"
  model: mimo-flash
  temperature: 0.1
```

### Study Tri-Units (Planned)

| Unit | Director | Executor | Guardian |
|------|----------|----------|----------|
| **Writer** | Structure syllabus | Generate content | Validate accuracy |
| **Researcher** | Define search | Find sources | Verify citations |
| **Examiner** | Design tests | Generate questions | Grade answers |
| **Oral Coach** | Plan defense | Simulate panel | Evaluate response |

---

## 18. Study Domain — 5 Blocks

```
┌─────────────────────────────────────────────────────────┐
│  BLOCK 1: CONTENT PIPELINE                               │
│  872 PDFs + 1695 photos + 18 videos → Qdrant RAG       │
│  Pipeline: OCR → Text → Chunk → Embed → Vector Store    │
│  TIER-06: PROCESSES handles this                         │
├─────────────────────────────────────────────────────────┤
│  BLOCK 2: SYLLABUS DESIGN                                │
│  18 video guides → Programming template → Syllabus       │
│  Quality validation: Technical accuracy and best practices     │
├─────────────────────────────────────────────────────────┤
│  BLOCK 3: KNOWLEDGE ASSESSMENT                             │
│  34 topics → Explanations + Summaries + Flashcards       │
│  Knowledge check → Question generation + Grading           │
├─────────────────────────────────────────────────────────┤
│  BLOCK 4: PRACTICAL SKILLS                               │
│  Technical procedures → Protocols + Checklists            │
│  Setup configurations → Standards documentation           │
├─────────────────────────────────────────────────────────┤
│  BLOCK 5: COMMUNICATION SKILLS                            │
│  Presentation simulator → Questions + Evaluation          │
│  Timer → 1-hour practice sessions                        │
│  Feedback → Improvement points                           │
└─────────────────────────────────────────────────────────┘
```

### Content Pipeline Detail

| Source | Count | Tool | Output |
|--------|-------|------|--------|
| PDFs | 872 | PyMuPDF / Vision API | Text + chunks |
| Photos (CEDE) | 1,695 | Vision Model OCR | Text by topic |
| Videos | 18 | ffmpeg + Whisper large-v3 | Structured guides |
| All combined | ~2,585 | Chunking (512 tok, overlap 50) | Qdrant vectors |

---

## 19. Service Inventory (Live)

### Running (as of 2026-04-11)

| Container | Image | TIER | Port | Status |
|-----------|-------|------|------|--------|
| jart-os-redis | redis:7-alpine | 03 | 10301 | ✅ Healthy |
| jart-os-nats | nats:latest | 03 | 10302-04 | ✅ Up 8h+ |
| jart-os-litellm | ghcr.io/berriai/litellm:main-latest | 02 | 10201 | ✅ Up |
| jart-os-mc | nginx:alpine | 07 | 10701 | ✅ Up 8h+ |
| jart-os-grafana | grafana/grafana | 07 | 10702 | ✅ Up 8h+ |
| jart-os-prometheus | prom/prometheus | 09 | 10901 | ✅ Up 8h+ |

### Models Active via LiteLLM

| Model Name | Provider | Status |
|------------|----------|--------|
| glm-5 | Z.AI | ✅ Working |
| glm-4.7 | Z.AI | ✅ Working |
| phi3-local | Ollama | ✅ Working |
| free-gemma4-31b | OpenRouter | 🔴 Key expired |
| free-llama33-70b | OpenRouter | 🔴 Key expired |
| free-nemotron-super | OpenRouter | 🔴 Key expired |
| free-qwen3-coder | OpenRouter | 🔴 Key expired |
| mimo-flash | Xiaomi MiMo | 🔴 Key expired |
| mimo-plan | Xiaomi MiMo | 🔴 Key expired |

### Local Models (Ollama on $JART_OS_USER)

| Model | Size | Status |
|-------|------|--------|
| phi4:latest | 9.1GB | Available |
| phi3:mini | 2.2GB | Available |
| qwen2.5:0.5b | ~500MB | Available |
| llama3.2:1b | ~1.3GB | Available |

---

## 20. Stack Summary

| Component | Technology | Version/Notes |
|-----------|------------|---------------|
| Orchestration | Docker Compose | v5.1.1, `include:` pattern |
| Cache / State | Redis 7 Alpine | :10301 |
| Event Bus | NATS JetStream | :10302 (command: --jetstream) |
| Vector DB | Qdrant | Inside RAG apps (TIER-08) |
| LLM Gateway | LiteLLM | :10201, 9 models configured |
| Agent Gateway | OpenClaw | :10202 (planned) |
| Agent Runtime | Hermes v0.7 | 47 tools, skills, memory |
| Agent Base | Python (own) | `agents/core/base.py` |
| LLM Primary | Z.AI GLM-5 / GLM-4.7 | api.z.ai |
| LLM Free | OpenRouter free tier | Various large models |
| LLM Validation | Xiaomi MiMo Flash | Cheap pass/fail |
| LLM Local | Ollama phi4 / phi3 | Offline fallback |
| Observability | Prometheus | :10901 |
| Dashboard | Grafana + Mission Control | :10702 + :10701 |
| Boot Manager | bash script | scripts/boot.sh |
| VPN | Tailscale | Mesh between Macs |
| Remote Models | LM Studio + LM Link | $JART_OS_USER ↔ $AGENT_USER |

---

## 21. Boot & Operations

### boot.sh Commands

```bash
./scripts/boot.sh start      # docker compose up -d
./scripts/boot.sh stop       # docker compose down
./scripts/boot.sh restart    # docker compose restart
./scripts/boot.sh status     # Show all services + health checks
./scripts/boot.sh logs [svc] # Follow logs (optional service name)
```

### Manual Operations

```bash
# Recreate a single service (after config change)
cd $JART_OS_HOME
docker compose up -d --force-recreate <service>

# View LiteLLM models
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://localhost:10201/models

# Test NATS connectivity
docker exec jart-os-nats nats pub test "hello from jart-os"

# Check Redis
docker exec jart-os-redis redis-cli -p 6379 ping

# Agent health check (when agents are running)
curl http://localhost:104YY/health
```

### File Write Permissions

When running as `$AGENT_USER`, use `sudo` to modify files owned by `$JART_OS_USER`:

```bash
sudo bash -c 'cat > /path/to/file << EOF
content
EOF'
sudo chown $JART_OS_USER:staff /path/to/file
```

---

## 22. Open Decisions

These items need resolution before implementation:

### 🔴 Critical (Blocking)

| # | Decision | Options | Impact |
|---|----------|---------|--------|
| D1 | **API Keys: OpenRouter + Xiaomi** | Get new keys or go local-only | Blocks 6 of 9 models |
| D2 | **Agent Runtime: Hermes vs Custom** | Use Hermes v0.7 as-is OR build from AgentBase | Affects TIER-04 & 05 |
| D3 | **Message Bus: Redis vs NATS** | Current base.py uses Redis. Architecture says NATS. Choose ONE. | Affects all inter-agent comms |

### 🟡 Important (Not Blocking)

| # | Decision | Options | Impact |
|---|----------|---------|--------|
| D4 | **RAG Engine** | RAGFlow vs AnythingLLM vs LlamaIndex vs R2R | Affects TIER-08 |
| D5 | **Secret Management** | Infisical vs .env files vs Docker secrets | Affects TIER-01 |
| D6 | **Team Communication** | Telegram vs Discord vs Mission Control only | Affects how team interacts |
| D7 | **~30 Agent Architecture** | Inspired by opencode-hermes-multiagent (17 agents) | How many agents, which domains |
| D8 | **Mission Control** | Replace static HTML with builderz-labs/mission-control | Better dashboard |

### 🟢 Nice to Have

| # | Decision | Options | Impact |
|---|----------|---------|--------|
| D9 | **LM Studio integration** | Add LM Link endpoint to LiteLLM | More local models |
| D10 | **Backup strategy** | rsync, Time Machine, or git-based | Data safety |
| D11 | **CI/CD** | GitHub Actions or local only | Code quality |
| D12 | **PostgreSQL** | Activate TIER-08 or skip for now | Audit trail storage |

---

## 23. Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-04-09 | 1.0.0 | Initial ARCHITECTURE.md created |
| 2026-04-09 | 2.0.0 | Consolidated from 8 Jart-OS variants |
| 2026-04-10 | 2.1.0 | LiteLLM fixed (api.z.ai), .env populated, permissions resolved |
| 2026-04-11 | 3.0.0 | CANONICAL SPEC — unified from: ARCHITECTURE.md + JART-OS-BASE-Y-CASCARA + SISTEMA-STUDY + MIX-CHECKLIST + MIX-9-LEVELS + OPENCLAW-system YAMLs + session decisions |

---

*Document generated by architecture session on 2026-04-11.*
*All team members and CLIs should reference THIS document as single source of truth.*
*Historical documents remain in $STUDY_DATA_DIR/PROJECT-Jart-OS/ for reference only.*

---

## 24. Decisions Log (Resolved 2026-04-11)

### D1: API Keys — RESOLVED
- **Decision:** User manages keys personally. Pass to agent when needed.
- **Storage:** 1Password (primary) + `.env` (runtime injection via `op` CLI)
- **Action:** No changes needed to architecture.

### D2: Agent Runtime — RESOLVED
- **Decision:** Build from **AgentBase** (`agents/core/base.py`) as canonical runtime.
- **Supplementary:** OpenClaw, Hermes, or any SOTA agent framework as optional layers (TIER-05).
- **Rationale:** AgentBase is tailored to Jart-OS conventions (Tiers, ports, NATS). External frameworks add capabilities on top.
- **Pattern:** AgentBase (foundation) → Hermes skills (capabilities) → OpenClaw gateway (channels)

### D3: Message Bus — RESOLVED → NATS
- **Decision:** **NATS JetStream** for ALL inter-agent and inter-service messaging.
- **Redis role:** State, cache, locks, rate-limiting ONLY. Not messaging.
- **Rationale:** NATS provides persistence (JetStream), request/reply, wildcards, flow control. Redis PubSub is fire-and-forget.
- **Rule:** EVERY message between components goes through NATS. No exceptions.

### D4: RAG Engine — RESOLVED → LlamaIndex + RAGFlow
- **Decision:** **LlamaIndex** as primary RAG engine (TIER-06 pipeline). **RAGFlow** as exploration UI (TIER-08).
- **Multimodal:** LlamaIndex handles PDFs (text + scanned via Vision), photos (Vision API OCR), video transcripts (Whisper).
- **Vector store:** Qdrant collection "study" (shared backend).
- **Agent access:** Python API direct from AgentBase.
- **User access:** RAGFlow web UI for exploration and search.
- **Pathway:** Rejected — designed for real-time data ETL, not conversational RAG.
- **AnythingLLM:** Simpler but less flexible. Can add later if needed.

### D5: Secret Management — RESOLVED → 1Password
- **Decision:** **1Password** with `op` CLI for secret injection.
- **Flow:** `op run -- boot.sh start` → env vars injected from 1Password vault.
- **No Infisical needed.** User already has 1Password running and prefers zero manual config.
- **Fallback:** `.env` file for non-secret config (ports, hostnames, feature flags).

### D6: Team Communication — RESOLVED → Telegram primary
- **Decision:** Telegram as primary notification/interaction channel (via OpenClaw).
- **Mission Control** as operational dashboard.
- **Discord** as optional secondary channel.

### D7: Agent Count — RESOLVED → Start with 12, scale to 30+
- **Phase 1 (MVP):** 4 agents (Director + Executor + Guardian + Council) for study.
- **Phase 2:** Add tri-units per domain as needed.
- **Phase 3:** Scale to full 30+ when hardware/meta demands it.
- **Pattern:** Spin up agents on demand. Dormant = zero RAM.

### D8: Mission Control — RESOLVED → Real (builderz-labs)
- **Decision:** **builderz-labs/mission-control** as the real dashboard.
- **Replace:** Current static HTML at :10701.
- **Features needed:** Workflows, pipelines, task boards, agent monitoring, study tracker, email/calendar integration, personal assistant UI.
- **Status:** Code exists in hermes-agent repo. Needs deployment to TIER-07.

### D9-D12: Nice to have — DEFERRED
- LM Studio integration, backup strategy, CI/CD, PostgreSQL activation.
- Will be addressed when needed.

---

## 25. Implementation Roadmap (Updated)

### Phase 0 — Infrastructure ✅ (Complete)
- [x] 10 TIER structure with autocontained apps
- [x] LiteLLM proxy with Z.AI GLM-5/GLM-4.7 working
- [x] Redis + NATS running stable
- [x] Prometheus + Grafana monitoring
- [x] boot.sh operational manager
- [x] AgentBase class created
- [x] CANONICAL SPEC document

### Phase 1 — Agent Core (Next)
- [ ] Migrate AgentBase messaging from Redis PubSub to NATS
- [ ] Implement Director agent (study)
- [ ] Implement Executor agent (study)
- [ ] Implement Guardian agent (policy gates)
- [ ] Implement Council agent (voting)
- [ ] Policy gate YAML files (spec-gate, quality-gate)
- [ ] NATS subject schema deployment

### Phase 2 — Knowledge Pipeline
- [ ] LlamaIndex pipeline for PDF ingestion (872 PDFs)
- [ ] Vision API pipeline for CEDE photos (1695)
- [ ] Whisper pipeline for video transcription (18)
- [ ] Qdrant collection "study" with embeddings
- [ ] RAGFlow deployment for exploration UI

### Phase 3 — Study Domain
- [ ] Content pipeline tests (Block 1)
- [ ] Syllabus generator (Block 2)
- [ ] Theoretical exam simulator (Block 3)
- [ ] Practical exam protocols (Block 4)
- [ ] Oral defense panel simulator (Block 5)

### Phase 4 — Mission Control + Integrations
- [ ] Deploy builderz-labs/mission-control
- [ ] Configure workflows for study tracking
- [ ] Email/calendar integration
- [ ] Telegram bot via OpenClaw
- [ ] Personal assistant workflows

### Phase 5 — Scale
- [ ] Additional domains (/dev, /infra, /domain_subject)
- [ ] 1Password `op` CLI integration in boot.sh
- [ ] Backup strategy
- [ ] PostgreSQL activation for audit trail
