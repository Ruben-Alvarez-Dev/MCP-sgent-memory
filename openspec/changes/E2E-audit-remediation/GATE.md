# GATE — E2E-audit-remediation

**Fecha:** 2026-09-07 · **Veredicto: ✅ GO**

## Criterios de salida

| # | Criterio | Evidencia | Estado |
|---|----------|-----------|--------|
| 1 | Cero tools MCP rotas en vivo | Barrido 54/54: 51 OK + 3 validaciones correctas, 0 crashes | ✅ |
| 2 | L2 + L3_facts operativas sobre DB points-first | `test_protocol_smoke` 3/3 + CRUD 8/8 en deployment real | ✅ |
| 3 | Delete sincroniza FTS (sin retención) | puntos_fts MATCH=0 post-delete en test; scrub real verificado | ✅ |
| 4 | Sin regresión de retrieval | Eval R@5 0.5388 / MRR 0.4570 = pre-fix | ✅ |
| 5 | Suite + adversarial en verde | 407/0/6 + 151/151 (feat y main) | ✅ |
| 6 | Cero secretos en ficheros | Token solo en Keychain; mcp.json/.env sin token; scan de secretos negativo | ✅ |
| 7 | Strict desplegado y fail-closed | Boot strict OK; agente sin credencial → exit 1 con error claro | ✅ |
| 8 | G-ISOLATION re-firmado | Adversarial 151/151 + aislamiento cross-tenant re-probado en protocolo real (OWNER/INTRUDER) | ✅ |
| 9 | Instaladores coherentes con M9 | 0 refs embedding; sandbox test de config.sh OK | ✅ |

## Notas

- El push a origin queda **fuera de este gate** (403 permisos GitHub, pendiente
  del propietario del repo). main local: `4d5bb88` + commit de cierre.
- Los 3 no-OK del barrido son validaciones intencionales contra args dummy del
  sondeo (no bugs): whitelist de `event_type`, whitelist de `folder`, y el FS
  jail bloqueando un path fuera del vault.
