# Tasks: M1-lite

## 1. Canonical scope
- [x] 1.1 `src/shared/scope.py` (normalize/validate/dirs/iter + `ScopeError`).
  Acept: tests de validación 15+ casos (válidos, traversal, reservados, largos, vacíos).

## 2. L-R1 reminders
- [x] 2.1 Namespacing en `L5_routing/server/main.py` + migración legacy + `dismiss_reminder(agent_id)`.
  Acept: A1 verde (B no ve nada de A; A ve lo suyo; todos ven shared).

## 3. L-D1 decisions
- [x] 3.1 Namespacing en `L3_decisions` (save/search/list/get-roots) + plumb `agent_scope` en `_retrieve_parallel`.
  Acept: A2 verde en ambas vías (tool directa y retrieval interno).

## 4. Adversarial + gates
- [x] 4.1 `tests/adversarial/test__ISO03__scope_isolation.py` en CI (markers `isolation`), header con estado A1–A16.
  Acept: suite verde; ningún test requiere servicios.
- [x] 4.2 `tests/core` completo sin regresiones + `ruff check` verde.
  Acept: 167 passed / 1 failed (KNOWN-BUG-003, preexistente) / 6 skipped.
- [x] 4.3 Rellenar `GATE_ISO1.md` y firmar GO/NO-GO.
