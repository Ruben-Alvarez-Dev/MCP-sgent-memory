# Checklist de Comprobación — MCP Memory Server V3

Este documento es la referencia ÚNICA para validar la integridad del sistema. 
Cualquier desviación de estos puntos se considera un estado "ROTO".

## 1. Versión y Entorno
- [ ] **Versión**: Archivo `VERSIONES.md` debe indicar que el estado actual es V3.
- [ ] **Python**: Mínimo 3.10. Comprobar con `python3 --version`.
- [ ] **Node.js**: Mínimo 18. Comprobar con `node --version`.
- [ ] **Bun**: Instalado y operativo en `/Users/ruben/.bun/bin/bun`.

## 2. Integridad Física (Ubicación por defecto)
- [ ] **Directorio Base**: Debe existir `~/MCP-servers/MCP-agent-memory`.
- [ ] **Binarios Críticos**: 
    - `~/MCP-servers/MCP-agent-memory/engine/bin/llama-server` (Ejecutable)
    - `~/MCP-servers/MCP-agent-memory/bin/qdrant` (Ejecutable)
- [ ] **Modelos de IA**:
    - `~/MCP-servers/MCP-agent-memory/models/bge-m3-Q4_K_M.gguf` (Mínimo 430MB)
    - `~/MCP-servers/MCP-agent-memory/models/all-minilm-l6-v2_q8_0.gguf`

## 3. Servicios y Puertos
- [ ] **Qdrant**: Corriendo en `http://127.0.0.1:6333`.
- [ ] **1MCP Gateway**: Corriendo en `http://127.0.0.1:3050/mcp`.
- [ ] **Launchd**: Comprobar con `launchctl list | grep memory-server`.

## 4. Base de Datos y Memoria
- [ ] **Colecciones Qdrant**: Deben existir `automem`, `conversations` y `mem0_memories`.
- [ ] **Tools Database**: `~/MCP-servers/MCP-agent-memory/tests/e2e/tools.db` debe tener > 100 herramientas.
- [ ] **Vault (Obsidian)**: Mínimo 17 notas en `~/MCP-servers/MCP-agent-memory/vault/`.

## 5. Herramientas y Plugins
- [ ] **Delegate Tool**: NO usar en OpenCode 1.4.6 (regresión conocida).
- [ ] **Task Tool**: Usar como alternativa síncrona obligatoria.
- [ ] **Quarantine**: Los binarios NO deben tener el atributo `com.apple.quarantine`.

---
*Validado por Ruben y Gemini CLI — 15 de Abril de 2026*
