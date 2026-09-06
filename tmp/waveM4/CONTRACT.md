# Contexto M4 (cwd=/Users/manu/.mcp-agent-memory)
src/shared/identity.py YA EXISTE (no lo modifiques): bind_identity() -> Identity
(.agent_id, .mode "bound"/"open", .assert_agent(x)->scope efectivo, .as_dict()),
IdentityError para boot fail-closed. REFERENCIA de wiring: src/L5_routing/server/main.py
(busca IDENTITY). shared.identity ya exporta todo; scope.py tiene normalize_scope.
PROHIBIDO: git, puertos/daemons, tocar ficheros fuera de tu propiedad, loguear tokens.
Testear: .venv/bin/python -m pytest <tu-test> -q. Ruff: sin violaciones NUEVAS.
