# MCP and Agent Skills Specifications Research

**Research Date:** 2026-04-06  
**Sources:** Official specifications and trusted aggregators

---

## 1. Model Context Protocol (MCP) Specification

### Overview
The Model Context Protocol (MCP) is an open protocol that enables seamless integration between LLM applications and external data sources and tools. It was introduced by Anthropic in November 2024 and uses **JSON-RPC 2.0** messages for communication.

### Architecture Components

| Component | Description |
|-----------|-------------|
| **Hosts** | LLM applications that initiate connections |
| **Clients** | Connectors within the host application |
| **Servers** | Services that provide context and capabilities |

### Core Features (Server-to-Client)

| Feature | Description |
|---------|-------------|
| **Resources** | Context and data for the user or AI model to use |
| **Prompts** | Templated messages and workflows for users |
| **Tools** | Functions for the AI model to execute |

### Client-to-Server Features

| Feature | Description |
|---------|-------------|
| **Sampling** | Server-initiated agentic behaviors |
| **Roots** | Inquiries into filesystem boundaries |
| **Elicitation** | Requests for additional information from users |

### Transport Mechanisms

#### 1. stdio Transport
- Client launches MCP server as a subprocess
- Server reads JSON-RPC messages from `stdin`
- Server sends messages to `stdout`
- Messages are newline-delimited JSON-RPC
- Server may write UTF-8 strings to `stderr` for logging

#### 2. Streamable HTTP Transport (2025-11-25)
- Server operates as independent process
- Handles multiple client connections
- **POST**: Send JSON-RPC messages to MCP endpoint
- **GET**: Open Server-Sent Events (SSE) stream
- Uses `MCP-Session-Id` header for session management
- Uses `MCP-Protocol-Version` header for versioning
- **Security**: Must validate `Origin` header to prevent DNS rebinding
- **Resumability**: Supports `Last-Event-ID` header for connection resumption

### Protocol Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Initialization│ ──▶ │  Operation  │ ──▶ │  Shutdown   │
└─────────────┘     └─────────────┘     └─────────────┘
```

#### 1. Initialization Phase
1. Client sends `initialize` request with:
   - Supported protocol version
   - Client capabilities (`roots`, `sampling`)
   - Implementation information
2. Server responds with:
   - Negotiated protocol version
   - Server capabilities (`prompts`, `resources`, `tools`)
   - Implementation information
3. Client sends `initialized` notification
4. Normal operations begin

#### 2. Operation Phase
- Normal protocol communication
- Both parties respect negotiated version
- Only use successfully exchanged capabilities

#### 3. Shutdown Phase
- **stdio**: Client closes input stream, waits for server exit
- **HTTP**: Close associated HTTP connections

### Current Specification Version
- **Latest**: 2025-11-25 (November 2025 anniversary release)
- **Previous**: 2025-06-18, 2025-03-26, 2024-11-05

---

## 2. Agent Skills Specification

### Overview
Agent Skills is a simple, open format for giving AI agents new capabilities and expertise. Skills are folders of instructions, scripts, and resources that agents can discover and use.

**Philosophy**: Write once, use everywhere.

### Directory Structure

```
skill-name/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
├── assets/           # Optional: templates, resources
└── ...               # Any additional files
```

### Progressive Disclosure Model

| Level | Content | Token Load |
|-------|---------|------------|
| Metadata | YAML frontmatter only | ~100 tokens |
| Instructions | Full SKILL.md content | On activation |
| Resources | scripts/, references/, assets/ | On demand |

### SKILL.md Format

```markdown
---
name: skill-name
# Required fields
name: my-skill                    # 1-64 chars, lowercase, numbers, hyphens
description: What the skill does  # 1-1024 chars

# Optional fields
license: MIT
compatibility: Requires Python 3.10+
metadata:
  author: developer-name
  version: 1.0.0
allowed-tools: Bash(git:*) Bash(jq:*) Read  # Experimental
---

# Skill Instructions

[Markdown content with steps, examples, edge cases]
```

### Required Fields

| Field | Constraints |
|-------|-------------|
| `name` | 1-64 chars, lowercase `a-z`, numbers, hyphens only. Cannot start/end with hyphen. Must match directory name. |
| `description` | 1-1024 chars. Should include keywords for discoverability. |

### Optional Fields

| Field | Description |
|-------|-------------|
| `license` | License name or reference to bundled license file |
| `compatibility` | Environment requirements (1-500 chars) |
| `metadata` | Arbitrary key-value map for additional properties |
| `allowed-tools` | Space-delimited list of pre-approved tools (Experimental) |

### Content Guidelines
- Keep instructions concise: **< 5000 tokens or 500 lines**
- Move detailed reference material to `references/` directory
- Use `scripts/` for self-contained executable code with helpful error messages

### Validation
- Use `skills-ref` library to validate frontmatter and naming conventions

---

## 3. Trusted Aggregators and Marketplaces

### Smithery.ai

| Attribute | Value |
|-----------|-------|
| **Type** | Registry, Host, and Marketplace |
| **URL** | https://smithery.ai |
| **Description** | Central hub for MCP servers and Agent Skills |
| **Features** | One-click install, OAuth handling, persistent sessions, CLI tools |
| **Size** | 7,300+ tools and extensions |
| **Services** | Hosting, deployment, discovery, credential management |

**Key Capabilities:**
- Single gateway for secure external service access
- Automatic OAuth and credential management
- CLI for discovery and installation: `smithery install <server>`
- Hosting infrastructure for MCP servers

### Glama.ai

| Attribute | Value |
|-----------|-------|
| **Type** | MCP Directory + Gateway |
| **URL** | https://glama.ai/mcp/servers |
| **Description** | Largest public index of MCP servers |
| **Size** | 6,500+ servers (20,000+ indexed with security grades) |
| **Features** | Security grading (A/B/C/F), direct connection without local install |

**Key Capabilities:**
- Massive discovery engine
- Security-graded servers
- Direct connection to remote servers
- MCP chat interface for testing

### Additional Registries

| Registry | URL | Notes |
|----------|-----|-------|
| MCP Market | https://mcpmarket.com | Curated MCP servers for Claude, Cursor |
| mcp.so | https://mcp.so | MCP server directory |
| lobehub.com | https://lobehub.com/mcp | MCP marketplace with skill support |
| PulseMCP | Various | 5,000+ servers, lacks reviews |

---

## 4. Official Documentation Sources

### MCP Official Sources

| Source | URL |
|--------|-----|
| Introduction | https://modelcontextprotocol.io/introduction |
| Specification (Latest) | https://modelcontextprotocol.io/specification/2025-11-25 |
| Transports | https://modelcontextprotocol.io/specification/2025-11-25/basic/transports |
| Lifecycle | https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle |
| Clients | https://modelcontextprotocol.io/clients |
| Security Best Practices | https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices |
| Registry | https://registry.modelcontextprotocol.io |
| Blog | https://blog.modelcontextprotocol.io |
| GitHub | https://github.com/modelcontextprotocol/modelcontextprotocol |

### Agent Skills Official Sources

| Source | URL |
|--------|-----|
| Home | https://agentskills.io/home |
| Specification | https://agentskills.io/specification |
| Client Implementation | https://agentskills.io/client-implementation/adding-skills-support |
| GitHub | https://github.com/agentskills/agentskills |

---

## 5. Key Differences: MCP vs Agent Skills

| Aspect | MCP | Agent Skills |
|--------|-----|--------------|
| **Purpose** | Protocol for LLM-to-tool communication | Format for packaging agent capabilities |
| **Communication** | JSON-RPC 2.0 over stdio/HTTP | File-based (SKILL.md + resources) |
| **Runtime** | Active server process | Passive files loaded by agent |
| **Discovery** | Registry/marketplace | Directory scanning, marketplace |
| **Scope** | Tools, resources, prompts | Instructions, scripts, references |
| **State** | Stateful connections | Stateless (context-loaded) |
| **Initiative** | Bidirectional (sampling) | Agent-driven activation |

---

## 6. Implementation Considerations for MCP Hub Bridge

### Security Pipeline Requirements
1. **Provenance Checks**: Official vs community source verification
2. **Static Analysis**: Secrets, vulnerabilities, suspicious patterns
3. **License Checks**: Compatibility and compliance
4. **MCP-Specific Checks**: Transport security, capability validation
5. **Dynamic Sandbox**: Runtime behavior analysis
6. **Policy Decisions**: Approve/quarantine/reject/manual-review

### Catalog Entity Types
- MCP Server (artifact with tools/resources/prompts)
- MCP Tool (individual function)
- MCP Resource (data context)
- MCP Prompt (templated message)
- Skill (SKILL.md package)
- Skill Script (executable code)
- Skill Reference (documentation)

### Status Lifecycle
```
discovered → quarantined → approved/rejected → deprecated → archived
```

---

## Summary

MCP provides the **protocol layer** for real-time bidirectional communication between AI applications and tools, while Agent Skills provides the **packaging format** for modular agent capabilities. Both are complementary and can be used together - an MCP server could expose Agent Skills, or an agent with skills could connect to MCP servers.

The ecosystem has matured significantly since MCP's November 2024 launch, with multiple trusted aggregators (Smithery, Glama) providing thousands of servers and tools. The 2025-11-25 MCP specification represents the current standard with Streamable HTTP transport replacing the older HTTP+SSE approach.
