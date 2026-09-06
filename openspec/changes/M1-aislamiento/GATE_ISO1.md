# GATE_ISO1-lite — Aislamiento hotfix (alcance lite)

Estado: PASS (GO con alcance lite; ver diferidos)
Fecha: 2026-09-06
Firma QA: arquitecto (46/46 adversarial + 213 suite verificados)
Firma Owner (arquitecto): arquitecto

## Checks automáticos
- [x] `pytest tests/adversarial -q` → **46 passed** (0 servicios externos)
- [x] `pytest tests/core tests/adversarial -q` → **213 passed, 1 failed (KNOWN-BUG-003 preexistente), 6 skipped** — idéntico a baseline + 46 nuevos
- [x] `ruff check` ficheros nuevos (`scope.py`, test adversarial) → **limpio**; ficheros tocados sin violaciones NUEVAS (37 preexistentes intactas, verificadas por diff stash)
- [x] A1 (reminders cross-read) verde · A2 (decisions cross-read, 2 vías) verde
- [x] A4/A7/A8/A9-shape verdes (scope inválido, traversal, reserved-spoof, no-glob)
- [x] Migración legacy reminders verificada (root → shared/, sin copias, sin pérdida)
- [x] Traversal vía `save_decision(scope="../../etc")` → `error`, cero writes fuera del jail

## Checklist humana
- [x] Hallazgo adversarial integrado: la sanitizaciónremapeaba traversal (`../../etc`→`etc`) — corregido validando el scope CRUDO antes de sanitizar, en L3 y L5. Sin este gate se habría escapado.
- [x] Cambio de default documentado: `save_decision` ahora persiste `scope` en frontmatter y escribe no-shared bajo `_scopes/` (default `agent` = namespaced, más seguro que el anterior global implícito).
- [x] `dismiss_reminder` gana param opcional `agent_id` (compatible hacia atrás).
- [x] Diferidos explícitos con dueño: A3/A5/A6/A10/A14/A15 → M2 · A11/A12/A16 → M5 · identidad harness → M4. Ninguno silenciado.
- [x] Trazabilidad: ISO-03/ISO-04 (MODIFIED) + ISO-09/ISO-10 (ADDED) en delta spec; tests nombran los casos A*.

## Decisión
- [x] GO → se abre M2-storage (`memory.db` con enforcement nativo + re-auditoría G-ISO completa)
- [ ] NO-GO: —
