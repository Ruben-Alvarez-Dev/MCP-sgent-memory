# Design: M4-identidad

## Módulo nuevo: `src/shared/identity.py` (stdlib: json, hashlib, hmac, secrets, os, stat)

```python
class IdentityError(RuntimeError)            # boot fail-closed (strict)
IDENTITY_MODE_ENV="MEMORY_IDENTITY_MODE"     # "open" (default) | "strict"
AGENT_ID_ENV="MEMORY_AGENT_ID"; AGENT_TOKEN_ENV="MEMORY_AGENT_TOKEN"

class AgentRegistry:
    def __init__(path=None)                  # default: <DATA_DIR>/agents.json
    def register(agent_id, token=None) -> str   # token claro UNA vez; guarda sha256
    def verify(agent_id, token) -> bool         # hmac.compare_digest, constant-time
    def list_agents() -> dict
    # escritura atómica (tmp+rename), chmod 600, agent_id via normalize_scope
    # A21: ids de agente RESERVADOS no registrables (global/merged/…)

@dataclass
class Identity:
    agent_id: str          # scope canónico propio
    mode: str              # "bound" | "open"
    def assert_agent(requested: str) -> str:
        """Devuelve el scope efectivo para la llamada.
        bound:  normalize(requested); "default"→coersa a propio (DEBUG log);
                shared ok; ajeno → ScopeError (ISO-13)
        open:   normalize(requested) (forma, sin binding)"""
    def as_dict() -> dict   # {"agent_id", "mode"} para status

def bind_identity(env=None, registry=None) -> Identity:
    """Ligadura en arranque. strict: env requerido + verify; fallo → IdentityError.
    open: si env completo y válido → bound silencioso; si no → open + WARN."""
```

## Wiring (patrón de referencia en L5, replicado por K en el resto)

En cada servidor, tras `config = Config.from_env()`:
```python
from shared.identity import bind_identity
IDENTITY = bind_identity()          # puede lanzar IdentityError en strict (fail-closed boot)
```
En cada tool con `agent_id`/`agent_scope`, PRIMERA línea:
```python
agent_id = IDENTITY.assert_agent(agent_id)   # devuelve scope efectivo
```
(normalize_scope posterior queda — assert ya devuelve canónico).
`health_check` del unified añade `checks["identity"] = IDENTITY.as_dict()`
(dict tool, sin cambio de esquema pydantic).

Servers a cablear: L5 (6 tools), L3_facts (scope de agente: add/search/
get_all/delete NO exponen agent_id — su eje es user_id; M4 añade assert en
nada… **decisión**: L3_facts no cambia salvo bind+status, documentado),
L0_capture (bind+status), L2_conversations (save/search/list con agent_scope
→ assert), unified (bind+health_check+pass-through ya cubierto).

## CLI: `scripts/register_agent.py`
`register <agent_id>` → imprime token una vez + snippet env para mcp.json;
`verify <agent_id> <token>`; `list`. Exit codes explícitos.

## Failure modes + adversarial (tests/adversarial/test__M4__identity.py)
- A17 spoof: bound director-1, tool con agent_id="engineer-1" → ScopeError,
  cero I/O; "default" → coerción a director-1; "shared" → ok
- A18 strict fail-closed boot: sin env → IdentityError; token malo → IdentityError;
  nada escucha en el proceso (el import muere antes de registrar tools)
- A19 replay cruzado: token válido de director-1 presentado como engineer-1 → verify False
- A20 open mode: sigue validando forma (traversal → ScopeError) y WARN documentado
- A21 registry: chmod 600 verificable; register→verify roundtrip; agent_id
  reservado rechazado; JSON corrupto → registry vacío + WARN (no crash de boot en open)
- Tokens: secrets.token_urlsafe(32); nunca persistidos en claro; jamás logueados

## Cobertura
tests/core/test_identity.py (unit, ~14) + tests/adversarial/test__M4__identity.py
(A17–A21, markers isolation). REQs: ISO-01 (MODIFIED), ISO-13, ISO-14 (ADDED).
