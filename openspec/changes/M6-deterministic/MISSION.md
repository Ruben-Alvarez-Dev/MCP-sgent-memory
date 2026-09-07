# MISSION BRIEF — M6-deterministic

## Mission Statement
Eliminar toda dependencia de embeddings (BGE-M3, llama-server, hash-vectors)
del pipeline de retrieval. El sistema passará a ser 100% determinista:
FTS5 + synonym expansion + entity graph boost + metadata filters.
Las capas L2-L4 se activan con consolidación léxica (sin LLM).

## Scope
- **In scope**: FTS5 en points, entities/relations tables, synonym dict,
  retrieval lexical-first, consolidación activa L1→L4, cleanup embedding.py,
  migration script, tests, docs.
- **Out of scope**: borrado de columna `vector` (M7), eval con corpus real,
  graph neural entities, multi-idioma dinámico.

## Team Structure — 4 squads en paralelo

### Squad A — Storage (STO-07, STO-08, STO-09, STO-10)
**Owner:** motor SQLite  
**Tasks:** 1.1, 1.2, 1.3, 1.4, 7.1, 7.2  
**Dependencies:** Ninguna (schema aditivo)  
**Duration estimada:** 1 día  

### Squad B — Entity System (STO-08, RET-08)
**Owner:** entity extraction + graph  
**Tasks:** 2.1, 2.2, 2.3, 8.2, 8.3, 8.6  
**Dependencies:** Squad A (tablas creadas primero)  
**Duration estimada:** 1.5 días  

### Squad C — Retrieval Pipeline (RET-01, RET-07, RET-08, RET-09)
**Owner:** router de recuperación  
**Tasks:** 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 8.4, 8.7  
**Dependencies:** Squad A (FTS5) + Squad B (entities)  
**Duration estimada:** 2 días  

### Squad D — Consolidation + Cleanup (MEM-01..03, cleaning)
**Owner:** consolidación + cleanup general  
**Tasks:** 5.1, 5.2, 5.3, 5.4, 6.1..6.6, 8.5, 8.6, 9.1..9.6, 10.1..10.3  
**Dependencies:** Squad B (entities para consolidación)  
**Duration estimada:** 2 días  

## Serialización crítica (caminho crítico)
```
Día 1:  Squad A (schema) → Squad B (entities) inicia
Día 2:  Squad B (entities) completa → Squad C (retrieval) inicia
        Squad D (consolidation) inicia en paralelo
Día 3:  Squad C (retrieval) completa → integración
        Squad D (cleanup) completa
Día 4:  Tests integrationales, eval-40 re-run, migration verification
Día 5:  Docs, GATE sign-off, cierre
```

## Estrategia de ejecución
1. **Día 1:** Squad A implementa schema FTS5+entities+relations. Squad B empieza
   entity extraction unitaria (tests first). Sin dependencias entre squads.
2. **Día 2:** Squad A termina. Squad B integra extraction en memory_db.
   Squad C empieza query expansion (depende de FTS5 table existente).
   Squad D empieza consolidation L1→L2 (independiente).
3. **Día 3:** Squad C integra FTS5 search + entity boost en retrieval pipeline.
   Squad D activa consolidación L2→L3, L3→L4 y hace cleanup embedding.py.
   Todos los squads integran sus cambios contra main.
4. **Día 4:** Suite completa de tests. Migration script verificado.
   Eval-40 re-run con FTS5. Verificación de que grep embedding = 0 refs.
5. **Día 5:** Docs actualizadas. GATE_M6 firmado. Commit de cierre.

## Hard constraints (no negociables)
- Cero referencias a `shared.embedding` en src/ post-M6
- Cero modelos locales: no BGE-M3, no qwen, no micro-LLM
- Scope isolation: entities/relations filtrados por agent_scope en SQL
- FTS5 queries parameterizadas (sin SQL injection)
- Consolidación idempotente (running twice = same result)
- Rollback: revert del commit restaura estado M5 completamente

## Delivery target
- ~3,500 líneas de código (down from ~7,400)
- R@5 ≥ 0.60 en eval-40 (up from 0.425 degraded)
- Latencia search < 5ms (down from ~50ms con embeddings)
- Cero dependencias externas de red
- 400+ tests passing (up from 321)
