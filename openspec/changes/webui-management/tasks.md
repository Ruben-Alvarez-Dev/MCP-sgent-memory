# Tasks — webui-management

## F1 — Núcleo (dashboard + memorias)
- [ ] 1.1 Esqueleto `src/webui/` (Starlette app, auth token opcional, readonly mode, arranque `scripts/webui.sh`) — criterio: `--help` y health responde en :8892, sin deps nuevas en pyproject
- [ ] 1.2 `GET /api/stats` (contadores, health, alertas umbrales) — criterio: coincide con `health_check` + metrics.py
- [ ] 1.3 `GET /api/memories` búsqueda FTS5 + filtros scope/user_id/layer + paginación server-side — criterio: 1k memorias sandbox, respuesta < 50ms
- [ ] 1.4 `GET/PATCH/DELETE /api/memories/{id}` con confirm=hash — criterio: delete purga points_fts (0 huérfanos post-delete)
- [ ] 1.5 Front: dashboard + explorador (vanilla JS, dark) — criterio: flujo manual search→abrir→editar→borrar sin consola
- [ ] 1.6 Test contract de la API (client de Starlette) — criterio: ≥10 tests, incluido readonly rechaza escrituras

## F2 — Decisiones y conversaciones
- [ ] 2.1 Decisions CRUD por file_path (scope filter propio+shared) — criterio: lista coincide con `list_decisions`
- [ ] 2.2 Vault write/read con whitelist de folders (sanitize) — criterio: folder inválido → 400 con lista
- [ ] 2.3 Conversaciones: list/search/get/delete — criterio: thread creado vía MCP visible en UI
- [ ] 2.4 Render markdown sanitizado — criterio: `<script>` en payload no ejecuta

## F3 — Lx, reminders, trunk, agentes
- [ ] 3.1 Sesiones Lx (thoughts + plans read-only) — criterio: sesión creada vía MCP visible
- [ ] 3.2 Reminders list/dismiss — criterio: dismiss equivale a la tool
- [ ] 3.3 Trunk: cola pendiente + approve con provenance — criterio: sin approved_by → 400; aprobado llega a merged
- [ ] 3.4 Agentes: list/rotate/revoke — criterio: rotate muestra token UNA vez; revocado → boot strict falla
- [ ] 3.5 Test contract por endpoint + adversarial (paths, scopes)

## F4 — Métricas, auditoría, hardening
- [ ] 4.1 `GET /api/metrics/snapshot|history` reutilizando metrics.py — criterio: mismo output que CLI
- [ ] 4.2 Auditoría L0 read-only paginada — criterio: evento ingestado vía REST visible
- [ ] 4.3 Hardening: readonly total, bind remoto exige token, rate-limit básico — criterio: suite adversarial UI
- [ ] 4.4 README (sección Web UI) + GATE con evidencia

## Fuera de alcance
- Auth multi-usuario/roles (una persona admin; token único compartido)
- Edición del vault bilingüe ES/EN automática (el vault se edita en Obsidian)
- Gráficas JS pesadas (sparklines canvas propios)
