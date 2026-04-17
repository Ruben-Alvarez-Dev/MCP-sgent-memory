# Manual de Operaciones — MCP Memory Server V3

Este documento es el **punto de referencia técnico definitivo** para el mantenimiento y diagnóstico del sistema evolucionado a V3. Si algo falla, la solución está aquí.

## 1. Arquitectura de la V3
El sistema se compone de dos bloques desacoplados:
- **1mcp-agent (Gateway)**: Servidor en TypeScript/Node.js que actúa como puerta de enlace unificada en el puerto `3050`.
- **MCP-servers (Engine)**: Suite de servidores en Python que gestionan la memoria (Qdrant), los embeddings (llama.cpp) y el Vault de Obsidian.

## 2. Protocolo de Instalación Segura
El script `MCP-servers/install.sh` ha sido blindado para evitar pérdida de datos.
- **Ubicación por defecto**: `~/MCP-servers/MCP-memory-server`.
- **Backups**: El instalador ahora crea automáticamente copias de seguridad de `tools.db` con timestamp antes de sobreescribir.
- **Confirmación**: Se requiere confirmación manual (`y/N`) si se detecta una instalación previa para evitar borrados accidentales de colecciones en Qdrant.

## 3. Resolución del Error "Binario Roto" (macOS)
Si un agente reporta que un binario (Bun, Qdrant, llama-server) está "roto" o no arranca, suele ser por la **Cuarentena de Apple** o falta de permisos.

### Solución:
Ejecutar los siguientes comandos en la terminal:
```bash
# Quitar el atributo de sospecha de macOS
xattr -d com.apple.quarantine /Users/ruben/.bun/bin/bun
xattr -d com.apple.quarantine ~/MCP-servers/MCP-memory-server/engine/bin/llama-server
xattr -d com.apple.quarantine ~/MCP-servers/MCP-memory-server/bin/qdrant

# Asegurar permisos de ejecución
chmod +x /Users/ruben/.bun/bin/bun
chmod +x ~/MCP-servers/MCP-memory-server/engine/bin/llama-server
chmod +x ~/MCP-servers/MCP-memory-server/bin/qdrant
```

## 4. Delegación de Agentes (OpenCode 1.4.6)
**IMPORTANTE**: Existe una regresión conocida en la versión 1.4.6 de OpenCode que rompe la herramienta `delegate`.
- **Síntoma**: La sesión hija devuelve 0 tokens y termina inmediatamente con estado "other". El agente lo interpreta como "binario roto".
- **Acción Obligatoria**: Usar la herramienta `task` en lugar de `delegate`. `task` es síncrona y funciona correctamente en esta versión.
- **Plugin**: El plugin en `~/.config/opencode/plugins/background-agents.ts` ha sido parcheado con advertencias descriptivas.

## 5. Gestión de la Memoria (Qdrant + Obsidian)
- **Persistencia de Notas**: El Vault de Obsidian vive en `~/MCP-servers/MCP-memory-server/vault/`. El instalador NO borra tus notas.
- **Re-indexado**: Si Qdrant se resetea, se debe forzar un re-indexado del Vault:
  ```bash
  source ~/MCP-servers/MCP-memory-server/.venv/bin/activate
  python3 -m src.search.service --reindex-vault
  ```
- **Base de Datos de Herramientas**: Ubicada en `~/MCP-servers/MCP-memory-server/tests/e2e/tools.db`. Contiene más de 100 herramientas configuradas.

## 6. Control de Servicios (Launchd)
Los servicios arrancan solos al iniciar sesión. Para gestionarlos manualmente:
```bash
# Reiniciar Qdrant
launchctl stop com.memory-server.qdrant && launchctl start com.memory-server.qdrant

# Reiniciar Gateway
launchctl stop com.memory-server.gateway && launchctl start com.memory-server.gateway
```

---
*Manual redactado tras la auditoría de integridad del 15 de abril de 2026.*
