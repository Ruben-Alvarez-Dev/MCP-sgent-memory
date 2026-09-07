# Proposal: M4-identidad — harness-asserted identity, registro de agentes, boot fail-closed

## Intent
Cerrar ISO-01 (identidad auto-afirmada): la identidad del agente deja de ser
un string del caller y pasa a ser **ligada al proceso del servidor** por el
harness en el arranque (env `MEMORY_AGENT_ID` + `MEMORY_AGENT_TOKEN`,
verificados contra un registro de agentes). Un servidor ligado solo puede
actuar en su propio scope o en `shared` — el spoofing de `agent_id` deja de
ser posible por diseño, no por convención.

## Modelo (M4-lite, decisión registrada)
- **Registro**: `data/agents.json` — agent_id → sha256(token); el token en
  claro se muestra UNA vez en el alta (`scripts/register_agent.py`). Fichero
  chmod 600. Verificación constant-time (`hmac.compare_digest`).
- **Modos**: `open` (default hoy: sin credenciales, WARN sonoro en boot,
  status lo reporta) y `strict` (boot falla sin credenciales válidas —
  fail-closed boot del plan M1 original). Migración: una línea de env en el
  bloque `env` de `config/mcp.json` por agente.
- **Política de coerción**: en modo bound, `agent_id="default"` (default MCP
  actual) coersa al scope propio; `shared` permitido; **cualquier otro scope
  ajeno → ScopeError**. En open, solo validación de forma (comportamiento M3).
- `user_id` (L3_facts) queda como particionado de aplicación, NO identidad
  (documentado; la identidad de tenant es el scope de agente).

## Capabilities
- Modified: `isolation` — ISO-01 deja de ser self-asserted (ISO-13/ISO-14 added).
- Sin cambios en storage/retrieval: ninguna consulta cambia de forma; la
  identidad es un gate previo a las rutas ya aisladas.

## Tenants/scopes e impacto de aislamiento
Estrictamente reductor: en bound mode se elimina la única vía de
ensanchamiento restante (spoof de agent_id). Open mode = comportamiento M3
explícito y visible en status.

## Rollback plan
Revert del commit; `MEMORY_IDENTITY_MODE` no está seteado en producción →
comportamiento idéntico a M3. El registro agents.json es aditivo (su presencia
no cambia nada sin strict).

## Fuera de alcance (con dueño)
- mTLS/firmas por request, identidad HTTP del sidecar → M5 (sidecar hereda
  bind por env, suficiente hoy).
- Rotación de tokens / múltiples tokens por agente → M5.
- Bind de `user_id` a identidad → M5 (requiere decidir modelo de usuarios).
