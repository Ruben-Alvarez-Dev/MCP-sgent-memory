# Grupo G — API, Config & Compatibilidad

## Especificaciones

### SPEC-G1: Versionado del server y tools

**ID auditoría**: API-H1
**Severidad**: HIGH
**Módulo**: root

**Problema**: 0 versionado. Cambios en tool signatures rompen consumers sin aviso.

**Spec de fix**:

1. Añadir `__version__` al server:
```python
# src/__init__.py
__version__ = "0.9.0"
```

2. Añadir `schema_version` a payloads (ya cubierto en SPEC-B3)

3. Tool de versionado:
```python
@server.tool("server_version")
async def server_version() -> dict:
    return {"version": __version__, "tools": len(server._tool_manager.list_tools())}
```

4. Changelog en `CHANGELOG.md` (semaántico)

**Criterio de aceptación**:
- [ ] `server_version()` retorna versión actual
- [ ] Tool signatures documentadas con @since tags
- [ ] BREAKING changes documentados en CHANGELOG

---

### SPEC-G2: Config unificada (.env como single source of truth)

**ID auditoría**: API-H2 + config drift
**Severidad**: MEDIUM
**Archivos**: `config/.env`, `config/mcp.json`, LaunchAgent plists

**Problema**: Configuración duplicada entre .env y mcp.json. Parcialmente desincronizada.

**Spec de fix**:

1. `.env` es el single source of truth
2. `mcp.json` se genera desde .env (no se edita manualmente)
3. Script de generación:
```bash
# scripts/generate-mcp-config.sh
source config/.env
cat > config/mcp.json <<EOF
{
  "mcpServers": {
    "agent-memory": {
      "command": "python",
      "args": ["-m", "unified.server.main"],
      "cwd": "${INSTALL_DIR}",
      "env": {
        "QDRANT_URL": "${QDRANT_URL}",
        "EMBEDDING_BACKEND": "${EMBEDDING_BACKEND}",
        ...
      }
    }
  }
}
EOF
```

4. Añadir `CONFIG_VERSION=1` a .env para detectar drift

**Criterio de aceptación**:
- [ ] mcp.json generado automáticamente desde .env
- [ ] 0 config duplicada manual
- [ ] .env tiene CONFIG_VERSION para migraciones

---

### SPEC-G3: Config.validate() completo

**Severidad**: MEDIUM
**Módulo**: `src/shared/config.py`

**Problema**: validate() solo verifica 4 campos de 25+.

**Spec de fix**: Validar todos los campos:

```python
def validate(self) -> list[str]:
    errors = []
    
    # URLs válidas
    if not self.qdrant_url.startswith(("http://", "https://")):
        errors.append(f"QDRANT_URL must be http(s) URL, got {self.qdrant_url}")
    
    # Backends válidos
    valid_embed_backends = {"llama_cpp", "llama_server", "http", "noop"}
    if self.embedding_backend not in valid_embed_backends:
        errors.append(f"EMBEDDING_BACKEND must be one of {valid_embed_backends}")
    
    valid_llm_backends = {"ollama", "llama_cpp", "lmstudio"}
    if self.llm_backend not in valid_llm_backends:
        errors.append(f"LLM_BACKEND must be one of {valid_llm_backends}")
    
    # Rangos
    if self.embedding_dim not in {256, 384, 512, 768, 1024, 1536}:
        errors.append(f"EMBEDDING_DIM unusual value: {self.embedding_dim}")
    
    if self.vk_min_score < 0 or self.vk_min_score > 1:
        errors.append(f"VK_MIN_SCORE must be 0-1")
    
    # Paths existentes
    if self.embedding_backend == "llama_server" and not Path(self.model_path).exists():
        errors.append(f"MODEL_PATH not found: {self.model_path}")
    
    return errors
```

**Criterio de aceptación**:
- [ ] validate() verifica todos los campos de Config
- [ ] Error si backend no reconocido
- [ ] Error si model_path no existe y se necesita
- [ ] Warning si dim no estándar (no error, solo warn)
