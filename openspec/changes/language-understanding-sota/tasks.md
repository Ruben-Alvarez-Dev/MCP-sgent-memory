# Tasks — language-understanding-sota

## L0 — FTS5 tuning (determinista)
- [ ] 0.1 Migration del schema FTS: `tokenize="unicode61 remove_diacritics 2"` + columna terciaria trigram para fuzzy — criterio: experimentos del 2026-09-07 reproducidos contra el índice real
- [ ] 0.2 bm25 con pesos: title/tags 10x sobre body en search_fts y search_conversations — criterio: ranking prefiere matches en título verificado por test
- [ ] 0.3 Prefix queries en entidades y NEAR en frases del query builder (`_build_fts5_query` v3) — criterio: 'config*' y NEAR testeados
- [ ] 0.4 Familias morfológicas españolas en synonym.py (verbos↔sustantivos: migrar/migración, consultar/consulta) — criterio: porter-fallo empírico cubierto
- [ ] 0.5 Eval R@5 ≥ 0.5388 (no-regresión) — criterio: scripts/run_eval.py

## L1 — Fusión RRF (determinista)
- [ ] 1.1 RRF de señales existentes: bm25 + entity_boost + importance + recencia (`rrf(k=60)`) — criterio: top-10 fusionado ≥ top-10 de cualquier señal sola en eval
- [ ] 1.2 Tests adversariales de fusión (query con señales contradictorias) — criterio: sin regresión de aislamiento

## L2 — Spreading activation (PPR)
- [ ] 2.1 PPR sobre entities/relations en Python puro (power iteration, damping 0.85, seed = entidades del query) — criterio: multi-hop synthético resuelto (A→relaciona→B→contiene→C)
- [ ] 2.2 Integración en search: puntos de entidades activadas fusionados RRF con bm25 — criterio: eval R@5 ≥ 0.60
- [ ] 2.3 Benchmark multi-hop propio (10 queries encadenadas sobre corpus real) como línea base y métrica de L2 — criterio: documento de resultados

## L3 — Enriquecimiento write-time (agéntico)
- [ ] 3.1 Tool `kb_enrich(content)→{entities[], relations[], importance, mem_type}` vía LLM del agente — criterio: grounding test (entidades ⊆ contenido)
- [ ] 3.2 Hook opcional en captura (L0_capture_memorize añade enriched=true y salta re-extracción) — criterio: telemetría de cobertura

## L4 — Query understanding agéntico
- [ ] 4.1 Enrutado S1/S2: score bajo → tool `understand_query` del agente (descomposición + expansión) — criterio: multi-hop resuelto sin degradar queries simples
- [ ] 4.2 LLM rerank de top-20 opcional — criterio: precision@3 ≥ baseline en muestreo

## L5 — Bi-temporalidad
- [ ] 5.1 valid_from/valid_to en hechos consolidados + filtrado temporal en recall — criterio: hecho caducado no aparece por defecto
- [ ] 5.2 GATE: eval final + adversarial de aislamiento de activación + firma
