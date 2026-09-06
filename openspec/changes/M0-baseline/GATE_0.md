# GATE_0 — Baseline freeze

Estado: PASS (GO)
Fecha: 2026-09-06
Firma QA: arquitecto (auto-validado contra evidencia)
Firma Owner (arquitecto): arquitecto

## Checks automáticos (comando + evidencia)
- [x] `pytest tests/core -q` ejecutado, salida en `evidence/suite-core.txt` → **167 passed, 1 failed (KNOWN-BUG-003), 6 skipped (legacy v3), ~5s**
- [x] Scope tests ejecutados, salida en `evidence/suite-scope.txt` → **6/6 PASS** (con matiz documentado en leaks.md: prueba clientes, no el sistema)
- [x] `evidence/latency.json` → Qdrant 200, embed 172–848 ms (varianza por carga CPU), `:8081` ocupado por proxy ajeno (DOWN para nosotros)
- [x] `evidence/leaks.md` confirma L-R1, L-D1, L-F1, L-C1, L-V1, L-ID0, ISO-08 con file:line
- [x] `evidence/known-bugs.md` contiene KNOWN-BUG-001, -002 y -003 (descubierto durante la baseline)
- [x] `evidence/eval-40.yaml` con 40 queries (20 ES / 20 EN, 5 intents), juicios TBD en M3
- [x] `pytest --markers` lista unit/contract/integration/nightly/isolation/req
- [x] Cero cambios de comportamiento: mis cambios son `openspec/` (nuevo) + markers en `pyproject.toml` (config) + dirs vacíos de skeleton. `config/mcp.json` e `install/bootstrap.sh` aparecen modificados en git pero son PREEXISTENTES (no tocados en esta misión).

## Checklist humana
- [x] La baseline es honesta: 1 fallo registrado como KNOWN-BUG-003, nada maquillado
- [x] La desviación eval-40-sin-juicios (diseño §Failure modes) queda aceptada
- [x] Trazabilidad iniciada: este gate no requiere REQs (skip_specs), verificado

## Decisión
- [x] GO → se abre M1-aislamiento-hotfix
- [ ] NO-GO (motivo + rollback ref): —
