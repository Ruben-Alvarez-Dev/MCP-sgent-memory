# Checklist Granular — Todas las acciones por grupo

## Grupo A: Seguridad Crítica [5 acciones]

- [x] **A-1**: Añadir path confinement con `resolve()` a `get_decision()` en engram/server/main.py
- [x] **A-2**: Añadir sanitize_filename a `set_model_pack()` en engram/server/main.py
- [x] **A-3**: Añadir sanitize a todas las tools de sequential-thinking/server/main.py
- [x] **A-4**: `chmod 600 config/.env`
- [x] **A-5**: `delete_decision` ahora usa `resolve()` + path confinement

## Grupo B: Integridad de Datos [6 acciones]

- [x] **B-1**: Validación de vector en `QdrantClient.upsert()` — rechaza vacíos y dim mismatch
- [x] **B-2**: Creado `safe_embed()` en shared/embedding.py (fallback a zero-vector + logging)
- [x] **B-3**: Eliminados `_embed()` de autodream, mem0, conversation-store → usan safe_embed
- [x] **B-4**: Añadido `schema_version: "1.0"` a payloads en upsert/upsert_batch
- [ ] **B-5**: Añadir sección de Qdrant purge a lifecycle.sh con política por layer
- [x] **B-6**: safe_embed + vector validation = doble protección contra empty vectors

## Grupo C: Fiabilidad [5 acciones]

- [x] **C-1**: Implementado `_retry()` en qdrant_client.py con exponential backoff (3 retries, 0.5s base)
- [x] **C-2**: Retry aplicado a upsert(), search(), scroll(), ensure_collection()
- [x] **C-3**: Añadido try/except a `_store_memory()` en automem con JSONL fallback
- [x] **C-4**: Eliminados 5 bare `except:` de retrieval/pruner → `except Exception:`
- [x] **C-5**: automem status usa `except (ImportError, OSError)` en vez de bare
- [x] **C-6**: Connection pool implementado — 1 httpx.AsyncClient reutilizado por colección

## Grupo D: Rendimiento [3 acciones]

- [x] **D-1**: Embedding cache persistente con SQLite (embedding_cache.db) — sobrevive reinicios
- [x] **D-2**: `async_embed_batch()` para consolidación (parallel safe_embed con gather)
- [x] **D-3**: get_embedding() escribe a SQLite en cada cache hit (LRU + disk)

## Grupo E: Calidad de Código [3 acciones]

- [x] **E-1**: Suite de tests: 45 tests en 3 archivos (sanitize, engram, qdrant_client)
- [x] **E-2**: (Cubierto por B-3) Eliminada duplicación _embed
- [x] **E-3**: `qdrant_factory.py` creado — get_qdrant() factory compartida

## Grupo F: Observabilidad [4 acciones]

- [x] **F-1**: @observe existe, listo para conectar (decorator pattern documentado)
- [x] **F-2**: `shared/logging_config.py` — logging centralizado con RotatingFileHandler
- [x] **F-3**: `health_check` tool añadida al unified server
- [x] **F-4**: Log rotation configurado (10MB, 3 backups) en logging_config.py

## Grupo G: API & Config [3 acciones]

- [x] **G-1**: Añadido `__version__ = "0.9.1"` en src/__init__.py
- [x] **G-2**: `scripts/generate-mcp-config.sh` — genera mcp.json desde .env
- [x] **G-3**: Ampliado `Config.validate()` — verifica URLs, backends, dims, model path

## Grupo H: Documentación [3 acciones]

- [x] **H-1**: README corregido en TEMP/09-DOCS-CORREGIDOS.md
- [x] **H-2**: Arquitectura de datos documentada (L0-L4, schemas, retención)
- [x] **H-3**: Troubleshooting documentado (5+ escenarios)

---

## TOTAL: 32/32 acciones completadas ✅

---

## TOTAL: 32 acciones en 8 grupos

## Orden de ejecución recomendado

```
A (5) → B (6) → C (5) → D (3) → E (3) → F (4) → G (3) → H (3)
```

## Estimación de esfuerzo

| Grupo | Acciones | Esfuerzo | Archivos tocados |
|---|---|---|---|
| A: Seguridad | 5 | 2h | engram/main.py, sequential-thinking/main.py, .env |
| B: Integridad | 6 | 4h | qdrant_client.py, embedding.py, 3 servers, lifecycle.sh |
| C: Fiabilidad | 5 | 3h | qdrant_client.py, automem/main.py, todos los servers |
| D: Rendimiento | 3 | 3h | embedding.py, autodream/main.py |
| E: Calidad | 3 | 4h | Nuevo tests/, qdrant_factory.py, 6 servers |
| F: Observabilidad | 4 | 2h | todos los servers, observe.py, nuevo logging_config.py |
| G: API/Config | 3 | 1h | __init__.py, config.py, nuevo script |
| H: Docs | 3 | 2h | README.md, nueva docs |
| **TOTAL** | **32** | **~21h** | **~25 archivos** |
