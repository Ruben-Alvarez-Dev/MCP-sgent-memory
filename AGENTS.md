# Repository operating rules

These instructions apply to the complete `MCP-agent-memory` repository.

## Authority and communication

- Communicate with Rubén in Spanish. Write code, specifications, schemas,
  documentation, configuration, evidence, changelogs, and commits in professional
  English.
- Follow the parent workspace governance, `openspec/AGENTS.md`, and the active
  approved change. Direct user instructions outrank normalized project guidance.
- Treat legacy documentation and branches as evidence, not automatically as
  current authority.

## Truth and scope

- Do not claim behavior without executable evidence tied to a commit and
  environment.
- Use two independent evidence paths for consequential claims.
- Never use production memory, credentials, or personal content as test data.
- Preserve unrelated work. Stop before destructive, production, secret,
  permission, deployment, merge, or out-of-plan actions.

## Spec-Driven engineering

- A behavior change requires an approved OpenSpec change containing proposal,
  spec delta, design, test plan, tasks, and iteration evidence.
- Use Red → Green → Refactor for domain rules, policy, authorization, lifecycle,
  and regressions. Use contract-first, migration-first, or evaluation-first when
  those represent the actual risk more faithfully.
- Apply SOLID, DRY, Clean/Hexagonal Architecture, deny-by-default authorization,
  typed failures, explicit data structures, and one composition root.
- Domain and policy code must not depend on MCP, HTTP, PostgreSQL, Qdrant, NATS,
  model runtimes, environment variables, clocks, UUID generators, or filesystems.
- Test doubles and sanitized fixtures are allowed only inside tests. Real-component
  integration is mandatory before release claims.

## Identity and memory safety

- Never trust tenant, user, agent, session, task, or scope authority from request
  payloads. Payload fields may narrow an authenticated `IdentityContext`; they may
  never widen it.
- Missing or invalid identity, scope, policy, or plaza evidence is denied. There is
  no implicit `shared`, `default`, or `current` authority.
- PostgreSQL metadata/journal and governed object storage are authoritative.
  Qdrant and SQLite are reconstructible indexes or edge caches.
- Promotion creates a governed derived version with lineage. It never mutates a
  private memory into a broader scope.
- Raw memory content is excluded from general telemetry, T9, UCO, and audit hashes.

## Git and verification

- Use granular Conventional Commits with a two-to-four sentence English body.
- Commit only complete logical units after applicable checks pass. Push only when
  the active approval explicitly authorizes it.
- Before every commit, verify branch, root, diff, tests, generated artifacts,
  secrets, and remote. Never mix baseline debt cleanup into a focused change.
