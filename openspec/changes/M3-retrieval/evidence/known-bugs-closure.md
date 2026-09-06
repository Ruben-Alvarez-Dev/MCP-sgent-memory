# Evidence M3 — cierre de KNOWN-BUG-002 y KNOWN-BUG-003

Fecha: 2026-09-06 · Misión: M3-retrieval · Baseline original: openspec/changes/M0-baseline/evidence/known-bugs.md

## KNOWN-BUG-002 — CERRADO (RET-06)
`L5_routing` usaba `async_embed` raising: `request_context`/`push_reminder`/
`detect_context_shift` fallaban cerrados sin embedding server (único módulo que
crasheaba en vez de degradar).

**Fix**: helper `_embed_or_hash(text)` — intenta `async_embed`; ante excepción
registra WARN y degrada a `hash_vector` determinista (shared.memory_db).
Aplicado en `push_reminder` y `detect_context_shift` (×2). Similitud entre
hashes de textos idénticos = 1.0 (determinista).

**Prueba**: `tests/adversarial/test__M3__l5_degradation.py` — outage simulado
(mock de async_embed raising): push_reminder persiste (score_source="hash"),
detect_context_shift(idénticos) → sim 1.0 / shift False; distintos → sim < 1.0.

## KNOWN-BUG-003 — CERRADO POR JUBILACIÓN (RET-04)
`test_rank_by_relevance_top_k` fallaba desde la baseline porque no hay
micro-LLM desplegado y el fallback devolvía la entrada sin rankear: "este fallo
ES la evidencia de que el ranking generativo está permanentemente degradado".
El plan M0 ya fijaba el remedio: borrar la función y su test.

**Ejecutado**: `rank_by_relevance()` eliminada de `llm/config.py` + exports;
bloque SPEC-4.1 en `_rank_and_fuse` eliminado; `get_llm` fuera del import de
retrieval; `tests/core/test_llm_ranking.py` borrado (4 tests difuntos).
`grep -rn rank_by_relevance src/ tests/` → 0.

**Prueba**: suite completa **0 failed** por primera vez (259 passed / 6 skipped).

## NOTA — restricción dura reforzada
`bm25_tokenize` usaba `hash()` de Python (aleatorio por PYTHONHASHSEED): los
sparse vectors no habrían matcheado entre procesos/reinicios. Migrado a
SHA-256-derived 32-bit ids (estables). Filas escritas pre-M3 conservan índices
viejos: su sparse decae silenciosamente a 0 (comportamiento seguro); la
re-ingesta o el migrador regeneran. BD real: ~2 puntos — sin impacto.

## NOTA — bug latente preexistente reparado
`async_embed_batch` importaba `asyncio as _aio` pero usaba `asyncio.to_thread/
gather` → NameError garantizado en el path batch (detectado por ruff F821 al
tocar el fichero). Corregido.
