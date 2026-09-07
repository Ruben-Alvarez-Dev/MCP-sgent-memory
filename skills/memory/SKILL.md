---
name: memory
description: Manual operativo completo de la memoria persistente multi-agente (MCP-agent-memory, 54 tools). Usar SIEMPRE al iniciar trabajo sobre proyectos/decisiones/preferencias del usuario (recall primero), antes de afirmar algo sobre el pasado, al guardar decisiones/hechos/conclusiones de sesión, para conversaciones completas, razonamiento estructurado (plans/thinking), o cuando el usuario pida recordar/olvidar/buscar algo. Cubre las 7 capas, las 54 tools con firmas exactas, reglas de aislamiento, presupuestos de tokens y el sidecar REST para hooks.
---

# Memoria persistente — manual operativo (memory-zero)

Servidor MCP `MCP-agent-memory`: **54 tools, motor FTS5-only** (cero embeddings),
una sola SQLite (`data/memory.db`, WAL), identidad strict por agente
(`MEMORY_AGENT_ID` vía arnés + token en Keychain), aislamiento engine-level.

## Modelo mental (memoriza esto)

```
L0 raw events (jsonl append-only) → L1 working → L2 episodios (conversaciones)
→ L3 semántico (hechos/facts) → L4 narrativa (consolidado)
L5 = enrutador de contexto (request_context / reminders)
Lx = razonamiento deliberativo (thinking, plans, changesets)
Vault = notas Obsidian bilingües (L3_decisions_vault_*)
```

- Todo vive en `data/memory.db` (tablas `points` + `points_fts` + `threads`/`messages` + `entities`/`relations`/`synonyms`) y ficheros FS (`data/memory/L3_decisions/`, `data/Lx-deliberative/`).
- La recuperación es **FTS5 bm25** (léxica, determinista): busca por PALABRAS, no por significado. Usa términos distintivos que aparecieron literalmente.
- El pipeline L0→L4 consolida en background (heartbeats + dream). No lo fuerces salvo necesidad.

## Protocolo de uso (obligatorio)

### 1. RECALL PRIMERO — antes de contestar nada sobre el pasado del usuario

1. `L5_routing_request_context(query="<tema>", token_budget=2000, agent_id="<tu-agente>")` → ContextPack con lo relevante de todas las capas. **Es el punto de entrada normal.**
2. Si necesitas precisión quirúrgica, añade búsquedas dirigidas:
   - hechos → `L3_facts_search_memory(query="...", limit=5)`
   - decisiones → `L3_decisions_search_decisions(query="...", limit=10)`
   - conversaciones → `L2_conversations_search_conversations(query="...")`
3. Si devuelve vacío, di "no tengo registro de eso" — **nunca inventes recall**.

### 2. SAVE LO QUE IMPORTA — al cerrar una decisión/hecho/conclusión

| Contenido | Tool | Firma mínima |
|---|---|---|
| Decisión técnica/producto | `L3_decisions_save_decision` | `title, content, category="general"|"architecture"|"bugfix"`, devuelve `file_path` |
| Hecho, preferencia, discovery, bug fixed | `L3_facts_add_memory` | `content` (una frase autocontenida) |
| Conclusión de sesión / contexto a llevar | `L0_capture_memorize` | `content, mem_type="summary"|"fact"|"preference"|"bug_fix"|"code_snippet"|"config"|"episode"|"error_trace"|"decision"|"step"|"conversation", importance=0..1, tags` |
| Conversación completa | `L2_conversations_save_conversation` | `thread_id, messages_json='[{"role":"user","content":"..."}]'` (¡STRING JSON!) |
| Nota larga para Obsidian | `L3_decisions_vault_write` | `folder, filename, content, tags` |

Reglas de guardado: **una memoria = un hecho autocontenible** (el "tú" futuro no tendrá esta conversación). Prohibido guardar secretos/credenciales. Nada de cháchara efímera.

### 3. MANTENIMIENTO

- Borrar hecho: `L3_facts_delete_memory(memory_id, user_id)` · decisión: `L3_decisions_delete_decision(file_path)` (¡por `file_path`, no por id!)
- Consolidar tras sesión larga: `L0_to_L4_consolidation_consolidate` (o `dream` para ciclo profundo)
- Diagnóstico: `health_check` (una llamada, todo el estado)

## Catálogo por módulo (firmas exactas, * = requerido)

### L0_capture (captura inmediata)
- `L0_capture_memorize(content*, mem_type='fact', scope='session', scope_id='current', importance=0.5, tags)` — store inmediato → L1_WORKING. `scope` válidos: session|agent|personal|domain|project|global-core.
- `L0_capture_ingest_event(event_type*, source*, content*, actor_id='system', session_id)` — `event_type` ∈ {terminal, file, git, agent, ide, system, diff_proposed, diff_accepted, diff_rejected, diff_applied, diff_failed} (whitelist estricta).
- `L0_capture_heartbeat(agent_id*, session_id, turn_count=0, prefetch_queries=[])` · `L0_capture_status()`

### L0_to_L4_consolidation (pipeline)
- `..._consolidate(force=False)` · `..._dream()` (ciclo profundo L1→L4) · `..._dream_status(task_id*)`
- `..._heartbeat(agent_id='default', turn_count=1)` — auto-consolida si hay umbrales
- `..._approve_promotion(point_ids*, approved_by*)` — trunk humano (ISO-16): única vía a `merged`
- `..._force_promote(from_layer=1, count=10)` (solo testing) · `..._get_consolidated(scope)` · `..._get_semantic(scope)` · `..._status()`

### L5_routing (contexto y reminders)
- `L5_routing_request_context(query*, agent_id='shared', intent='answer', token_budget=8000, scopes, mode='standard')` — **la tool estrella**: ContextPack con presupuesto. `intent` guía el enrutado.
- `L5_routing_push_reminder(query*, reason='relevant_to_current_task', agent_id='default')` · `L5_routing_check_reminders(agent_id='default')` · `L5_routing_dismiss_reminder(reminder_id*, agent_id='shared')` · `L5_routing_detect_context_shift(current_query*, previous_query, agent_id)` · `L5_routing_status()`

### L2_conversations (episodios)
- `L2_conversations_save_conversation(thread_id*, messages_json*, summary, agent_scope='shared')` — `messages_json` es **string** con JSON dentro: `'[{"role":"user","content":"..."}]'`.
- `L2_conversations_get_conversation(thread_id*)` · `L2_conversations_search_conversations(query*, limit=5, min_score=0.3, agent_scope)` — `min_score` se ignora en el motor FTS5 (bm25 ≠ coseno); fíate del ranking. · `L2_conversations_list_threads(limit=20, agent_scope)` · `L2_conversations_status()`

### L3_facts (semántico)
- `L3_facts_add_memory(content*, user_id='default', metadata)` → devuelve `memory_id`
- `L3_facts_search_memory(query*, user_id='default', limit=5, min_score=0.3)` · `L3_facts_get_all_memories(user_id='default', limit=50)` · `L3_facts_delete_memory(memory_id*, user_id='default')` · `L3_facts_status()`

### L3_decisions (decisiones + vault + model packs)
- `L3_decisions_save_decision(title*, content, category='general', tags, scope='agent', body)` → **guarda el `file_path` devuelto**: es la clave para get/delete.
- `L3_decisions_search_decisions(query*, category, limit=10, agent_scope='shared')` · `L3_decisions_get_decision(file_path*)` · `L3_decisions_list_decisions(category, scope, limit=20)` · `L3_decisions_delete_decision(file_path*)`
- Vault Obsidian: `L3_decisions_vault_write(folder*, filename*, content*, tags)` — `folder` ∈ whitelist {inbox, decisions, knowledge, episodes, entities, people, notes, templates, Decisions, Knowledge, Episodes, Entities, People, Patterns, Learnings, Projects, Sandbox, Archive, Patrones, Aprendizajes, Proyectos, Archivos, log_global}. · `L3_decisions_vault_read_note(folder*, filename*)` · `L3_decisions_vault_list_notes(folder)` · `L3_decisions_vault_integrity_check()` · `L3_decisions_vault_process_inbox()`
- Model packs: `L3_decisions_list_model_packs()` · `L3_decisions_get_model_pack(name='default')` · `L3_decisions_set_model_pack(name*, content*)` · `L3_decisions_status()`

### Lx_reasoning (deliberación)
- `Lx_reasoning_sequential_thinking(problem*, context, max_steps=10, thinking_style='analytical', session_id)` · `Lx_reasoning_record_thought(session_id*, thought*, step=0, confidence=0.5)` · `Lx_reasoning_reflect(session_id*, focus='quality')`
- Plans: `Lx_reasoning_create_plan(title*, steps_json, context, session_id)` · `Lx_reasoning_update_plan_step(plan_id*, step_index*, status='completed', notes)`
- Changesets: `Lx_reasoning_propose_change_set(session_id*, title*, changes_json='[]')` · `Lx_reasoning_apply_sandbox(change_set_id*, dry_run=True)` — **deja dry_run=True salvo orden explícita**
- `Lx_reasoning_get_thinking_session(session_id*)` · `Lx_reasoning_list_thinking_sessions()` · `Lx_reasoning_status()`

### health
- `health_check()` — una llamada: estado de memory_db, contadores por capa, sidecar.

## Aislamiento (no negociable)

- **agent_scope**: tu scope es privado (coercido del arnés, ISO-13/15); lo que guardes va a `shared` salvo que indiques scope — `shared` lo ven todos los agentes, los scopes ajenos jamás. El filtro es **engine-level** (SQL), no post-filtro.
- **user_id** (L3 facts): tenant key de hechos. Usa tu `user_id` por defecto; buscar con user_id ajeno no devuelve su memoria.
- Nunca escribas en scope ajeno. Nunca promovas a `merged` sin `approve_promotion` humano.

## Optimización (presupuestos)

- **Recall**: 1º `request_context` con `token_budget` ajustado (2000 tarea típica, 8000 investigación). Solo añade búsquedas dirigidas si el pack no basta.
- **Save**: 1 llamada por hecho, conciso. No re-guardes lo ya guardado (busca antes).
- **No llames** a: `dream`/`consolidate` por rutina (background ya consolida), `force_promote` (testing), `*_status` en cada turno (solo diagnóstico).
- Search devuelve `limit` resultados rankeados por bm25 — con `limit=5` basta casi siempre; sube a 10 en investigaciones.

## Sidecar REST (hooks y scripts, sin LLM) — `127.0.0.1:8890/api/*`

Lo aloja la instancia designada (opencode) — single-bind. Si no responde, fail-silent.

```
GET  /api/health
POST /api/ingest-event       {event_type, source, content, actor_id?, session_id?}
POST /api/heartbeat          {agent_id, turn_count?}
POST /api/heartbeat-dream    {...}
POST /api/save-conversation  {thread_id, messages_json, summary?, agent_scope?}
POST /api/consolidate        {}
POST /api/request-context    {query, agent_id?, token_budget?}
POST /api/verify-memories    {...}
```
Ejemplo hook: `curl -s --max-time 2 -X POST http://127.0.0.1:8890/api/consolidate -d '{}' -H 'Content-Type: application/json'`

## Gotchas verificados (auditoría E2E 2026-09-07)

- `min_score` NO filtra en FTS5 (parity de contrato) — no intentes umbralizar.
- Decisions se direccionan por `file_path`; `decision_id` no existe como clave.
- `messages_json` y `steps_json` y `changes_json` son **strings** con JSON dentro.
- `event_type` y `folder` tienen whitelist — un valor inválido devuelve error con la lista permitida.
- Delete de punto purga también el índice FTS (sin retención fantasma).
- Boot fail-closed: credenciales parciales (id sin token) matan el arranque aunque el modo sea open — ISO-14.
