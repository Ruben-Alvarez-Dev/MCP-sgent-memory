# Handoff: Auditoría E2E + Remediación completa (P0 + P1)

**Fecha:** 2026-09-07
**Rama:** `main` @ `4d5bb88` + commit de cierre
**Estado:** ✅ Remediación completa, GATE GO (openspec/changes/E2E-audit-remediation)

---

## Resumen Ejecutivo

La auditoría E2E (spawn real del servidor unificado por stdio + JSON-RPC contra
DB production-shaped) encontró **4 tools MCP rotas en producción con la suite
403/0 en verde**. Causa sistémica: los tests mockean el store y usan DBs
vírgenes — nada ejercitaba el protocolo real ni DBs pre-existentes. Remediado,
certificado y blindado con una red de regresión de protocolo.

## Lo que se rompió y por qué (lección central)

| Bug | Causa raíz |
|-----|-----------|
| `L3_facts_add_memory` / `L2_search_conversations` muertas | `vector = await None` — placeholders de la migración M6/M7 nunca eliminados |
| L2 conversaciones muerta en producción | `_ensure_db` solo inicializaba DBs vírgenes; la DB real nace points-first (MemoryDB crea `points` primero) → `threads` jamás se creaba |
| Contenido borrado persistía en `points_fts` | `_delete_one` no purgaba el índice (sin triggers) |
| Tokens alfanuméricos sin match (`E2E…`, `OAuth2`) | `_build_fts5_query` infiel al tokenizador unicode61 |

**Regla para el próximo dev:** cualquier handler de tool debe probarse por
protocolo (spawn + JSON-RPC), no solo por import directo. `await None` es un
anti-pattern prohibido — si una migración deja un placeholder, que falle el
test, no producción.

## Entregables

### P0 — fixes de código (`69196e7`)
- 2 `await None` eliminados; `_ensure_db` always-init idempotente; FTS purge en
  `_delete_one`; `_build_fts5_query` unicode61-faithful.
- `tests/e2e/test_protocol_smoke.py` — spawn subprocess + JSON-RPC + sandbox
  points-first: add→search→aislamiento→delete→purga-FTS + roundtrip L2.

### P1 — deployment (`4d5bb88` + cierre)
- Env muertos purgados: generador, `.env`, `.env.example`, **instaladores
  completos** (bootstrap sin fase embedding; `services.sh` eliminado;
  `verify/config/detect/update/app-install` purgados).
- **Identidad strict vía Keychain** (cero secretos en ficheros):
  `scripts/launch-unified.sh` + `generate-mcp-config.sh` emite launcher cuando
  `MEMORY_AGENT_ID` está en `.env`. Agente `pi-agent` registrado; token solo en
  Keychain (`memory-zero/pi-agent`).
- README actualizado (config, MCP, identidad); residuos `engine/`, `models/`,
  marcadores de auditoría en `data/` eliminados.

### Certificación final
- Suite: **407 passed / 0 failed / 6 skipped** · Adversarial: **151/151**
- Eval: **R@5 0.5388 / MRR 0.4570** — cero regresión vs pre-fix
- **Barrido 54/54 tools en vivo**: 0 crashes (3 no-OK = validaciones correctas:
  whitelists y FS jail)
- Strict en vivo: boot + tool calls OK; fail-closed para credencial ausente
- CRUD en deployment real: **8/8**

## Estado del deployment

- `~/.pi/mcp.json` → launcher strict (`pi-agent`). El servidor arrancará en
  strict en el próximo reinicio del cliente MCP.
- Rotación de credenciales: `scripts/register_agent.py register pi-agent` +
  `security add-generic-password -s "memory-zero/pi-agent" -a "$USER" -w '<token>' -U`

## Pendiente (bloqueado fuera de sesión)

- **`git push origin main`** → 403: `manu-alvarez` no tiene permiso de escritura
  en `Ruben-Alvarez-Dev/MCP-agent-memory`. main local va N commits por delante;
  resolver credenciales/colaborador y push.

## Links

- GATE: `openspec/changes/E2E-audit-remediation/GATE.md` (GO)
- Evidencia: `openspec/changes/E2E-audit-remediation/evidence/findings.md`
- Scripts de auditoría (reutilizables): `tmp/e2e_sweep54.py`, `tmp/e2e_crud.py`
