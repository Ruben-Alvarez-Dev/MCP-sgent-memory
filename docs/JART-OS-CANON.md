# THE JART-OS CANON
## Systematic Framework for Anthropic-Canonical AI Infrastructure

### 1. Foundational Standards (The Sources of Truth)
Jart-OS development is strictly governed by the following official specifications. No deviation is permitted.

#### A. Model Context Protocol (MCP)
- **Source**: [Anthropic Official Spec](https://modelcontextprotocol.io/)
- **Implementation**: Every Jart-OS server must implement the standard JSON-RPC 2.0 interface, exposing **Tools**, **Resources**, and **Prompts**.
- **Requirement**: Use the official `@modelcontextprotocol/sdk` (TypeScript) or `mcp` (Python) packages.

#### B. Agent-to-Agent (A2A) Protocol
- **Source**: [Anthropic A2A Messaging Specification](https://github.com/anthropics/anthropic-sdk-python) (Latest Research/Prod Releases)
- **Implementation**: Asynchronous capability negotiation and task delegation.
- **Requirement**: Support for **UUID v7** message tracking and cross-agent handshakes.

#### C. MCP Apps (Interactive Ecosystem)
- **Source**: [MCP App SDK Documentation](https://github.com/modelcontextprotocol/app-sdk)
- **Implementation**: Exposure of interactive UIs through App-type resources.
- **Requirement**: Scaffolding must include an optional `ui/` directory for React-based server dashboards.

#### D. Twelve-Factor App Methodology (Agent Adaptation)
- **Source**: [12factor.net](https://12factor.net/)
- **Adaptation**: Strict environment isolation, stateless processes (where possible), and log-as-event-streams.

---

### 2. Architectural Rules (The Corporate Guide)

#### I. Total Self-Containment (The Sandbox)
Every server must reside in `~/MCP-servers/MCP-[DOMAIN]-[NAME]-server/`.
- Must contain its own `.venv/`.
- Must contain its own `bin/` (external binaries).
- Must contain its own `data/` and `logs/`.
- **PROHIBITION**: No global dependencies (brew, npm -g, etc.) are allowed.

#### II. 100% Production Reality (The No-Mock Policy)
- Mock data, hardcoded demos, or unverified technical claims are **FORBIDDEN**.
- All benchmarks must be performed against running binaries.
- All code must be production-ready from the first commit.

#### III. Documentation & TDD
- Every new feature must start with a **SPEC-[ID]** document in English.
- Every SPEC must have a corresponding laboratory test (`tests/lab_*.py`).

---

### 3. Scaffolding Pattern (The Jart-Blueprint)
```text
/MCP-XXXX-server/
├── bin/            # Self-contained binaries
├── config/         # Environment variables and manifests
├── data/           # Persistent local state (DBs)
├── docs/           # Specifications and Canon compliance
├── src/            # Source code (Canonical MCP/A2A)
│   ├── protocol/   # Handshake and Messaging logic
│   ├── tools/      # Official MCP Tools
│   ├── apps/       # MCP Apps (UI resources)
│   └── main.py     # Entrypoint
├── scripts/        # Standardized Installer and Lifecycle
├── tests/          # Laboratory Benchmarks
└── .jart-manifest  # Framework compliance fingerprint
```
