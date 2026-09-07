# Análisis Forense — MCP-agent-memory v2.1.0
**Fecha:** 2026-09-07  
**Método:** Protocolo analyze-codebase (Phase 0-6)  
**State:** Solo lectura, sin modificaciones al código

---

## Driving Question
¿Qué necesita el sistema para eliminar embeddings y LLM generation de forma segura y efectiva?

## Depth: `deep` (+ per-module behavior tables)

---

## Executive Summary

El sistema tiene **infraestructura sólida de seguridad** (fail-closed boot, engine-level scope filters, trunk gate) pero **capacidades funcionales limitadas**:

| Dimensión | Estado | Score |
|-----------|--------|-------|
| Seguridad / aislamiento | ✅ Sólido | 9/10 |
| Retrieval funcional | 🔴 Degradado | 3/10 |
| Consolidación automática | 🔴 NO-OPs | 1/10 |
| Datos en producción | 🔴 Vacío | 0/10 |
| Testing | ✅ Robusto | 8/10 |
| Limpieza de código | ⚠️ Dead code | 5/10 |

**Veredicto:** La base de seguridad es excelente. Las capacidades funcionales de memoria (retrieval, consolidación) están rotas o ausentes. La propuesta v3.0 de eliminar embeddings completamente es viable porque el sistema ya opera degradado — quitar la capa de embedding simplifica sin perder funcionalidad real.

---

## Key Findings (Top 5 por impacto)

### 1. 🔴 FINDING-001: Embedding backend configurado pero NO EJECUTÁNDOSE
- `.env` apunta a puerto 8091; `lsof -i :8091` → vacío
- Todo retrieval cae en hash_vector fallback
- Código muerto que añade complejidad innecesaria

### 2. 🔴 FINDING-004: Consolidación L2-L4 es NO-OP por diseño
- 3 funciones (`_promote_l2_l3`, `_promote_l3_l4`, `dream`) retornan `{"status": "disabled"}`
- Las capas L2, L3, L4 del modelo de memoria NUNCA se pueblan automáticamente
- El sistema solo opera L0→L1

### 3. 🔴 FINDING-008: Sin query expansion — retrieval depende de query engineering perfecto
- `classify_intent` usa keyword matching plano
- "auth user token" no encuentra "JWT authentication middleware"
- 18/40 queries tienen zero-recall (45%)

### 4. 🔴 FINDING-012: FTS5 ausente en tabla points
- Conversaciones tienen FTS5; memorias generales NO
- Retrieval depende 100% de cosine similarity (que funciona mal con hash-vectors)
- Esto explica el R@5 = 0.15 en code_lookup

### 5. ⚠️ FINDING-002: `llm_model` es dead code en Config
- Campo presente en config pero nunca usado
- Remanente de pre-M5 cuando existía micro-LLM
- Aumenta complejidad sin valor

---

## Eval-40 Results (Live Run)

```
recall_at_5:    0.425   (documentado: 0.463 — peor que lo reportado)
mrr:            0.476   (documentado: 0.477 — casi igual)
zero_recall:    18/40   (45% de queries no encuentran nada)
code_lookup:    0.15    (catastrófico para uso principal)
conversation_recall: 0.75 (único intent con buen performance)
```

**Nota:** El eval corre con `EMBEDDING_BACKEND=noop` forzado, midiendo retrieval degradado, no real.

---

## Proposed Architecture (v3.0 Deterministic Memory)

Eliminación completa de embeddings:
- BORRAR: `embedding.py` (700 líneas), `embedding_cache.py` (90 líneas)
- AGREGAR: FTS5 en tabla `points` + triggers de sync
- AGREGAR: Tabla `entities` + `relations` para graph determinista
- AGREGAR: Diccionario de sinónimos + query expansion
- ACTIVAR: Consolidación L1→L2, L2→L3, L3→L4 (sin LLM, puramente léxico)
- ELIMINAR: Todo reference a `llm_model`, `EMBEDDING_*` env vars
- REDUCIR: ~7,400 líneas → ~3,500 líneas

**Objetivo:** R@5 ≥ 0.65, latencia < 5ms, cero dependencias externas.
