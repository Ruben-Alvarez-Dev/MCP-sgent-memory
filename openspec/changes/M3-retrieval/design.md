# Design: M3-retrieval

## 1. Sparse read path (RET-05) — en `memory_db.py`

`search()` gana dos params opcionales (compatibilidad hacia atrás total):
- `sparse_query: dict | None = None` — formato Qdrant heredado
  `{"indices": [int], "values": [float]}` (salida de `bm25_tokenize`).
- `sparse_weight: float = 0.3` — peso de la componente léxica.

Fusión por fila candidata (ya filtrada por WHERE — el aislamiento no cambia):
```
sparse_score = dot(q_sparse, d_sparse) / (|q_sparse| * |d_sparse|)   # coseno sparse
             = 0.0 si cualquiera falta o es vacío
final = dense + w * sparse_score * (1 - dense)   # BOOST monótono, nunca encoge
score_source incluye "+sparse" cuando sparse > 0
```
Fórmula de boost (NO media ponderada): con sparse=0 → final=dense exacto
(compat total con thresholds M2); sparse solo puede MEJORAR el score hasta 1.
Decisión registrada: la media ponderada (1-w)*dense + w*sparse rompería el
umbral MIN_SCORE reduciendo recall — descartada en diseño.
```
- `d_sparse` se lee de `sparse_json` (columna M2) con parse tolerante
  (JSON corrupto → sparse_score 0, fila sigue con dense).
- Coseno sparse: producto punto solo sobre índices compartidos (dict lookup);
  normas L2 completas. Determinista, stdlib.
- Umbrales: `score_threshold` se aplica al score FINAL (fusión), como antes.
- Empates deterministas: sort por (final desc, id asc) — añadido id como
  clave secundaria para orden estable en tests.

## 2. Degradación L5 (RET-06 / KNOWN-BUG-002) — en L5_routing

Nuevo helper `_embed_or_hash(text) -> tuple[list[float], bool]`:
1. `try: await async_embed(text)` → `(vec, True)`.
2. `except Exception: WARN log + (hash_vector(text, dim), False)`.

Aplicado en `push_reminder`, `detect_context_shift` (×2 llamadas). La
similitud de hashes es determinista (dos textos iguales → sim 1.0), así que
`detect_context_shift` sigue siendo correcto sin embedding server, solo con
sensibilidad léxica exacta. `ContextShiftResult` no cambia. FALL-CLOSED →
DEGRADED, jamás crash.

## 3. Jubilación del micro-LLM (RET-04 / KNOWN-BUG-003)

- Borrar bloque SPEC-4.1 en `_rank_and_fuse` (retrieval/__init__.py:337-347)
  y `rank_by_relevance`/`get_llm` del import (get_llm ya no se usa ahí).
- Borrar `rank_by_relevance()` de `llm/config.py` + export en `llm/__init__.py`.
- Borrar `tests/core/test_llm_ranking.py` (los 4 tests prueban la función
  eliminada; KNOWN-BUG-003 ya está congelado como evidencia en M0).
- NO tocar: `get_small_llm`/`llama_cpp.py`/`get_llm` — consumidor vivo en
  `shared/compliance` (degradación graceful ya implementada ahí). Diferido M5.
- `intent.needs_ranking` queda como metadato inerte de classify_intent (sin
  consumidor) — documentado, no eliminado (contrato público de QueryIntent).

## 4. eval-40 — fixture, juicios y runner

- `tests/eval/fixture_corpus.py`: construye memory.db temporal con ~35 docs
  extraídos del repo real (chunks de los módulos que las queries nombran:
  AuthService→sanitize/fixtures, bm25_tokenize, L0_capture heartbeat,
  combined_score, FTS5, decisiones de arquitectura como docs .md sintéticos).
  IDs deterministas `eval-<n>`, layer/agente variados, agent_scope=shared.
- `scripts/run_eval.py`: corre las 40 queries congeladas (eval-40.yaml) vía
  `retrieve()` + embeddings hash (determinista, sin servicios), calcula
  Recall@5 y MRR contra juicios, escribe
  `openspec/changes/M3-retrieval/evidence/eval-40-results.yaml`.
- `tests/eval/judgments.yaml`: query → doc_ids relevantes (derivados del
  contenido del fixture; juicio sintético pero trazable — cada query nombra
  símbolos que existen en chunks concretos).
- Nota de honestidad (heredada de M0): corpus sintético derivado del repo
  real; mide comportamiento de ranking/fusión, no calidad de producción.

## Failure modes + casos adversariales
- sparse_query con índices no-int/values no-num → ValueError fail-closed,
  cero filas (test unit).
- sparse_json corrupto en fila → dense sigue, sparse=0, warning (test).
- Embedding server caído en L5 → push_reminder/detect_context_shift funcionan
  con hash (test: mock async_embed raising) — KB-002 cerrado.
- queries del eval sin resultados → Recall 0 registrado sin crash (runner
  tolera; honesto).
- Fusión no debe alterar aislamiento: test spy reutilizado de A3 — con
  sparse_query, filas foráneas siguen sin scorearse (adversarial M3).

## Cobertura
tests/core/test_sparse_fusion.py (nuevo, ~10 tests) · tests/core o
test__M3__ L5-degradation (adversarial, isolation) · eval runner en
scripts/ + evidence/ · eliminación test_llm_ranking (difunto).
