# Design: M5-troncal

## 1. Trunk gate en el motor (ISO-16) — `memory_db.py`

Constante: `_MERGED_SCOPES = {"merged"}` (canal troncal; `global` queda
reservado-inservible). En `_prepare_row`, ANTES de persistir:

```
si payload["agent_scope"] in _MERGED_SCOPES:
    exigir allow_reserved_scope=True (param de upsert/upsert_batch, default False)
    exigir payload["approved_by"]  (string no vacío, identidad humana)
    exigir payload["provenance"]   (lista no vacía de {from_scope, point_id})
    → si falta algo: ScopeError, CERO I/O (fail-closed)
```

`update_payload` con merge a merged-scope exige las mismas claves presentes en
el payload resultante. `scroll/search` leen `merged` igual que cualquier scope
(sin flag). Herramienta de entrada: `approve_promotion(point_ids, approved_by)`
en L0_to_L4_consolidation — copia los puntos fuente a scope `merged` con
`provenance=[{from_scope, point_id, approved_by, approved_at}]`, marca los
origen con `merged_into=<nuevo id>` y devuelve los nuevos ids. Las promociones
automáticas siguen siendo no-ops WARN (M2, ISO-06).

## 2. Lectura pública de merged (retrieval)

`_retrieve_hybrid`: la cláusula `agent_scope IN (...)` pasa a incluir
`"merged"`: own + shared + merged (el tronco es conocimiento común aprobado).
A11/A12/A16 cubren: A11 automatismo no escribe merged (guard), A12 merged sin
provenance es imposible (guard), A16 merged es legible por todos (read test).

## 3. Cero modelos locales en código (restricción dura)

- `shared/compliance`: `verify_semantic` pierde get_small_llm; las reglas con
  `semantic_prompt` se reportan como violación informativa `SEMANTIC_UNVERIFIED`
  (severity INFO, detalle "requires harness LLM review") — la verificación
  semántica pertenece al LLM del agente/harness, no a un modelo local.
- Borrar: `llm/llama_cpp.py`, `llm/base.py`, y de `llm/config.py`:
  get_llm, get_small_llm, list_available_backends, _get_llama_cpp y helpers.
  `llm/__init__.py` exporta SOLO `classify_intent`, `QueryIntent`.
- `shared/config.py`: fuera `llm_backend` + validación LLM_BACKEND.
- `L0CaptureStatusResult.llama_cpp`: verificar su origen — si refleja el
  EMBEDDING backend, se conserva (embeddings ≠ generación); si sondeaba el
  LLM local, se elimina junto con el sondeo.

## 4. Entity extractor (findings eval)

- snake regex: `[A-Z_]{2,}` → `[A-Z_0-9]{2,}` — `FTS5` íntegro, `6333` capturable.
- fallback alfanumérico: `[a-záéíóúüñA-Z0-9_]{3,}` (conserva dígitos).
- routing `decision_recall`: ampliar keywords (decidimos, decisión, decisiones,
  decidir, acuerdo, elegimos, motivo, razón, why did we, we decided, rationale,
  choice, approved) en ES/EN.
- Re-medición: re-run eval-40 → evidence/eval-40-results-m5.yaml con delta vs M3.

## 5. Sidecar HTTP con token opcional (ISO-17)

`api_server`: si `MEMORY_HTTP_TOKEN` está seteado, todo endpoint exige header
`X-Memory-Token` (compare_digest); sin env → comportamiento actual (localhost,
sin auth) + WARN en el log de arranque. Hereda la identidad M4 del proceso.

## Failure modes + adversarial
- approve_promotion sin approved_by → ScopeError (A11: automatismo bloqueado)
- upsert directo a merged sin triple → ScopeError en engine (fail-closed)
- merged sin provenance imposible por constructor (A12)
- merged legible desde cualquier scope (A16, spy de candidates incluye merged)
- semantic rules sin LLM → SEMANTIC_UNVERIFIED INFO, nunca crash
- sidecar sin token header con env seteado → 401; token correcto → 200
- extractor: "FTS5" íntegro; "puerto 6333" captura 6333 (unit tests)

## Cobertura
tests/core/test_trunk.py (guard + approve) · tests/adversarial/test__M5__trunk.py
(A11/A12/A16 + semantic + sidecar token) · tests/core/test_intent_entities.py
· eval re-run evidencia.
