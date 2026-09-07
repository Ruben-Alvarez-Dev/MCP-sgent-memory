# Tasks: M5-troncal

## 1. Motor + tronco
- [x] 1.1 Guard reserved-scope en memory_db (merged exige flag+approved_by+provenance).
  Acept: tests/core/test_trunk.py. REQ: ISO-16.
- [x] 1.2 approve_promotion en L0_to_L4 (copia con provenance, marca merged_into).
  Acept: e2e approve → visible A16. REQs: ISO-06, ISO-16.
- [x] 1.3 retrieval: merged en cláusula IN de lectura.
  Acept: A16 spy. REQ: ISO-06.

## 2. Cero modelos locales
- [x] 2.1 M: compliance sin micro-LLM (SEMANTIC_UNVERIFIED INFO) + borrado llama_cpp/base/get_llm/get_small_llm + llm/__init__ reducido + config.py sin llm_backend.
  Acept: grep sin refs; suite verde. REQ: restricción dura.

## 3. Extractor + eval
- [x] 3.1 M: snake regex con dígitos (FTS5 íntegro), fallback alfanumérico, routing decision_recall ampliado.
  Acept: tests/core/test_intent_entities.py. REQ: findings eval.
- [x] 3.2 Re-run eval-40 → evidence/eval-40-results-m5.yaml con delta vs M3.
  Acept: runner sin crash; delta documentado.

## 4. Sidecar + adversarial + gate
- [x] 4.1 api_server: MEMORY_HTTP_TOKEN gate (X-Memory-Token, 401, WARN si unset).
  Acept: adversarial sidecar test. REQ: ISO-17.
- [x] 4.2 tests/adversarial/test__M5__trunk.py (A11/A12/A16 + semantic + sidecar).
  Acept: markers isolation; suite verde. REQs: ISO-16, ISO-17.
- [x] 4.3 Suite completa verde + ruff nuevo = 0 + GATE_M5 firmado (cierre del programa). → **PASS (GO) — PROGRAMA CERRADO**
