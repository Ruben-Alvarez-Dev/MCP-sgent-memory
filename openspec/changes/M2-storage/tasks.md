# Tasks: M2-storage

## 1. Núcleo storage
- [x] 1.1 `src/shared/memory_db.py`: schema, WAL, upsert (NULL-vector, no zero), get/delete/count, search/scroll con WHERE parametrizado + coseno stdlib + hash-vector.
  Acept: STO-01-T1..T4, STO-05-T1, ISO-12 verde en tests/core/test_memory_db.py.
  REQs: STO-01, STO-05, ISO-11, ISO-12.
- [x] 1.2 `scope_jail_path` + 5 niveles `c:/p:/a:/s:/u:` en `scope.py`.
  Acept: jail rechaza traversal/symlink (A5/A6/A10-shape); 20+ casos de normalize.
  REQs: STO-04, ISO-07.
- [x] 1.3 `conversation_db._get_db_path()` → memory.db; test de fichero único.
  Acept: STO-02-T1 verde. REQ: STO-02.

## 2. Migración de hot paths (fan-out por dueño de fichero)
- [x] 2.1 L3_facts → MemoryDB; post-filtros borrados (filter al engine); delete/get con filtro.
  Acept: A3 verde vía engine (spy en cursor), ISO-05-T1..T3. REQs: ISO-05, STO-01.
- [x] 2.2 L0_capture + retrieval/__init__.py → MemoryDB (todas las colecciones L0/L1/L2/L3/L4), sin clientes scoped.
  Acept: retrieve() e2e sobre memory.db en tmp; cero import qdrant. REQs: STO-01, ISO-05.
- [x] 2.3 L2_conversations, L5_routing, Lx_reasoning, timeline, health, api_server, unified/* → MemoryDB o refs muertas eliminadas.
  Acept: grep -ri qdrant src/ = 0 (test_no_qdrant.py). REQ: ISO-08.
- [x] 2.4 L0_to_L4_consolidation: promociones → no-ops WARN sin writes mixtos.
  Acept: adversarial consolidation_noop verde. REQ: ISO-06.

## 3. Demolición + migración
- [x] 3.1 Borrar qdrant_client/qdrant_factory/scoped_qdrant/hybrid_qdrant (+ tests dedicados) y refs en config.py (QDRANT_URL queda obsoleto, remover validación).
  Acept: suite import-limpia; ruff verde. REQ: ISO-08.
- [x] 3.2 `scripts/migrate_to_memory_db.py` idempotente desde events.jsonl (sin leer Qdrant).
  Acept: STO-06-T1 verde. REQ: STO-06.

## 4. Adversarial + gates
- [x] 4.1 tests/adversarial: A3, A5, A6, A10, A14, A15 verdes (markers isolation) + extensión del header A1–A16.
  Acept: pytest tests/adversarial -q verde completo. REQs: ISO-05, ISO-07, ISO-11.
- [x] 4.2 KNOWN-BUG-001: suite app reescrita sobre memory.db (3 e2e sin puertos).
  Acept: pytest tests/ -q sin skips por puerto; KNOWN-BUG-001 cerrado en evidence.
- [x] 4.3 Suite completa verde (solo KNOWN-BUG-002/003 permitidos, owners M3) + ruff limpio en ficheros nuevos/tocados.
  Acept: pytest tests/core tests/adversarial tests/app -q → 246 passed / 1 known-failed / 6 skipped; ruff nuevo = 0.
- [x] 4.4 Rellenar GATE_M2.md con re-auditoría G-ISOLATION completa (ISO-01..12) y firmar GO/NO-GO.
  Acept: gate PASS o NO-GO documentado; diferidos con dueño. → **PASS (GO)**
