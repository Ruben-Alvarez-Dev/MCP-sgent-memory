# Design — webui-management

## 1. Arquitectura

```
┌────────────── Navegador (humano) ──────────────┐
│  SPA vanilla JS (hash routing, sin build)      │
│  static/ index.html app.js style.css           │
└───────────────┬────────────────────────────────┘
                │ fetch /api/* (JSON, same-origin)
┌───────────────▼────────────────────────────────┐
│  src/webui/  (Starlette + uvicorn, :8892)      │
│  app.py        — Starlette app + rutas         │
│  auth.py       — token opcional + readonly     │
│  views/*.py    — handlers por módulo           │
│  (reutiliza shared/: MemoryDB,                │
│   conversation_db, sanitize, usage, identity)  │
└───────────────┬────────────────────────────────┘
                │ lectura/escritura directa
        data/memory.db · vault FS · agents.json · usage.jsonl
```

**Decisiones y porqués:**
- **Servicio aparte en :8892** (`MEMORY_UI_PORT` configurable), NO en :8890:
  el sidecar de hooks es single-bind y pertenece a una instancia de agente;
  la UI es un daemon humano independiente (`scripts/webui.sh start|stop`).
- **Starlette ya está en el venv** (1.6.0) → cero dependencias nuevas. uvicorn
  también. Sin jinja2: front estático + API JSON.
- **Reutiliza `shared/`**: toda operación pasa por MemoryDB / conversation_db /
  sanitize (mismas validaciones que las tools; delete con purga FTS heredada).
- SQLite síncrono ejecutado en threadpool de Starlette (el bloqueo es µs-ms;
  mismo patrón que MemoryDB con `asyncio.to_thread`).

## 2. Seguridad

| Control | Decisión |
|---|---|
| Bind | `127.0.0.1` por defecto; si `MEMORY_UI_HOST≠127.0.0.1` → warning + token OBLIGATORIO |
| Auth | `X-Memory-Token` vs `MEMORY_HTTP_TOKEN` (mismo mecanismo ISO-17 del sidecar); sin token = solo localhost |
| Escritura | `MEMORY_UI_READONLY=1` deshabilita POST/PATCH/DELETE de contenido |
| Destructivo | DELETE requiere `?confirm=<hash-del-id>`; el borrado deja rastro en L0 (auditoría append-only) |
| Secrets | La UI NUNCA muestra tokens (solo hash de agentes.json) ni payloads marcados sensibles |
| CSRF | Same-origin + token header; sin cookies de sesión (stateless) |

## 3. Pantallas y API

| # | Pantalla | API | Notas |
|---|----------|-----|-------|
| 1 | **Dashboard** | `GET /api/stats` | health, contadores por capa, adopción (llamadas/día, top tools, p50/p95 de usage.jsonl), growth sparkline (history.jsonl), alertas de umbrales (mismos que metrics.py) |
| 2 | **Memorias** (points) | `GET /api/memories?q&scope&user_id&layer&collection&page` · `GET /api/memories/{id}` · `PATCH /api/memories/{id}` (payload) · `DELETE /api/memories/{id}?confirm=` | búsqueda FTS5 MATCH parametrizada + filtros; paginación server-side LIMIT/OFFSET; detalle = payload JSON formateado; delete reutiliza `_delete_one` (purga FTS incluida); sección "huérfanos FTS" con purga |
| 3 | **Decisiones** (vault FS) | `GET /api/decisions?category&scope&q` · `GET/PUT/DELETE /api/decisions/{path}` · `POST /api/decisions/vault` (nota Obsidian) | lee `data/memory/L3_decisions/_scopes/`; render markdown en cliente; integrity check accesible |
| 4 | **Conversaciones** | `GET /api/conversations?q&scope&page` · `GET /api/conversations/{thread_id}` · `DELETE ...` | threads + mensajes, FTS de conversation_db |
| 5 | **Sesiones Lx** | `GET /api/lx/sessions` · `GET /api/lx/sessions/{id}` (thoughts + plans) | lectura del FS de sesiones; plans con estado de pasos |
| 6 | **Reminders** | `GET /api/reminders?agent` · `DELETE /api/reminders/{id}` | de L5-selective |
| 7 | **Trunk** (aprobaciones) | `GET /api/trunk/pending` · `POST /api/trunk/approve {point_ids, approved_by}` | cola humana ISO-16; exige `approved_by` no vacío (provenance) |
| 8 | **Agentes** | `GET /api/agents` · `POST /api/agents/{id}/rotate` · `DELETE /api/agents/{id}` | registry agents.json; rotate imprime token UNA vez en la respuesta (nunca se re-muestra); revoke = borrar entrada |
| 9 | **Métricas** | `GET /api/metrics/snapshot` · `GET /api/metrics/history` | reutiliza la lógica de scripts/metrics.py (extraída a función) |
| 10 | **Auditoría L0** | `GET /api/l0/events?from&to&type` (read-only, paginado) | timeline append-only |

Front: una sola página, hash-routing (#/memories, #/decisions, …), tabla
virtualizada simple (paginación server-side), visor JSON con plegado, dark
theme. Sin frameworks: vanilla JS ~600 líneas estimadas.

## 4. Modos de fallo y casos adversarios

- **Puerto 8892 ocupado** → error claro y exit (no retry silencioso).
- **DB corrupta/locked** → las lecturas devuelven 503 con detalle; la UI no
  escribe salvo operaciones explícitas del usuario.
- **Payload JSON malicioso** → siempre se muestra como texto escapado (sin
  eval/innerHTML crudo); render markdown solo en decisiones con sanitización.
- **DELETE en cascada accidental** → confirmación por hash + rastro L0.
- **Fuga por bind remoto** → token obligatorio + warning persistente en UI.
- **usage.jsonl gigante** → lectura por cola (últimas N líneas) con offset;
  agregación incremental futura si hace falta.
- **Race con agentes** → escrituras vía `MemoryDB._write_lock` (ya existente);
  lecturas WAL no bloquean.

## 5. Fases

| Fase | Contenido | Criterio de aceptación |
|---|---|---|
| F1 | esqueleto app + auth + Dashboard + Memorias (search/ver/editar/delete) | smoke: arranque, búsqueda FTS real, delete con purga FTS verificada |
| F2 | Decisiones + Conversaciones | CRUD completo con scope filter correcto |
| F3 | Lx + Reminders + Trunk + Agentes | rotate token funciona una sola vez; approve exige approved_by |
| F4 | Métricas + Auditoría L0 + hardening (readonly, bind remoto) | snapshot UI == metrics.py CLI byte a byte |
