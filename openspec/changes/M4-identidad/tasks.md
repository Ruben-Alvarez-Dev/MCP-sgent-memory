# Tasks: M4-identidad

## 1. Núcleo identidad
- [ ] 1.1 `src/shared/identity.py`: AgentRegistry (sha256-only, chmod 600, compare_digest, atómico), Identity.assert_agent (coerción default), bind_identity (strict fail-closed).
  Acept: tests/core/test_identity.py ~14 unit verde. REQs: ISO-01, ISO-13, ISO-14, ISO-15.

## 2. CLI + wiring de referencia
- [ ] 2.1 `scripts/register_agent.py` (register/verify/list, token una sola vez).
  Acept: roundtrip CLI smoke. REQ: ISO-13.
- [ ] 2.2 L5 wiring de referencia: bind en arranque + assert_agent en 6 tools + status.
  Acept: A17 verde contra L5. REQs: ISO-01, ISO-15.

## 3. Replicación (fan-out)
- [ ] 3.1 K: L2_conversations (save/search/list) + L3_facts (bind+status) + L0_capture (bind+status) + unified (bind+health_check.identity).
  Acept: patrón idéntico al reference; suite verde.
  REQs: ISO-01.

## 4. Adversarial + gate
- [ ] 4.1 tests/adversarial/test__M4__identity.py: A17 spoof, A18 strict boot, A19 replay, A20 open WARN, A21 registry.
  Acept: markers isolation; suite adversarial verde.
  REQs: ISO-01, ISO-13, ISO-14, ISO-15.
- [ ] 4.2 Suite completa verde + ruff nuevo = 0 + GATE_M4 firmado.
