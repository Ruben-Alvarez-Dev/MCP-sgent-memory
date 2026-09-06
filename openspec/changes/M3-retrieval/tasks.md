# Tasks: M3-retrieval

## 1. Motor
- [x] 1.1 Fusión sparse en `memory_db.search` (sparse_query/sparse_weight, coseno sparse, score_source, tie-break por id).
  Acept: RET-05 escenarios + RET-07 en tests/core/test_sparse_fusion.py.
  REQs: RET-05, RET-07, RET-01.

## 2. Retrieval wiring
- [x] 2.1 `retrieval._retrieve_hybrid` pasa sparse_query=bm25_tokenize(query_text); SPEC-4.1 eliminado; import rank_by_relevance/get_llm fuera.
  Acept: e2e retrieval con fusión; cero refs rank_by_relevance en src/.
  REQs: RET-05, RET-04.

## 3. L5 degradación
- [x] 3.1 `_embed_or_hash` en L5 (push_reminder, detect_context_shift×2) con WARN; KB-002 cerrado.
  Acept: adversarial outage verde (mock raising); sim=1.0 para textos iguales.
  REQs: RET-06.

## 4. Jubilación micro-LLM
- [x] 4.1 Borrar rank_by_relevance (llm/config.py + __init__ exports) y tests/core/test_llm_ranking.py; get_small_llm/compliance intactos (diferido M5).
  Acept: grep rank_by_relevance = 0; suite verde sin el 1 failed del baseline.
  REQs: RET-04.

## 5. eval-40
- [x] 5.1 Fixture corpus determinista (~35 docs del repo) + judgments.yaml trazables.
  Acept: fixture regenerable idempotente; cada query ≥1 doc relevante o justificado.
- [x] 5.2 `scripts/run_eval.py` → evidence/eval-40-results.yaml (Recall@5, MRR, notas de cobertura).
  Acept: runner corre sin servicios; resultados honestos registrados.

## 6. Gate
- [x] 6.1 Suite completa verde — 0 failed por primera vez (KNOWN-BUG-003 se jubila con su función); ruff nuevos = 0.
- [x] 6.2 GATE_M3.md firmado con cierre de KNOWN-BUG-002/003 en evidence. → **PASS (GO)**
