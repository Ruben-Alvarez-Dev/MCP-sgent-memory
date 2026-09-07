# Design — two-tier-memory

## 1. Modelo

```python
# campos nuevos en payload (persisten en points sin migrar schema):
#   persistence: "ephemeral" | "durable"        (derivado o marcado)
#   last_recalled: iso                          (refuerzo al ser recordada)
#   reinforce_count: int
#   valid_from / valid_to: iso                  (solo durables; bi-temporal L5)

S₀ = 7 días (estabilidad base)          # Ebbinghaus: sensibilidad media
R(t) = e^(-Δt / S)                      # retención 0..1
importance_effective = importance × R(t)
umbral de olvido: importance_effective < 0.05 → archivar + olvidar
refuerzo: cada recall (hit en search/context) → reinforce_count += 1,
          last_recalled = now → S crece → la curva se aplana (spaced repetition)
```

## 2. Derivación de clase (TIER-01, determinista)

```
durable SI:
  - destilada (existe nota KB con source: memory:<id> y estado ≥ pulido-agente)
  - O mem_type == "decision"
  - O importance ≥ MEMORY_KB_IMPORTANCE (0.8)
  - O persistence="durable" explícito
ephemeral: resto (calle: estado de sesiones, apuntes, contexto operativo)
```

El override humano (TIER-08) gana siempre. La derivación corre en captura y se
re-evalúa en cada consolidación (una efímera puede ASCENDER a durable al ser
destilada — nunca al revés).

## 3. El reaper (olvido como proceso, no como accidente)

Se ejecuta dentro de la consolidación (mismo ciclo, tras la pasada KB):

```
1. actualizar importance_effective de efímeras (decay)
2. archivar las bajo umbral: bundle quirúrgico → DELETE points+FTS
   → evento L0 "forgotten {distillated: true|false}"
3. jamás toca durables (TIER-02)
4. informe de retención → telemetría (olvidadas, restaurables)
```

**Olvidar con memoria de haber olvidado**: el archivo JSONL + el evento L0
conservan metadatos (qué se olvidó y cuándo) sin el contenido — el sistema
"recuerda que olvidó" sin fingir que recuerda.

## 4. Interacción con el resto del sistema

| Componente | Efecto |
|---|---|
| Promoción KB (obsidian-kb-pipeline) | al promover, la fuente queda protegida un ciclo y marcada distillated → su expiración es inocua (TIER-05) |
| Motor quirúrgico | el reaper reutiliza delete_single + undo (olvidar = quirúrgico masivo con trazabilidad) |
| Telemetría | decay/reaper emiten métricas (olvidadas/día, ratio durable/efímero) |
| request_context | respeta importance_effective (lo olvidado no satura el contexto) |
| Fase 2 (indexación del vault) | las notas del KB en Obsidian son durables por naturaleza (viven fuera de la DB) |

## 5. Modos de fallo y adversarios

| Amenaza | Defensa |
|---|---|
| Reaper borra una dura | TIER-02 test con invariante duro; excluidas por derivación pre-consulta |
| Decay borra lo valioso antes de destilar | umbral de olvido (0.05) muy bajo; destilación corre antes que el reaper en el mismo ciclo |
| Archivo corrupto | fail-closed como SURG-14 (no borra sin bundle válido) |
| Olvido en cascada de entidades | fuera de alcance: el grafo se purga por purge_orphans (quirúrgico), no por decay |
| Tuning de S₀ malo | S₀ y umbrales env-configurables; telemetría de ratio olvido/destilado para calibrar |

## 6. Grupos de implementación (serializados)

- **A — Campos + derivación + decay** (TIER-01/03): puro cálculo, sin borrado · tests de curva
- **B — Reaper + archivo + undo** (TIER-04/07): olvido real con traza · tests adversariales
- **C — Distilación protege + bi-temporal** (TIER-05/06) · tests
- **D — UI/REST: informe de retención + override + restauración** (TIER-08) · tests
- **E — E2E con calendario simulado (avance temporal) + GATE**
