# GATE_M5 — troncal: merged con aprobación+provenance, cero modelos locales, findings del eval

Estado: PASS (GO) — CIERRA EL PROGRAMA memory-zero
Fecha: 2026-09-06
Firma QA: arquitecto (313 passed / 0 failed / 6 skipped + 87 adversarial verificados)
Firma Owner (arquitecto): arquitecto

## Checks automáticos
- [x] `pytest tests/ -q` → **313 passed, 0 failed, 6 skipped** (285 M4 + 28 nuevos M5)
- [x] `pytest tests/adversarial -q` → **87 passed** (81 + 6 M5: A11/A12/A16 + semantic + sidecar ×2)
- [x] `pytest tests/core/test_trunk.py tests/core/test_intent_entities.py -q` → **22 passed**
- [x] `ruff check` ficheros NUEVOS M5 (test_trunk, test__M5__trunk, test_intent_entities) → **limpio**; tocados sin violaciones NUEVAS
- [x] `grep get_small_llm|get_llm|llama_cpp` (excl. embedding) → **cero refs de generación**; llm/ reducido a classify_intent+QueryIntent; llama_cpp.py/base.py BORRADOS; config.py sin llm_backend
- [x] ISO-16: upsert a merged sin triple aprobación → ScopeError cero I/O (A11); provenance obligatoria por constructor (A12)
- [x] ISO-17: sidecar 401 sin/verificación constante-time con X-Memory-Token; WARN si unset
- [x] eval-40 re-medido: **R@5 0.425→0.463 · MRR 0.4542→0.4767 · zero-recall 19→17** → evidence/eval-40-results-m5.yaml

## Checklist humana
- [x] **Tronco = único canal a merged**: exige allow_reserved_scope + approved_by + provenance[{from_scope,point_id}] (imposible representar merged sin auditoría — A12 por construcción); fuentes marcadas merged_into, nunca destruidas
- [x] **Restricción dura ejecutada en código**: compliance emite SEMANTIC_UNVERIFIED (low) para reglas semánticas — la verificación semántica pertenece al LLM del harness, no a un modelo local; `intent.needs_ranking` queda como metadato sin consumidor (documentado)
- [x] Findings del eval atendidos con medición: FTS5 íntegro (snake regex con dígitos), fallback alfanumérico, decision_recall ampliado (ES/EN); delta honesto: code_lookup R@5 baja 0.35→0.30 por re-routing — registrado, no maquillado
- [x] ISO-17 sidecar: /api/health exento (liveness), resto 401 sin token; localhost sin env sigue válido con WARN
- [x] Diferidos FINALES (documentados, con dueño=owner): bind user_id (requiere modelo de usuarios) · multi-token por agente · mTLS · sqlite-vec si >50k puntos · README métricas de programa (post-cierre)
- [x] Rollback: revert; guards aditivos; sin migraciones

## Re-auditoría de restricciones duras del programa (cierre)
- [x] Cero modelos locales → **ejecutado en código** (solo embeddings como infraestructura)
- [x] Capas L0-L5 preservadas como conceptos → sí (física unificada en memory.db)
- [x] Default-deny + scope filtro duro → sí (engine WHERE; trunk aprobado; identidad ligada)
- [x] Sin human-approved merge automático → sí (approve_promotion exige approved_by)
- [x] Toda misión con GATE firmado → M0..M5 completos

## Decisión
- [x] GO → **PROGRAMA memory-zero COMPLETO**. Mantenimiento futuro: issues nuevos vía openspec changes.
- [ ] NO-GO: —
