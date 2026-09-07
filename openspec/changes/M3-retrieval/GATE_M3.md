# GATE_M3 — retrieval: sparse read, degradación L5, jubilación micro-LLM, eval-40

Estado: PASS (GO)
Fecha: 2026-09-06
Firma QA: arquitecto (262 passed / 0 failed / 6 skipped + 72 adversarial verificados)
Firma Owner (arquitecto): arquitecto

## Checks automáticos
- [x] `pytest tests/ -q` → **262 passed, 0 failed, 6 skipped** — PRIMERA SUITE COMPLETAMENTE VERDE del programa (KNOWN-BUG-003 se jubiló con su función)
- [x] `pytest tests/adversarial -q` → **72 passed** (69 M2 + 3 RET-06 outage)
- [x] `pytest tests/core/test_sparse_fusion.py -q` → **13 passed** (RET-05 boost, RET-07 tie-break, fail-closed, degradación corrupta, aislamiento intacto con spy A3)
- [x] `ruff check` ficheros NUEVOS M3 (test_sparse_fusion, test__M3__l5_degradation, tests/eval/, run_eval.py, memory_db.py) → **limpio**
- [x] `grep -rn rank_by_relevance src/ tests/` → **0** (RET-04: función + exports + SPEC-4.1 + test difunto borrados)
- [x] eval-40 ejecutado: **R@5 0.425 · MRR 0.4542** (19/40 zero-recall, causas documentadas) — reproducible en 2 runs con motor corregido → `evidence/eval-40-results.yaml`

## Hallazgos y fixes de integración (todos verificados)
- [x] **BUG MOTOR (nuevo, fijado por eval J)**: lecturas concurrentes `to_thread` sobre la conexión compartida → `SQLITE_MISUSE` intermitente. Fix: serialización de las 4 rutas de lectura con `self._lock` (writes ya lo tenían)
- [x] **BUG MOTOR (nuevo)**: `classify_intent` usaba `list(set(...))` → orden de entities dependía de PYTHONHASHSEED → retrieval no reproducible entre procesos. Fix: `sorted(set(...))`
- [x] **BUG LATENTE preexistente**: `async_embed_batch` importaba `asyncio as _aio` pero usaba `asyncio.to_thread/gather` → NameError garantizado en path batch (ruff F821). Corregido
- [x] **DEFECTO DE DISEÑO corregido en diseño**: media ponderada `(1-w)*dense + w*sparse` encogía scores y rompía MIN_SCORE → fórmula boost monótono `dense + w*s*(1-dense)` (sparse solo mejora; back-compatible con sparse=0)
- [x] **bm25_tokenize inestable**: `hash()` de Python aleatorio por proceso → sparse matching roto entre reinicios. Fix: SHA-256-derived 32-bit ids. (Filas pre-M3: sparse decae a 0 silenciosamente — seguro; BD real ~2 puntos)

## Cierres de known-bugs (evidence/known-bugs-closure.md)
- [x] **KNOWN-BUG-002 CERRADO**: L5 degrada a hash-vector con WARN (outage simulado: push_reminder persiste, detect_context_shift sim=1.0 en idénticos)
- [x] **KNOWN-BUG-003 CERRADO POR JUBILACIÓN**: función+test eliminados; suite 0 failed por primera vez

## Checklist humana
- [x] Eval honesto: corpus sintético (38 docs trazables al repo), juicios con notas (incluye símbolos muertos AuthService/build_repo_index_points como "hallazgo del sistema, no del juicio")
- [x] Los 19 zero-recall son **findings documentados, no silenciados**: gap léxico es→en (how_to ES), entity splitter parte FTS5→FTS y descarta dígitos, 18/40 queries enrutan a pattern_match (keywords estrechas → decisiones L4 inalcanzables), boost single-token insuficiente sobre dense negativo → dueño: M5-troncal/eval continuo
- [x] `get_small_llm`/llama_cpp.py intactos: consumidor vivo en `shared/compliance` (degradación graceful) → **diferido M5** con nota
- [x] RET-01 delta spec backfilled (M2 cambió el backend sin su delta de retrieval — deuda documental saldada)
- [x] G-ISOLATION NO re-firmada (sin cambios de enforcement); verificación positiva: fusión sparse opera post-WHERE, spy A3 verde con sparse_query
- [x] Trazabilidad: RET-01/04/05/06 (MODIFIED) + RET-07 (ADDED) en delta spec; tests nombran los casos

## Decisión
- [x] GO → se abre M4-identidad (harness-asserted identity, ISO-01) o M5-troncal según prioridad del owner
- [ ] NO-GO: —
