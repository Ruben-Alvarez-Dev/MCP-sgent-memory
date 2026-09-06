# Auditoría post-programa y pulido — 2026-09-06

Alcance: revisión independiente completa tras cerrar M0–M5 (3 auditores
subagente de ojos frescos + verificación dinámica del orquestador).
Método: A (seguridad adversarial, glm-5.2) · B (consistencia documental,
glm-5.3-flash) · C (operaciones/deployment, glm-5.2) · orquestador
(flakiness ×3, boot real, CLI smoke, barridos grep).

## Veredicto

El aislamiento **engine-level es sólido** (filtros SQL, fail-closed, trunk
gate por construcción) pero la auditoría encontró **1 CRITICAL real** y
**5 HIGH** en la capa de herramientas — todos remediados en esta misma sesión
(commit "audit/polish"). El instalador arrastraba ~4.5GB de software muerto.
La documentación presentaba.tools y rutas inexistentes. Todo lo hallado queda
registrado abajo con su estado.

## Remediado (esta sesión)

| ID | Hallazgo | Severidad | Estado |
|---|---|---|---|
| C1 | `approve_promotion` + `db.get` sin filtro: exfiltración cross-tenant al trunk con `approved_by` decorativo | 🔴 CRITICAL | ✅ `get()` fail-closed con filtro obligatorio; approve solo ve own+shared |
| H1 | `update_payload` mintía rows `merged` sin gate ISO-16 (PoC del auditor) | 🟠 HIGH | ✅ gate también en patches; merged via update → ScopeError |
| H2 | L0 `heartbeat`: path traversal vía `agent_id` crudo | 🟠 HIGH | ✅ `assert_agent` + `assert_contained` |
| H3 | L3_decisions sin identidad + contención por prefijo `startswith` (bug clásico) | 🟠 HIGH | ✅ bind + `assert_agent` + `assert_contained` (resolve-based) |
| H4 | L3_facts `user_id` 100% caller-controlled | 🟠 HIGH | ⚠️ Parcial: bind presente; binding user_id→identidad requiere modelo de usuarios (diferido con dueño, ver abajo) |
| H5 | L2 `get_conversation` sin predicate de scope (oráculo de existencia) | 🟠 HIGH | ✅ gate + not_found sin leak |
| M1 | `"MERGED"`/`" merged"` esquivaban el trunk guard (exact-match) | 🟡 | ✅ comparación sobre valor strip+lower |
| M3 | Lx `sanitize_thread_id` permitía paths absolutos | 🟡 | ✅ rechazo de `/` y `..` en los 7 puntos de path |
| M4e | Engine `get`/`delete` sin filtro obligatorio habilitaba C1 | 🟡 | ✅ get fail-closed; delete documentado admin-only con filtro recomendado |
| — | Instalador: bootstrap descargaba Qdrant + qwen 4.4GB por defecto | 🔴 (ops) | ✅ Steps 3/5 eliminados; grep residuo = 0 |
| — | verify.sh exigía binarios llama aunque el backend fuera http/noop | 🟡 (ops) | ✅ condicionado a EMBEDDING_BACKEND |
| — | `etc/mcp.json` con rutas de máquina ajena (`/Users/ruben`) | 🟡 (ops) | ✅ eliminado del repo |
| — | `.bootstrap-status`/`install-constraints.txt` tracked (estado runtime) | 🟡 (ops) | ✅ untracked + gitignore |
| — | `tmp/wave*/**` (16 ficheros de sesión) trackeados por `git add -A` | 🟡 | ✅ untracked + `tmp/` en .gitignore |
| — | `bench/*` ejercitaba gateway muerto + colecciones externas | 🟢 | ✅ borrados |
| — | `AUTOMEM_*`/`MEM0_*`/`ENGRAM_PATH` residuos del purge | 🟢 | ✅ renombrados con fallback / eliminados |
| — | `pyproject` descripción "Qdrant client" + deps sin consumidor (httpx, pydantic-settings) + packaging ilusorio | 🟡 | ✅ actualizado + nota honesta venv-in-repo |
| — | README: tabla de tools con nombres inventados (23 de 54 mal), `etc/` vs `config/`, plugin inexistente, sin docs de run_eval | 🟡 | ✅ tabla regenerada desde el registro real (54/54), rutas corregidas, sección Evaluation añadida |
| — | Specs BASE sin marcar como superadas (un lector nuevo las leería como vigentes) | 🟡 | ✅ banners SUPERSEDED + puntero a cadena de deltas |
| — | GATE_M4 afirmaba "7 servidores con bind"; la realidad eran 5 | 🔴 (proceso) | ✅ remediado: 8/8 bind hoy (L0_to_L4 y Lx completados en M5/auditoría); errata documentada aquí |
| — | `generate-mcp-config.sh` generaba config roto (SERVER_DIR≠MEMORY_SERVER_DIR) y pisaba el mcp.json vivo | 🔴 (ops) | ✅ template regenerado alineado; `--install` explícito para pisar |
| — | config/.env live con 8 claves muertas | 🟡 | ✅ podadas (solo claves vivas) |

## Verificación post-remediación

- `pytest tests/ -q` → **321 passed / 0 failed / 6 skipped** (×3 sin flakiness)
- `pytest tests/adversarial -q` → 87 → **95 passed** (+8 hardening, +2 no-qdrant)
- Boot real unified: 7/7 módulos, 54 tools, identity open-WARN una vez por bind
- Strict boot sin credenciales: muere con IdentityError antes de registrar tools
- Ruff: ficheros nuevos limpios; deuda preexistente intacta (documentada)

## Hallazgos aceptados / diferidos (con dueño)

- **H4-user_id**: el binding completo exige decidir el modelo de usuarios
  (¿user_id = agente? ¿multi-usuario humano?) → decisión de owner, no parche.
- **Modo open por defecto**: documentado M4-lite; migración a strict es 1 línea
  de env por agente. En open, los gaps inter-agente son el trade-off declarado.
- **Eval residual**: code_lookup R@5 0.30 (gap es→en), 17/40 zero-recall →
  backlog de retrieval quality para misión futura.
- **Specs BASE**: banners añadidos; el plegado canónico de deltas a specs/
  queda como tarea de mantenimiento cuando el programa reabra.

## Lección de proceso (registrada)

El fallo más grave (C1) no estaba en el código nuevo sino en la **composición**:
dos piezas correctas por separado (get por id + trunk con aprobación) creaban
juntas un canal de exfiltración. Los gates por misión verificaron invariantes
locales; la auditoría de composición entre misiones era la pieza que faltaba —
se añade como práctica permanente: **re-auditoría de composición tras cada
cierre de programa**.
