# Proposal: language-understanding-sota

**Fecha:** 2026-09-07 · **Origen:** investigación multidisciplinar (ver nota en
el vault de Obsidian: `30 Investigacion/SOTA comprensión de lenguaje —
investigación multidisciplinar.md`) + experimentos empíricos FTS5.

## Tesis

El SOTA de comprensión de lenguaje alcanzable en nuestro entorno (cero modelos
locales, SQLite FTS5, agentes LLM como capa de generación) NO está en
embeddings: está en la combinación **índice hipocampal (grafo
entidades/relaciones) + spreading activation (PPR) + enriquecimiento
write-time + agente como System 2** — la fórmula de HippoRAG 2, que bate a
retrieval denso en multi-hop sin modelos.

## Niveles (serializados, cada nivel incrementa R@5 medible)

- **L0 — FTS5 tuning** (determinista, horas): trigram para substring/autocomplete,
  bm25 con pesos por columna (title/tags > body), prefix queries en entidades,
  NEAR para proximidad, familias morfológicas españolas en synonym.py
  (migrar→migración: porter NO cubre verbos españoles — verificado).
- **L1 — Fusión RRF** (determinista, días): Reciprocal Rank Fusion de las
  señales existentes (bm25 + entity_boost + importance + recencia). Sin
  entrenamiento: fórmula cerrada 1/(k+rank).
- **L2 — Spreading activation** (determinista, días): Personalized PageRank
  sobre entities/relations para recall multi-hop (la pieza HippoRAG). Seed =
  entidades del query; propagación con damping; resultados = puntos de las
  entidades activadas, fusionados RRF con bm25.
- **L3 — Enriquecimiento write-time** (agéntico): al capturar, tool kb_enrich
  extrae entidades/relaciones/importance con el LLM del agente (elaborative
  encoding; HippoRAG offline phase).
- **L4 — Query understanding agéntico** (agéntico, bajo demanda): descomposición
  de queries multi-hop + expansión semántica + LLM rerank de top-k — solo
  cuando L0-L2 devuelven score bajo (enrutado System 1/System 2).
- **L5 — Bi-temporalidad** (continuo): valid_from/valid_to en hechos
  consolidados (Zep/Graphiti): los hechos caducan; el frame problem resuelto
  con dos relojes.

## Capabilities

- **modified** `retrieval` (RET-10..13: trigram, pesos, RRF, PPR)
- **new** `kb` (KB-09 enriquecimiento write-time, KB-10 query understanding
  agéntico) — se implementa sobre obsidian-kb-pipeline

## Impacto de aislamiento

Ninguna operación nueva cruza scopes: PPR y RRF heredan el filtro engine-level
(solo entidades/puntos del scope+shared entran en el grafo de activación).
G-ISOLATION re-firma con adversarial de activación cruzada.

## Rollback

Cada nivel es independiente y flaggeado (`MEMORY Retrieval_LEVEL`); revert =
bajar de nivel. El motor FTS5 existente queda intacto.

## Métrica de decisión

eval actual: R@5 0.5388 / MRR 0.4570 (48 queries). Cada nivel debe SUBIR la
métrica o revertirse. Objetivo L0-L2: R@5 ≥ 0.65 en multi-hop. Benchmark
multi-hop propio (10 queries encadenadas sobre corpus real) como línea base
antes de L2.
