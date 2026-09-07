# Capability: isolation (delta M4)

## MODIFIED Requirements

### Requirement: ISO-01 Identity is harness-asserted, not caller-supplied (was: KNOWN WEAKNESS)
The system SHALL bind agent identity at server boot from harness-provided
credentials (`MEMORY_AGENT_ID` + `MEMORY_AGENT_TOKEN`) verified against the
agent registry. In `strict` mode, a server SHALL refuse to boot without valid
credentials. In `bound` mode, every scope-touching tool call SHALL resolve its
effective scope through `Identity.assert_agent`: the bound scope, `shared`, or
the documented `default` coercion — any other caller-supplied scope SHALL be
rejected with `ScopeError` BEFORE any I/O (enforcement point: identity.py
assert_agent called at tool entry; tests: tests/adversarial/test__M4__identity.py).

#### Scenario: Spoofed agent rejected at tool entry
- GIVEN a server bound to `director-1` (strict)
- WHEN a tool is called with `agent_id="engineer-1"`
- THEN `ScopeError` is raised, zero storage I/O occurs, and no data from
  `engineer-1` is reachable.

#### Scenario: Open mode is explicit and observable
- GIVEN `MEMORY_IDENTITY_MODE` unset (default `open`)
- WHEN the server boots
- THEN a WARN is logged, `health_check` reports `identity.mode="open"`, and
  scope parameters remain shape-validated (legacy behavior).

## ADDED Requirements

### Requirement: ISO-13 Agent registry with hash-only token storage (ADDED)
The system SHALL maintain a registry (`data/agents.json`, mode 0600) mapping
each `agent_id` to the SHA-256 of its credential token. Plaintext tokens SHALL
be displayed exactly once at registration and never stored or logged.
Verification SHALL be constant-time (`hmac.compare_digest`). Reserved scope
names SHALL NOT be registrable (enforcement point: identity.py AgentRegistry;
test: tests/core/test_identity.py).

#### Scenario: Registration roundtrip
- WHEN `register("director-1")` returns token T
- THEN `verify("director-1", T)` is True, `verify("director-1", wrong)` is
  False, the registry file contains only a hash, and its mode is 0600.

#### Scenario: Cross-agent replay rejected
- GIVEN tokens T1 for `director-1` and T2 for `engineer-1`
- WHEN `verify("engineer-1", T1)` runs
- THEN it returns False (id+token are verified as a pair).

### Requirement: ISO-14 Fail-closed strict boot (ADDED)
With `MEMORY_IDENTITY_MODE=strict`, a memory server SHALL raise
`IdentityError` at startup — registering no tools — when credentials are
missing, malformed, or fail verification (enforcement point: bind_identity at
module import; test: tests/adversarial/test__M4__identity.py, case A18).

#### Scenario: Strict boot without credentials fails closed
- GIVEN strict mode and no MEMORY_AGENT_ID/MEMORY_AGENT_TOKEN
- WHEN the server module is imported
- THEN IdentityError is raised before any tool registration or storage I/O.

### Requirement: ISO-15 Default-coercion policy is explicit (ADDED)
In bound mode, a caller-supplied `agent_id="default"` SHALL coerce to the
bound scope (logged DEBUG); `shared` SHALL remain public; any other foreign
scope SHALL be rejected. The coercion SHALL be documented in the module
docstring and covered by an adversarial test (enforcement point:
identity.assert_agent; test: case A17).

#### Scenario: Default coercion keeps legacy callers working
- GIVEN a server bound to `director-1`
- WHEN a tool is called without explicit agent_id (default)
- THEN the effective scope is `director-1` and the call succeeds within
  own+shared.
