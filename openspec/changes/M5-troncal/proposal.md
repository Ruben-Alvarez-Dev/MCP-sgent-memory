# Proposal: M5-troncal — trunk con provenance, cero modelos locales en código, findings del eval

## Intent
Cerrar la última misión del programa memory-zero: (1) el tronco de
consolidación con aprobación humana y provenance (ISO-06 completo, casos
A11/A12/A16) — `merged` pasa de scope prohibido a canal dedicado auditado;
(2) ejecutar la restricción dura "cero modelos locales" EN CÓDIGO: fuera
get_llm/get_small_llm/llama_cpp.py/base.py — el módulo llm queda reducido a
classify_intent determinista; compliance pierde su dependencia del micro-LLM;
(3) atender los findings del eval-40 (entity splitter parte FTS5→FTS y pierde
dígitos; routing de decision_recall estrecho) y re-medir; (4) token opcional
del sidecar HTTP (hereda la identidad M4); (5) refresco de README.

## Capabilities
- Modified: `consolidation` (ISO-06 se completa: merged con aprobación+provenance)
- Modified: `retrieval` (merged visible a todos los agentes; entities con
  acrónimos+dígitos íntegros; routing de decisiones ampliado)
- Modified: `isolation` (ISO-16 ADDED: reserved-scope guard en el motor;
  ISO-17 ADDED: sidecar HTTP con token opcional)
- HARD CONSTRAINT ejecutado: cero código de modelos de generación locales.

## Tenants/scopes e impacto de aislamiento
El tronco es el ÚNICO canal hacia `merged` y exige `approved_by` + provenance;
el motor rechaza writes a scopes reservados sin ese triple. Lectura de merged:
pública (todos los agentes). Ningún ensanchamiento: merged se añade a la
cláusula IN de lectura, jamás a la de escritura automática.

## Rollback plan
Revert del commit. El guard de reserved-scopes es estrictamente aditivo (sin
flag, sin writes merged — estado M4). events.jsonl/agents.json sin migración.

## Fuera de alcance (permanente o con dueño)
- Bind de user_id a identidad → requiere modelo de usuarios (decisión de owner,
  no misión técnica). Documentado como deferral permanente por defecto.
- Rotación multi-token por agente → la rotación simple ya existe (register
  invalida el anterior); multi-credencial solo si un owner lo pide.
- sqlite-vec si >50k puntos → decisión operativa futura, no bloqueante.
