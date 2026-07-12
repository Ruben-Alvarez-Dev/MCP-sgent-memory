# /loop prompt — orchestrated spec-driven development (v2, verification protocol)

> Usage: start Claude Code in the repo root with the main model on **Sonnet** (`claude --model sonnet` or `/model sonnet`), then paste the block below after `/loop`. One loop iteration = one numbered OpenSpec iteration `I<NN>` completed with evidence. Push always requires Rubén's approval.

```
Lee CLAUDE.md, openspec/AGENTS.md (protocolo VINCULANTE), docs/plan/SESSION-HANDOFF.md y docs/plan/IMPROVEMENT-PLAN.md (§4). NO re-audites el repo. Ejecuta el plan fase a fase (resto de Fase 0 → Fase 1 → Fase 2/v2.2.0) como iteraciones numeradas I01, I02… dentro de changes aprobados de openspec/changes/, hasta cumplir los exit criteria de la Fase 2.

PROTOCOLO DE VERIFICACIÓN (openspec/AGENTS.md — invalida el trabajo si se viola)
- NADA mockup/demo/fake/mentira: cero mocks/stubs/datos de muestra fuera de tests/; ninguna afirmación de funcionamiento sin prueba ejecutable; lo no verificable se reporta como UNVERIFIED, jamás como funcionando.
- DOBLE VALIDACIÓN: ninguna suposición es accionable sin 2 fuentes independientes (código+ejecución, docs oficiales+probe real, schema+dato real…), ambas nombradas en la evidencia. Si discrepan: parar y reportar.
- TDD ESTRICTO por paso: test en rojo PRIMERO (output capturado) → implementación mínima → verde (test dirigido + tests/core completo una vez por change + ruff) → evidencia inequívoca en openspec/changes/<id>/evidence/I<NN>.md con comando, exit code y output VERBATIM + fecha + HEAD. "Los tests pasan" sin output pegado NO es prueba.
- ITERACIONES: I<NN> mapea 1:1 con tasks.md del change; DoD = rojo→verde→ruff→doble validación→evidencia commiteada→commit granular inglés con sufijo [<change-id>/I<NN>]→box marcado. Prohibido empezar I(n+1) sin cerrar I(n). Prohibido código fuera de una iteración.

ORQUESTACIÓN
- Tú (Sonnet) solo orquestas: NUNCA explores ni implementes en el contexto principal. Delega en subagentes jart-dev-team (dev-software-architect specs/ADRs, dev-backend-specialist, dev-database-specialist, dev-testing-specialist) y lanza EN PARALELO (un mensaje, múltiples Task) changes independientes — p.ej. fix-embedding-truncation ∥ vault-integrity ∥ honest-l2-status. Los subagentes heredan el protocolo completo: exígeles la evidencia, no te fíes de sus resúmenes (doble validación: su informe + tú ejecutas la verificación final).
- Comandos de verificación: PYTHONPATH=src .venv/bin/python -m pytest tests/core -q · .venv/bin/ruff check src tests

DISCIPLINA DE TOKENS
- offset/limit al leer; agrupa tool calls; no releer tras editar; informes de subagente ≤300 palabras; al usuario 1 línea por iteración: "I<NN> <change-id> — <qué se probó> — VERDE (evidencia: <ruta>)".
- Reutiliza subagentes vivos (SendMessage) en vez de relanzar contexto.

GATES
- Nunca push sin aprobación explícita de Rubén. Nunca commit con tests en rojo. Pregunta (en español) SOLO en: fin de fase, fallo tras 2 intentos, ambigüedad de alcance.
- Sin dependencias nuevas; loggers agent-memory.*; modelos siempre vía shared/model_tier.py.
- ARQUITECTURA (ADR-0007, vinculante): hexagonal ports&adapters, SOLID, DRY, normalización enterprise. Toda I/O tras un puerto; duplicación se extrae, no se copia; regla boy-scout: cada módulo tocado migra al layout objetivo (domain/ports/adapters/app/runtime); sin cross-imports entre módulos Lx; abstrae toda frontera de I/O/política, nada de abstracciones especulativas de un solo consumidor.

FIN: exit criteria de Fase 2 (P0s cerrados con regresión y evidencia, cobertura ≥60%, tag v2.2.0 propuesto — tag y push los aprueba Rubén). Empieza por el paso 1 del handoff (install/pull-models.sh; evidencia = /api/tags antes/después + tier resolver antes/después) y el resto de Fase 0.
```
