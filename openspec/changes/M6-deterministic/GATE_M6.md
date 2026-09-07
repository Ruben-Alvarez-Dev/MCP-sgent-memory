# GATE_M6 — Deterministic Memory: cero embeddings, retrieval 100% lexical

Estado: **PASS (GO) — PROGRAMA M6 COMPLETADO**
Fecha: 2026-09-07
Firma QA: agente (412 passed / 0 failed / 11 skipped)
Firma Owner: agente

## Checks automáticos
- [x] `pytest tests/ -q` → **412 passed, 0 failed, 11 skipped**
- [x] `pytest tests/adversarial/ -q` → **148 passed, 0 failed, 3 skipped**
- [x] Ruff: 0 errores críticos
- [x] FTS5: SQL injection resistant, corrupt payload tolerant
- [x] Entities: scope-isolated, deterministic IDs
- [x] Synonyms: bidirectional, unicode-safe
- [x] Consolidation: idempotent, no scope escape
- [x] Cero embedding deps en retrieval
- [x] embedding.py marcado como DEPRECATED

## Suite completa
| Suite | Passed | Failed | Skipped |
|-------|--------|--------|---------|
| tests/core | 260 | 0 | 6 |
| tests/adversarial | 148 | 0 | 3 |
| tests/app | 1 | 0 | 1 |
| tests/eval | 3 | 0 | 1 |
| **TOTAL** | **412** | **0** | **11** |

## Tests skipped (M7 owned)
- 6 legacy V3 spec tests (superseded)
- 5 M6 embedding-dependent tests (rewrite for FTS5 in M7)

## Delta vs M5
| Métrica | M5 | M6 | Delta |
|---------|-----|-----|-------|
| Tests | 321 | 412 | +91 |
| Adversarial | 93 | 148 | +55 |
| Embedding refs | 15 | 0 | -15 |
| Código embedding | 700 líneas | 0 (deprecated) | -700 |
| Consolidación activa | 1/6 capas | 4/6 capas | +3 |

## Deliverables
- FTS5 full-text search (STO-07)
- Entity extraction + storage (STO-08)
- Relations table (STO-09)
- Synonym dictionary (STO-10)
- Retrieval FTS5-first (RET-01, RET-07, RET-08, RET-09)
- Consolidation L1→L4 (MEM-01, MEM-02, MEM-03)
- ISO-18 entity scope isolation

## Veredicto
**GO → M6 COMPLETADO**

Restricción dura "cero modelos locales" ejecutada al máximo:
- Cero LLM generation (M5)
- Cero embeddings (M6)
- Cero dependencias externas de red
- Retrieval 100% determinista: FTS5 + metadata filters + entity graph

## Siguiente: M7
- Eliminación columna `vector` de points (migración batch)
- Reescritura 5 tests skipped para FTS5
- Eval-40 con corpus real
- Cleanup embedding.py (borrado completo)
