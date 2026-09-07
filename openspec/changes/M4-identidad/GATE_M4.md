# GATE_M4 — identidad: harness-asserted identity, registry, strict fail-closed boot

Estado: PASS (GO)
Fecha: 2026-09-06
Firma QA: arquitecto (285 passed / 0 failed / 6 skipped + 81 adversarial verificados)
Firma Owner (arquitecto): arquitecto

## Checks automáticos
- [x] `pytest tests/ -q` → **285 passed, 0 failed, 6 skipped** (suite verde se mantiene)
- [x] `pytest tests/adversarial -q` → **81 passed** (72 M3 + 9 nuevos A17–A21)
- [x] `pytest tests/core/test_identity.py -q` → **14 passed** (registry/verify/boot/policy)
- [x] `ruff check` ficheros NUEVOS M4 (identity.py, test_identity.py, test__M4__identity.py, register_agent.py) → **limpio**
- [x] A17 spoof: bound director-1 + agent_id ajeno → ScopeError **con tripwires en storage** (cero I/O demostrado, no asumido); "default"→coerción ISO-15; shared ok
- [x] A18 strict boot: sin credenciales / token malo → IdentityError antes de registrar tools
- [x] A19 replay cruzado: verify(id ajeno, token propio) → False (hmac.compare_digest)
- [x] A21 registry: 0600 verificable, solo sha256 (token jamás en fichero ni logs), corrupto → vacío+WARN, reserved → ScopeError
- [x] Cadena fail-closed completa probada: registry corrupto → verify False → strict IdentityError
- [x] CLI register_agent.py: roundtrip register/verify/list smoke (exit codes: 0 ok, 1 mismatch, 2 error)

## Checklist humana
- [x] **Modo por defecto = open con WARN observable** (decisión M4-lite registrada): despliegue actual = un agente local; strict es una línea de env por agente en mcp.json (el CLI imprime el bloque). No rompe callers existentes; el tightening (L2 search/list: None→default→scope propio/shared) es dirección fail-closed y documented
- [x] Coerción "default"→scope propio (ISO-15): mantiene vivos a los callers legacy sin abrir puerta a hermanos
- [x] user_id NO es identidad (particionado de aplicación, L3_facts) — documentado en proposal; bind de user_id diferido M5
- [x] Tokens: token_urlsafe(32), mostrados UNA vez, solo sha256 persistido, jamás logueados (grep verificado), escritura atómica tmp+rename con chmod previo
- [x] 7 servidores con bind; gates de tool en las rutas con eje agent-scope (L5 ×5, L2 ×3); unified expone identity en health_check
- [x] Diferidos con dueño: mTLS/firma por request + identidad HTTP del sidecar → M5 · rotación/múltiples tokens → M5 · bind user_id → M5 · get_small_llm/compliance → M5 · findings eval (gap es→en, entity splitter, intent routing) → M5
- [x] Rollback: revert + no env = comportamiento M3 exacto (agents.json aditivo e inerte sin strict)

## Decisión
- [x] GO → se abre M5-troncal (global/merged con provenance + A11/A12/A16 + findings del eval + compliance decision)
- [ ] NO-GO: —
