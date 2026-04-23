# Sesión del 2026-04-23 — Cronología Completa

## Objetivo
Instalar y auditar MCP-agent-memory desde el repo de Ruben-Alvarez-Dev/MCP-sgent-memory.

## Secuencia de eventos

### Fase 1: Instalación inicial
- Se ejecutó el one-liner: `curl -fsSL .../install.sh | bash`
- El instalador compiló llama.cpp desde fuente con Metal
- Descargó modelo BGE-M3 (417MB)
- Creó Qdrant collections, venv, config
- Verificación: 19/20 checks pasaron (embedding dimension check falló, cosmético)

### Fase 2: Conexión a Pi
- Se copió `config/mcp.json` a `~/.pi/mcp.json`
- Pi reiniciado para cargar el MCP server

### Fase 3: Primeros bugs encontrados
- **Bug 1**: mem0 IDs no-UUID → Qdrant rechaza con 400
  - `mem0_20260422...` no es UUID válido
  - Fix: `str(uuid.uuid4())`
- **Bug 2**: conversation-store mismo bug de IDs
  - Fix: `str(uuid.uuid4())`

### Fase 4: llama-server apuntando a Homebrew
- El LaunchAgent `com.llama-server.plist` apuntaba a `/opt/homebrew/bin/llama-server`
- No al compilado en `engine/bin/`
- Fix: recompilar estático con Metal + actualizar plist

### Fase 5: Binarios compilados con dylibs rotas
- `engine/bin/llama-server` referenciaba librerías en `/var/folders/...` (tmp borrado)
- Fix: recompilación con `-DBUILD_SHARED_LIBS=OFF` y `GGML_METAL_EMBED_LIBRARY=ON`

### Fase 6: Descubrimiento del instalador incompleto
- install.sh NO copia `scripts/` (watchdog.sh, lifecycle.sh)
- install.sh NO crea LaunchAgents de watchdog/lifecycle
- install.sh borra build dir con dylibs aún referenciadas
- Fix: descarga manual de scripts + creación de plists

### Fase 7: Consolidación de LaunchAgents
- 10+ plists duplicados/heredados de instalación anterior (MCP-memory-server)
- Nombres inconsistentes (com.memory-server.*, com.agent-memory.*, com.qdrant.*)
- Fix: eliminación de duplicados, consolidación bajo `com.agent-memory.*`

### Fase 8: Qdrant storage path roto
- `bin/config.yaml` apuntaba a `./data` (vacío)
- Datos reales estaban en `./storage`
- Colecciones se perdieron al reiniciar Qdrant
- Fix: config.yaml → `storage_path: ./storage` + start-qdrant.sh con ulimit

### Fase 9: Sin auto-inicialización
- El MCP no creaba colecciones ni directorios al arrancar
- Fix: añadido `_initialize()` al unified server

### Fase 10: ensure_collection faltante
- autodream no llamaba `ensure_collection` antes de operar
- Fix: añadido a `_promote_l1_l2`, `_promote_l2_l3`, `_promote_l3_l4`

### Fase 11: Auditoría industrial
- Ejecutada auditoría a 10 dimensiones
- Resultado: 6 critical, 14 high, 8 medium, 5 low issues
- Ver archivo 03-AUDITORIA-COMPLETA.md

## Estado final de la sesión
- Sistema parcialmente funcional: 15/15 tests E2E pasan
- 5 LaunchAgents limpios bajo com.agent-memory.*
- 3 colecciones Qdrant con datos
- 10+ bugs documentados pendientes de fix
- Auditoría completa realizada con hallazgos críticos
