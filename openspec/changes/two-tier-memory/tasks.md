# Tasks — two-tier-memory

## Grupo A — Fundamentos (cálculo puro, sin borrado)
- [ ] A.1 Campos persistence/last_recalled/reinforce_count en captura y en el derivador de clase (TIER-01) — criterio: derivación determinista testeada (4 reglas)
- [ ] A.2 Curva de decay Ebbinghaus con refuerzo (TIER-03) — criterio: test matemático de curva y refuerzo (S crece, R se aplana)
- [ ] A.3 Recall refuerza (search/context hits actualizan last_recalled) — criterio: hit duplica S
- [ ] A.4 Suite Grupo A — criterio: ≥6 tests

## Grupo B — El reaper (olvido real)
- [ ] B.1 Reaper en ciclo de consolidación: decay → archivar bundle → delete points+FTS → evento L0 "forgotten" (TIER-04) — criterio: contenido fuera, traza dentro, undo restaura
- [ ] B.2 Protección de durables (TIER-02) — criterio: reaper con 100 durables no los toca
- [ ] B.3 Fail-closed ante bundle corrupto — criterio: sin borrado
- [ ] B.4 Suite Grupo B — criterio: ≥6 tests

## Grupo C — Destilación protege + bi-temporal
- [ ] C.1 Marca distillated al promover a KB (KB-11) — criterio: expiración de fuente destilada es inocua (TIER-05)
- [ ] C.2 valid_from/valid_to en durables + filtrado en recall (TIER-06) — criterio: hecho caducado no satura, histórico accesible
- [ ] C.3 Suite Grupo C — criterio: ≥4 tests

## Grupo D — Superficie
- [ ] D.1 Informe de retención (REST + UI: olvidadas/periodo, restaurables, ratio durable) — criterio: TIER-07 visible
- [ ] D.2 Override humano durable/TTL (TIER-08) — criterio: gana sobre derivación
- [ ] D.3 Restauración desde archivo (undo) vía UI — criterio: roundtrip completo

## Grupo E — E2E + GATE
- [ ] E.1 E2E calendario simulado (avance temporal inyectado): captura→decay→refuerzo→destilación→expiración sin pérdida — criterio: knowledge survives, street forgotten
- [ ] E.2 G-ISOLATION re-firmada + GATE con evidencia
