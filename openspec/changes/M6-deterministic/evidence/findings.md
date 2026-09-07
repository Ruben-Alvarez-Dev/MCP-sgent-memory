# Findings — MCP-agent-memory v2.1.0 (Forensic Report)

All findings are evidence-backed with file:line references and live probes.

---

## FINDING-001: Port drift — EMBEDDING_BACKEND=llama_server pero nada escucha en 8091

**Evidence:**
- `config/.env:4` → `LLAMA_SERVER_URL=http://127.0.0.1:8091`
- `config/mcp.json:10` → `"LLAMA_SERVER_URL": "http://127.0.0.1:8091"`
- `src/shared/config.py:37` → default `"http://127.0.0.1:8081"`
- `src/shared/embedding.py:380` → default `"http://127.0.0.1:8081"`
- `install/app-install.sh:277` → hardcodes port 8081
- `install/bootstrap.sh:157` → `EMB_PORT=8081` by default
- **Probe:** `lsof -i :8091` → EMPTY; `lsof -i :8081` → EMPTY
- `ps aux | grep llama` → Ollama running (general LLM), no embedding server

**Impact:** Every embedding call falls through to `safe_embed` -> zero-vector fallback -> `hash_vector` -> degraded retrieval. The eval confirms: code_lookup R@5 = 0.15 because dense channel is pure hash-noise.

**Verdict:** CRITICAL — Embedding backend configured but not running. All semantic retrieval is degraded to lexical+hash hybrid with poor recall.

---

## FINDING-002: `llm_model` es dead code en config

**Evidence:**
- `src/shared/config.py:41` → `llm_model: str = "qwen2.5:7b"`
- `src/shared/config.py:86` → loaded from `os.getenv("LLM_MODEL")`
- `grep -rn "llm_model" src/` → ZERO use sites beyond config definition
- `src/shared/llm/__init__.py:3` → "Zero local generation models" (documented M5 constraint)

**Verdict:** DEAD CODE — Configuración huérfana que aumenta complejidad sin valor.

---

## FINDING-003: `hash_vector` genera pseudo-vectores con cosine negativa para texto diferente

**Evidence (live probe):**
```python
v1 = hash_vector('hello world', 10); v2 = hash_vector('goodbye world', 10)
cosine(v1, v2) = -0.100925   # NEGATIVA — empeora el ranking
```
- `src/shared/memory_db.py:78-110` — usa SHA-256 stream -> normaliza a [-1,1]
- `src/shared/memory_db.py:505` — usado como fallback cuando embedding falla

**Verdict:** DEGRADED — El fallback hash_vector es peor que no buscar nada (score negativo vs no aparece).

---

## FINDING-004: Consolidación L2->L3 y L3->L4 son NO-OPs documentados

**Evidence:**
- `src/L0_to_L4_consolidation/server/main.py:116-124` — retornan `{"status": "disabled"}` sin escribir
- `src/L0_to_L4_consolidation/server/main.py:272-275` — `dream()` retorna `{"status": "disabled"}`
- Docstring (line 5-8): "ISO-06 (M2): ... are hard NO-OPS: they log a warning, report status='disabled', and never write."

**Verdict:** NOT IMPLEMENTED — Las capas L2, L3, L4 del modelo de memoria NUNCA se pueblan automáticamente. Solo existe lo que el agente escribe manualmente.

---

## FINDING-005: memory.db está vacía — 0 puntos almacenados

**Evidence (live probe):**
```sql
SELECT COUNT(*) FROM points; -> 0
SELECT agent_scope, COUNT(*) FROM points GROUP BY agent_scope; -> (empty)
```
- `data/memory.db` -> 16384 bytes (schema only, no rows)
- `data/L0-sensory/events.jsonl` -> 2 líneas (solo 2 eventos de prueba)

**Verdict:** EMPTY — No hay datos de memoria. Las herramientas existen pero nobody las ha usado en este entorno.

---

## FINDING-006: `_admin_read_by_layer` salta ISO-11 usando json_extract directo

**Evidence:**
- `src/L0_to_L4_consolidation/server/main.py:67-83` — ejecuta SQL directo con `json_extract(payload, '$.layer')`
- `src/shared/memory_db.py:51-53` — ISO-11 allowlist: solo `agent_scope`, `user_id` como keys engine-filterables
- `layer` NO está en `_ENGINE_FILTER_COLUMNS`

**Verdict:** ACCEPTED RISK — Puerta trasera de mantenimiento necesaria pero sin contrato de seguridad formal.

---

## FINDING-007: Doble storage sin sync automática (SQLite <-> vault)

**Evidence:**
- `src/shared/vault_manager/__init__.py:1-50` — Vault manager escribe markdown en filesystem
- `src/shared/conversation_db.py` — usa el MISMO memory.db pero con tablas separadas (`threads`, `messages`)
- No hay trigger ni proceso que sincronice `points` table <-> vault markdown files

**Verdict:** DIVERGENCE RISK — Dos sistemas de almacenamiento sin sincronización automática.

---

## FINDING-008: Query expansion no existe — classify_intent usa keyword matching plano

**Evidence:**
- `src/shared/llm/config.py:39-159` — `classify_intent` usa `any(kw in q for kw in [...])` sin expansión
- No hay diccionario de sinónimos, stemming, ni typos tolerance
- `src/shared/retrieval/__init__.py:140-145` — `_retrieve_L3_decisions` hace token matching simple

**Verdict:** LIMITED — Retrieval depende de query engineering perfecto por parte del agente.

---

## FINDING-009: FTS5 no se usa en la tabla `points` — solo en `threads` y `messages`

**Evidence:**
- `src/shared/memory_db.py:55-75` — Schema de `points` NO tiene FTS5 virtual table
- `src/shared/conversation_db.py:44-72` — `threads/messages/messages_fts` SÍ tiene FTS5
- `src/shared/retrieval/__init__.py:155-175` — `_retrieve_L3_decisions` lee archivos .md del filesystem y hace token matching manual

**Verdict:** MISSING FEATURE — FTS5 ausente en points table es la causa raíz de low R@5.

---

## FINDING-010: Evaluación actual refleja degradación, no capacidad real

**Evidence (live eval run):**
```
recall_at_5:    0.425   (documentado: 0.463 — peor que lo reportado)
mrr:            0.476   (documentado: 0.477 — casi igual)
zero_recall:    18/40   (45% de queries no encuentran nada)
code_lookup:    0.15    (catastrófico para búsqueda de código)
```
- `scripts/run_eval.py:29` — usa `hash_vector` porque `EMBEDDING_BACKEND=noop` forzado
- El eval fue diseñado para medir retrieval con hash-vector, NO con embeddings reales

**Verdict:** MEASUREMENT BIAS — Las métricas reportadas miden retrieval degradado, no retrieval pleno.
