# 📋 INVENTARIO EXHAUSTIVO DE TOUCHPOINTS QDRANT — Demolición M2

**SOLO LECTURA completada.** Un solo punto de entrada MCP en caliente: `src/unified/server/main.py` (stdio, referenciado por `etc/mcp.json`, `install/config.sh`, `install/app-install.sh`, `scripts/generate-mcp-config.sh`, `run-daemon.sh`). Todo lo demás cuelga de ahí o está muerto.

## Tabla de touchpoints

| Fichero | Símbolos qdrant | Colecciones | Env vars | ¿Hot-path? | Acción de demolición |
|---|---|---|---|---|---|
| `src/shared/qdrant_client.py` | `QdrantClient` (`health`, `ensure_collection`, `collection_info`, `count`, `upsert`, `upsert_batch`, `get`, `delete`, `search`, `scroll`, `with_collection`, `close`, `_retry`), `_validate_payload_keys`, `_QDRANT_RESERVED_KEYS` | todas (parametrizada) | `QDRANT_URL` (fallback L61) | ✅ HOT (cliente de los 6 servers) | **BORRAR AL FINAL** — último fichero en caer cuando 0 imports |
| `src/shared/qdrant_factory.py` | `get_qdrant()`, `_clients` | L0_L4_memory | `QDRANT_URL` | ❌ MUERTO (0 imports en prod; ISO-08) | **BORRAR ENTERO YA** |
| `src/shared/scoped_qdrant.py` | `ScopedQdrantClient` (`_get_client`, health, ops delegadas) | `{base}_{agent_scope}` | — | ❌ MUERTO (solo `tests/core/test_agent_scope_qdrant.py`) | **BORRAR ENTERO + su test** |
| `src/shared/hybrid_qdrant.py` | `HybridQdrantClient`, `_parse_agent_level`, `LEVEL_MAP` | `{base}_{agent_scope}` + payload-filter | — | ❌ MUERTO (solo `test_agent_scope_qdrant.py`) | **BORRAR ENTERO + su test** |
| `src/shared/embedding.py` | `bm25_tokenize()` (formato sparse Qdrant L263-291); resto agnóstico | — | ninguna de qdrant | ✅ HOT (L0/L2/L3_facts/L5/consolidation/health) | CONSERVAR; `bm25_tokenize` queda huérfano (sparse read RET-05 → M3) |
| `src/shared/config.py` | campos `qdrant_url`, `qdrant_collection` + validación URL/puerto (L30-32, 79-81, 119-131) | L0_L4_memory (default) | `QDRANT_URL`, `QDRANT_COLLECTION` | ✅ HOT | **PODAR** campos + validación |
| `src/shared/health.py` | `check_qdrant()` (L99), `run_health_check(qdrant_url)` (L236), label launchd `com.agent-memory.qdrant` (L203), CLI `--qdrant-url` | — (lista `/collections`) | `QDRANT_URL` | ⚠️ Operativo (watchdog/CLI), no MCP | **PODAR** check + label + flag CLI |
| `src/shared/timeline.py` | `HybridTimeline` (`_get_qdrant`, `append_async`, `search_semantic`), rama `"hybrid"` en `create_timeline` | `timeline` (propia) | — (kwarg, default `:6333`) | ❌ MUERTO (0 imports en src; test solo usa SQLite/JSONL) | **PODAR HybridTimeline** (fichero entero candidato a borrado: timeline sin consumidores en prod) |
| `src/shared/conversation_db.py` | **cero código** (solo docstring L4) | — | — | ✅ HOT (L2) | Nada qdrant; fusión en memory.db por M2-STO es tema aparte |
| `src/shared/api_server.py` | `_verify_memories()`: httpx directo a `/points/scroll`, `/points`, `/points/payload` (L38-39, 63, 103, 164) | L0_L4_memory | `QDRANT_URL`, `QDRANT_COLLECTION` | ✅ HOT (sidecar :8890, hooks OpenCode) | **REESCRIBIR** `_verify_memories` sobre memory.db o eliminar endpoint |
| `src/shared/result_models.py` | campos `qdrant: str = "OK"` en `L0CaptureStatusResult` (L36) y `VkCacheStatusResult` (L93) | — | — | ✅ HOT (esquema MCP) | **PODAR** campos (actualizar `status()` de L0 y L5) |
| `src/shared/env_loader.py` | crea `data/qdrant/` (L102), setea `QDRANT_DATA` (L120), docstring `bin/qdrant` | — | `QDRANT_DATA` | ✅ HOT (todos llaman `load_env()`) | **PODAR** dir + var + comentario |
| `src/shared/vault_manager/__init__.py` | `VaultManager.rebuild(qdrant_url)` scroll de 3 colecciones (L548-612); keyword "qdrant" L394 | L0_L4_memory, L2_conversations, L3_facts | — | ❌ MUERTO (`rebuild()` sin callers en prod ni tests) | **PODAR** `rebuild()` + docstring |
| `src/shared/retrieval/__init__.py` | `QdrantClient` import, `_get_scoped_client`, cache `_qdrant_clients`, `_retrieve_hybrid()` (search + filter layer, L235-285); import muerto de `index_repo` (L29) | L0_L4_memory, L2_conversations (`CONV_COLLECTION`), L3_facts (`L3_FACTS_COLLECTION`), `{coll}_{agent_scope}` | `QDRANT_URL`, `QDRANT_COLLECTION`, `CONV_COLLECTION`, `L3_FACTS_COLLECTION` | ✅ HOT (`L5_routing.request_context` → `retrieve`; sidecar `/api/request-context`) | **REESCRIBIR** `_retrieve_hybrid` (RET-01); borrar L29 |
| `src/shared/retrieval/index_repo.py` | `_ensure_collection`, `upsert_repository_index`, `build_repo_index_points`, CLI argparse (upsert denso+sparse httpx) | L0_L4_memory | `QDRANT_URL`, `QDRANT_COLLECTION` | ❌ MUERTO (importado L29 de retrieval/__init__ pero jamás llamado; CLI manual) | **BORRAR ENTERO** + quitar import |
| `src/shared/retrieval/code_map.py` | string `"qdrant"` en dirs excluidos (L637) | — | — | ✅ indirecto | Cosmético; dejar |
| `src/L0_capture/server/main.py` | global `qdrant`; `ensure_collection()`, `upsert(sparse)`, `health()`, `count()`; `register_tools(target_qdrant)` | L0_L4_memory | vía config | ✅ HOT (`memorize`, `ingest_event`, `heartbeat`, `status`) | **REESCRIBIR** upsert/count → memory.db |
| `src/L0_to_L4_consolidation/server/main.py` | `ensure_collection(sparse=False)`, `scroll(layer=N)`, `upsert`, `upsert_batch` en consolidate×3, dream, force_promote, get_layer | L0_L4_memory | vía config | ✅ HOT | **REESCRIBIR** sobre SQL (elimina de paso writes mixtos ISO-06) |
| `src/L5_routing/server/main.py` | `qdrant.with_collection(f"{coll}_{agent_id}")` (L116,154), `search` (L117,155), `health` (L162); `from shared.retrieval import retrieve` | L0_L4_memory + per-agent | vía config | ✅ HOT (`request_context`, `context_shift`, `status`) | **REESCRIBIR** búsqueda |
| `src/L2_conversations/server/main.py` | `ensure_collection(sparse=True)`, `upsert(sparse)` best-effort (L67-84), `search(filter scope)` (L136), `health`; instancia propia en `register_tools` | L2_conversations | vía config | ✅ HOT | **ELIMINAR rama vectorial** (FTS5/SQLite ya cubre; ISO-06) |
| `src/L3_facts/server/main.py` | CRUD completo: `ensure_collection(sparse=True)`, `upsert`, `search`, `scroll`, `get`, `delete`, `health`, `count`; instancia propia `QdrantClient(url,"L3_facts",dim)` | L3_facts | vía config | ✅ HOT | **REESCRIBIR** a SQL |
| `src/L3_decisions/server/main.py` | solo placeholder `_qdrant` en `register_tools` (L150, sin uso) | — | — | ✅ HOT pero sin qdrant (FS-only) | Quitar parámetro al demoler |
| `src/Lx_reasoning/server/main.py` | ídem: `_qdrant` placeholder (L168) | — | — | ✅ HOT pero sin qdrant | Quitar parámetro |
| `src/unified/server/main.py` | global `qdrant` (L30), `_ensure_initialized()` crea 3 colecciones sparse (L109-121), `health_check()` (health + counts, L145-165), inyecta `qdrant` en los 7 `register_tools` | L0_L4_memory, L2_conversations, L3_facts | vía config | ✅ HOT **ENTRYPOINT** | **REESCRIBIR** init/health → memory.db |
| `src/unified/server/main_http.py` | global `qdrant` + `register_tools` (L28-67) | las 3 | vía config | ❌ MUERTO (0 referencias; todos los launchers usan `main.py` stdio) | **BORRAR ENTERO** |
| `src/unified/server/backpack.py` | instancia `QdrantClient(...)` module-level (L37) **jamás usada**; sin `register_tools`; importado por NADIE | L0_L4_memory | vía config | ❌ MUERTO | **BORRAR ENTERO** |
| `src/unified/server/gateway.py` | cero qdrant (aiohttp puro) | — | — | — | Nada |
| `bin/vault_processor.py` | cero qdrant (FS-only) | — | — | — | Nada |

## 🗑️ Ficheros borrables ENTEROS (sin cirugía)

**Código (5):**
1. `src/shared/qdrant_factory.py` — muerto, ISO-08
2. `src/shared/scoped_qdrant.py` — muerto (+ borrar `tests/core/test_agent_scope_qdrant.py`)
3. `src/shared/hybrid_qdrant.py` — muerto (ídem)
4. `src/shared/retrieval/index_repo.py` — muerto (quitar antes el import de `retrieval/__init__.py:29`)
5. `src/unified/server/main_http.py` — muerto (entrypoint real es `main.py`)
6. `src/unified/server/backpack.py` — muerto (instancia qdrant fantasma, 0 importers)

**Casi-entero (condicional):** `src/shared/timeline.py` (0 importers en prod; al podar `HybridTimeline` queda timeline sin uso real → candidato a borrado completo).

**Infra Qdrant:**
- `bin/qdrant` (binario), `bin/config.yaml`, `bin/storage/`, `bin/snapshots/`
- `src/shared/qdrant/` (dir completo: `config.yaml`, `start.sh`, `stop.sh`, `start-qdrant.sh`)
- `scripts/start-qdrant.sh`
- `etc/qdrant.yaml`
- `data/qdrant/` (0B), `qdrant.log` (raíz), `~/.memory/qdrant.log` y `qdrant-error.log` (paths del plist)
- Plist launchd `com.agent-memory.qdrant` (lo genera `configure.sh`; ahora mismo no cargado en `~/Library/LaunchAgents`)

**Tests/bench qdrant-dependientes:**
- `tests/core/test_qdrant_client.py` → BORRAR
- `tests/core/test_agent_scope_qdrant.py` → BORRAR
- `tests/app/test_retrieve_e2e.py` → BORRAR (skip-marked, exige :6333 real)
- `bench/e2e_bench.py`, `bench/flow_verification.py` → BORRAR/reescribir (tocan además colecciones externas `automem` y `mem0_memories`)

## ✂️ Cirugía parcial (podar, no borrar)

- `config.py`: campos `qdrant_url`/`qdrant_collection` + validación
- `env_loader.py`: `data/qdrant` + `QDRANT_DATA`
- `health.py`: `check_qdrant`, label launchd, `--qdrant-url`
- `result_models.py`: 2 campos `qdrant`
- `api_server.py`: `_verify_memories` → memory.db
- `retrieval/__init__.py`: `_retrieve_hybrid` + import L29 + envs `CONV_COLLECTION`/`L3_FACTS_COLLECTION`
- `timeline.py`: clase `HybridTimeline` + rama `"hybrid"`
- `vault_manager/__init__.py`: `rebuild()`
- `embedding.py`: `bm25_tokenize` (diferir a M3 con RET-05)
- Servidores L0/L0_to_L4/L2/L3_facts/L5/unified-main: reescritura a memory.db (el grueso de M2)
- `L3_decisions`/`Lx_reasoning`: quitar param `_qdrant`

## 🔧 Shell/config con qdrant (podar)

| Fichero | Qué |
|---|---|
| `config/.env:1-2` | `QDRANT_URL`, `QDRANT_COLLECTION` |
| `scripts/lifecycle.sh` | backup/purge/rotation Qdrant (~L101-106, 135-165, 304-405) + `QDRANT_BACKUP_KEEP` |
| `scripts/watchdog.sh:22,73,102-104` | `QDRANT_URL`, restart `com.agent-memory.qdrant` |
| `scripts/configure.sh:49,66,79,108,155-177` | generación plist qdrant |
| `scripts/generate-mcp-config.sh:30` | `QDRANT_URL` en mcp.json |
| `install/bootstrap.sh:156-198+` | Step 3/6 + descarga binario |
| `install/app-install.sh:8,39,69,76-77,91-92` | envs + .env template |
| `pyproject.toml:8` | descripción "Qdrant client" (cosmético); revisar si `httpx` queda sin consumidores tras M2 |

## Env vars totales a extinguir
`QDRANT_URL` · `QDRANT_COLLECTION` · `QDRANT_DATA` · `CONV_COLLECTION` · `L3_FACTS_COLLECTION` · `QDRANT_BACKUP_KEEP`

## Colecciones totales tocadas
`L0_L4_memory` (7 consumidores) · `L2_conversations` (4) · `L3_facts` (4) · `timeline` (HybridTimeline) · `{base}_{agent_id}` dinámicas (L5, scoped/hybrid, retrieval) · `test_scoped*`/`test_hybrid*` (tests) · `automem`/`mem0_memories` (bench)

**Orden de demolición seguro:** (1) muertos puros → (2) infra binaria/plists/logs → (3) reescritura hot-path a `memory.db` → (4) poda config/env/scripts/install → (5) `qdrant_client.py` último (cuando grep dé 0 imports) → (6) tests/bench.
| `tests/core/test_qdrant_client.py` | Test unitario exclusivo de `QdrantClient` | ❌ | **BORRAR ENTERO** |
| `tests/core/test_agent_scope_qdrant.py` | Único cliente de scoped/hybrid_qdrant | ❌ | **BORRAR ENTERO** |
| `tests/app/test_retrieve_e2e.py` | Qdrant + embedding reales; crea/borra colección | ❌ (skip si no hay Qdrant) | **BORRAR ENTERO** |
| `tests/app/test_conversation_store_integration.py` | Importa `QdrantClient`, requiere :6333 | ❌ | **BORRAR ENTERO** (o reescribir) |
| `tests/app/conftest.py` | Skip-guard "requires Qdrant :6333" | ❌ | Purgar guard |
| `tests/core/test_mcp_modules.py` | `fake_qdrant = MagicMock()` en register_tools | ❌ | Ajustar mock |
| `tests/core/test_conversation_store.py`, `test_v3_spec_features.py`, `test_vault_manager.py` | Solo docstrings/strings "qdrant" | ❌ | Cosmético |
| `bench/flow_verification.py` | `qdrant_search()`, `qdrant_count()` — verifica flujos vía HTTP crudo | ❌ | **BORRAR ENTERO** (su propósito es validar Qdrant) |
| `bench/e2e_bench.py` | `qdrant_health`, `qdrant_collections` + payloads de prueba | ❌ | Purgar tests Infra |
| `src/shared/qdrant/{start.sh, start-qdrant.sh, stop.sh}` | ciclo de vida del binario | ❌ | **BORRAR DIR ENTERO** |
| `bin/qdrant`, `bin/config.yaml`, `bin/snapshots/`, `bin/storage/` | binario + storage del servidor | ❌ | **BORRAR** |
| `data/qdrant/`, `qdrant.log`, `.qdrant-initialized` | datos/logs/marcador | ❌ | **BORRAR** |
| `install/bootstrap.sh`, `services.sh`, `verify.sh`, `app-install.sh`, `config.sh`, `manifest.json` (dep `qdrant-client` — **nunca importada en código**, solo httpx), `install.sh` | descarga binario, crea colecciones vía curl, checks | ❌ | Purga masiva (services.sh conserva parte llama-server) |
| `scripts/{configure.sh, watchdog.sh, lifecycle.sh, start-qdrant.sh, generate-mcp-config.sh}` | launchd `com.agent-memory.qdrant`, watchdog, snapshots | ❌ | Purga (watchdog conserva embedding/llama) |
| `config/mcp.json`, `config/.env.example`, `README.md`, `.gitignore` | `QDRANT_URL`, `QDRANT_COLLECTION`, paths storage | ❌ | Actualizar |

## 🌐 Variables de entorno a eliminar (consolidado)

`QDRANT_URL` · `QDRANT_COLLECTION` · `QDRANT_DATA` · `CONV_COLLECTION` · `L3_FACTS_COLLECTION` · (`EMBEDDING_DIM` solo como dim de colección en `qdrant_factory`; la dim del embedding sobrevive) — más el launchd label `com.agent-memory.qdrant`.

## 🗑️ LISTA FINAL — ficheros BORRABLES ENTEROS

**Borrables HOY (código muerto, cero importadores de producción):**
```
src/shared/qdrant_factory.py
src/shared/scoped_qdrant.py
src/shared/hybrid_qdrant.py
tests/core/test_agent_scope_qdrant.py
src/shared/retrieval/index_repo.py        (+ import muerto en retrieval/__init__.py:29)
bench/flow_verification.py
src/shared/qdrant/                        (dir: start.sh, start-qdrant.sh, stop.sh)
bin/qdrant · bin/snapshots/ · bin/storage/ · bin/config.yaml (cfg de qdrant)
data/qdrant/ · qdrant.log · .qdrant-initialized
tests/core/test_qdrant_client.py
tests/app/test_retrieve_e2e.py
tests/app/test_conversation_store_integration.py
```

**Borrables tras rewire del hot-path (son 100% Qdrant):**
```
src/shared/qdrant_client.py               (último en caer: 7 servidores + retrieval + timeline dependen)
tests/app/conftest.py                      (solo existe como guard de Qdrant/embedding)
pip uninstall qdrant-client                (declaro: el código NUNCA importó el paquete oficial, todo es httpx crudo)
```

**Purga parcial (NO borrar entero):** `timeline.py` (solo `HybridTimeline`), `api_server.py` (solo `_verify_memories`), `vault_manager` (solo `rebuild()`), `embedding.py` (solo `bm25_tokenize`), `bench/e2e_bench.py` (bloque Infra), `install/services.sh` (parte qdrant), `result_models.py`/`config.py`/`env_loader.py`/`health.py` (campos/bloques), `L3_decisions`+`Lx_reasoning` (solo parámetro `_qdrant` muerto).

**Intocables confirmados (0 touchpoints):** `conversation_db.py`, `gateway.py`, `retrieval/pruner.py`, `retrieval/repo_map.py`, `retrieval/code_map.py` (1 palabra cosmética), `bin/vault_processor.py`.

**Nota crítica de demolición:** el punto de entrada real según `config/mcp.json` es `src/unified/server/main.py` — ahí viven los 3 `ensure_collection` y la inyección del cliente a los 7 módulos; cualquier rewiring debe empezar por desacoplar `register_tools(mcp, qdrant, config)` de esa firma.
