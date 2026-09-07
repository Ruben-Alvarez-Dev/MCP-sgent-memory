# Proposal: M3-retrieval — sparse read path, degradación L5, jubilación del micro-LLM, eval-40

## Intent
Cerrar los tres diferidos de retrieval heredados: dar lectura al sparse vector
(RET-05, write-only desde siempre), degradar L5 deterministicamente sin
embedding server (RET-06/KNOWN-BUG-002) y jubilar el ranking por micro-LLM
(RET-04/KNOWN-BUG-003 — la degradación por score ya es el estado permanente
aceptado). Además: construir el fixture + juicios del eval-40 congelado en M0,
y backfill del delta RET-01 (backend memory.db) que M2 implementó sin su spec.

## Capabilities
- Modified: `retrieval` (RET-01 backend documentado; RET-04 ranking LLM
  eliminado permanentemente; RET-05 sparse con lectura y fusión; RET-06
  degradación determinista sin embeddings).
- Sin cambios en storage ni isolation (G-ISOLATION no se re-firma: ningún
  cambio toca enforcement de scope — la fusión sparse opera sobre candidatos
  YA filtrados por el motor).

## Tenants/scopes afectados e impacto de aislamiento
Ninguno estructuralmente. El score combinado se calcula post-WHERE sobre
candidatos ya aislados (misma propiedad ISO-05: nada cruza scopes porque nada
lee fuera del resultado del motor). Los pesos de fusión son agnosicos al scope.

## Rollback plan
Revert del commit. El sparse_json ya se escribe desde antes (columna M2), así
que desactivar la lectura es wire-compatible. L5 vuelve a async_embed raising
con revert. Sin migraciones de datos.

## Fuera de alcance (con dueño)
- `get_small_llm` + backend llama_cpp LLM: consumidor vivo en
  `shared/compliance` (verificación semántica) — su demolición requiere decidir
  el futuro del compliance check → diferido a M5-tronco con nota en gate.
  Ningún hot path de retrieval lo usa tras M3.
- Re-ranking generativo: prohibido por restricción dura (cero modelos
  locales); el ranking es fusión determinista de scores, permanentemente.
