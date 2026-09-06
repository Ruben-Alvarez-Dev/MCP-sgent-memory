# Proposal: M1-aislamiento LITE (alcance reducido por decisión de arquitectura)

## Intent
Cerrar las dos fugas de lectura baratas (L-R1 reminders, L-D1 decisions) con
enforcement real, congelar el formato canónico de scope como contrato para M2, y
dejar la matriz adversarial A1–A16 escrita como tests (verdes donde aplica,
documentados como pendientes donde requieren M2/M4/M5).

## Desviación registrada vs plan maestro
El plan preveía M1 completa (middleware `resolve_scope`, allowlist, fail-closed
boot, migración a scoped clients). Decisión de arquitectura 2026-09-06: la BD
está vacía (2 puntos), hay un solo usuario, Qdrant será demolido en M2 y la
identidad confiable exige M4. Blindar Qdrant a fondo sería trabajo desechable.
M1-lite cierra lo barato-real-hoy y convierte el resto en contrato testeable.
El aislamiento pesado (middleware, allowlist, jail FS, re-auditoría) se construye
nativo en M2. Esta desviación es intencional y queda aquí registrada.

## Scope
IN: `shared/scope.py` (canon + validación); reminders por namespace (L-R1);
decisiones por namespace + plumb `agent_scope` en retrieval (L-D1); cableado de
los params decorativos `save_decision.scope` / `list_decisions.scope`; tests
adversariales filesystem-only en CI; deltas ISO-03/ISO-04 + ADDED ISO-09/ISO-10.
OUT (diferido con dueño): L-F1/L-C1/L-V1/L-ID0 (M2/M4), enforcement motor Qdrant
(M2), identidad harness (M4), tronco (M5), middleware y fail-closed boot (M2).

## Capabilities
- Modified: `isolation` (ISO-03, ISO-04 cambian de fuga-documentada a enforced).
- New (delta): ISO-09 canonical scope, ISO-10 namespace directories.

## Rollback plan
Revert de los 4 ficheros tocados (`scope.py` nuevo se borra; L5/retrieval/L3
vuelven a lectura global). Sin migración de datos (dirs nuevos vacíos en prod).

## Isolation impact
Positivo y acotado: dos vías de lectura cruzada eliminadas; ningún ensanchamiento.
