# Addendum — SOTA IA/ML (extensión de investigación II)

Investigación completa en el vault del usuario:
`30 Investigacion/SOTA IA-ML — comprensión de lenguaje y memoria de agentes.md`.
Esta pieza documenta lo ACCIONABLE en nuestro entorno.

## Hallazgos adoptables (mapeados a requisitos)

### AI-1 · Operaciones de memoria completas (patrón Mem0)

Mem0 decide ADD/UPDATE/DELETE/NOOP sobre la memoria existente en cada captura
(dedup semántico). Nosotros solo hacemos ADD — duplicamos conocimiento con
variaciones.

**Adopción:** en la captura (tras kb_enrich de L3), comparar contra candidatos
por entidad/scope y emitir la operación correspondiente. Sin LLM local: el
criterio de similitud es entity-overlap + FTS score (determinista); el caso
ambiguo se delega al agente (tool kb_decide).
Tests: `test_memory_ops_update_merges`, `test_memory_ops_noop_on_new`,
`test_memory_ops_delete_respects_trace`.

### AI-2 · RLVR-lite en el editor (recompensa verificable)

DeepSeek-R1 entrenó razonamiento con recompensas verificables; nuestro
kb-editor ya tiene el circuito a nivel de sistema: genera → gate de calidad
(citas/plantilla/dedup) → reintentar. Formalizar como bucle con reintentos
máximos y registro del ciclo (telemetría ya instalada).
Tests: `test_editor_retry_cycle_records`, `test_gate_rejection_requeues`.

### AI-3 · Test-time compute selectivo

Los modelos de razonamiento gastan más cómputo en problemas difíciles
(o1/R1; Snell et al.: el trade-off pesos-vs-tokens). Nuestro kb-editor debe
gastar más en destilaciones complejas (multi-fuente) y poco en simples:
`thinking_budget` proporcional al número de fuentes.
Tests: `test_editor_budget_scales_with_sources`.

### AI-4 · Mapping CoALA como especificación

CoALA (Sumers et al.): working/episodic/semantic/procedural. Mapea 1:1:
L0/L1=working, L2=episodios, L3=semántica, Lx=procedural, skills=procedural.
Documentar como especificación de arquitectura (validación externa del diseño
memory-zero).

### AI-5 · Context engineering aplicado

- Compaction = nuestra consolidación.
- Orden U-shaped de atención → lo importante al inicio/fin de los ContextPacks.
- Sub-agent contexts = la geometría de perfiles que ya usamos.
Test: `test_contextpack_orders_anchors_first_last`.

## Tareas añadidas

- [ ] AI.1 Memory ops (ADD/UPDATE/DELETE/NOOP) en captura — criterio: dedup semántico por entity-overlap+FTS
- [ ] AI.2 RLVR-lite formalizado en kb-editor (reintentos + registro) — criterio: ciclo observable en telemetría
- [ ] AI.3 thinking_budget ∝ complejidad en el editor — criterio: destilaciones multi-fuente gastan más
- [ ] AI.4 Doc CoALA-mapping en openspec — criterio: revisión arquitectónica firmada
- [ ] AI.5 ContextPack con anclas U-shaped — criterio: test de orden
