# /loop prompt — orchestrated spec-driven development

> Usage: start Claude Code in the repo root with the main model on **Sonnet** (`claude --model sonnet` or `/model sonnet`), then paste the block below after `/loop`. One iteration = one OpenSpec change completed. Push always requires Rubén's approval.

```
Lee CLAUDE.md, docs/plan/SESSION-HANDOFF.md y docs/plan/IMPROVEMENT-PLAN.md (§4). NO re-audites el repo: el estado y los P0 ya están mapeados ahí. Ejecuta el plan fase a fase (resto de Fase 0 → Fase 1 → Fase 2/v2.2.0), un change de openspec/changes/ por iteración, hasta cumplir los exit criteria de la Fase 2.

REGLAS DE ORQUESTACIÓN
- Tú (Sonnet) solo orquestas: NUNCA explores ni implementes en el contexto principal. Delega en subagentes jart-dev-team (dev-software-architect para specs/ADRs, dev-backend-specialist, dev-database-specialist, dev-testing-specialist) y lanza EN PARALELO (un solo mensaje, múltiples Task) los changes independientes — p.ej. fix-embedding-truncation ∥ vault-integrity ∥ honest-l2-status.
- Por change: (1) si falta proposal, que architect lo redacte desde la tabla del plan (≤1 página); (2) implementar (subagente especialista, diffs quirúrgicos); (3) tests dirigidos y luego tests/core completo UNA vez: PYTHONPATH=src .venv/bin/python -m pytest tests/core -q; (4) .venv/bin/ruff check src tests; (5) commits granulares en inglés (Conventional Commits), NUNCA con tests en rojo; (6) marcar tasks.md y archivar el change en openspec/specs/.

DISCIPLINA DE TOKENS
- Lee archivos con offset/limit; agrupa tool calls independientes en un mensaje; no releas archivos tras editarlos; informes de subagente ≤300 palabras; al usuario solo 1 línea de estado por change.
- Reutiliza subagentes vivos (SendMessage) en vez de relanzar contexto.

GATES Y PARADAS
- Nunca push sin aprobación explícita de Rubén. Pregunta (en español) SOLO en: fin de fase, fallo tras 2 intentos de arreglo, o ambigüedad de alcance. Todo lo demás: decide y avanza.
- Norma dura: sin mocks/fakes fuera de tests/, loggers agent-memory.*, sin dependencias nuevas, modelos siempre vía shared/model_tier.py.

CRITERIO DE ITERACIÓN COMPLETA: tasks.md del change activo todo marcado + suite verde + commit hecho. CRITERIO DE FIN: exit criteria de Fase 2 del plan (P0s cerrados con tests de regresión, cobertura ≥60%, tag v2.2.0 propuesto — el tag y push los aprueba Rubén). Empieza ahora por el paso 1 del handoff (install/pull-models.sh y verificación del tier) y el resto de Fase 0.
```
