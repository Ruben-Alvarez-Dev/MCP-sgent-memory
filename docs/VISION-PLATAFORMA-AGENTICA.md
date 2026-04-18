# Plataforma Agéntica — Visión Completa

**Fecha**: 2026-04-18
**Estado**: Diseño inicial

## Problema

Gentle-ai y herramientas similares son genéricas. No saben del memory server, pierden reglas con el tiempo, no enforcement nada. Cualquier adaptación de gentle-ai subestima el desarrollo propio.

## Principios Obligatorios

- **Temperature MÁXIMO 0.1** — determinismo total, sin alucinaciones
- **Spec-driven OBLIGATORIO** — no se codea sin spec verificada y contrastada
- **Double-check** — nunca asumir, siempre verificar con evidencia
- **ZERO mock/demo/fake data** — siempre producción real
- **TDD obligatorio** — tests antes que código
- **Post-action verification** — después de cada acción, verificar resultado
- **Sandbox real** — protección ante desastres
- **Ralph loop activo** — mejora continua detectada por el sistema
- **Auto-testing** — el agente se pone a prueba a sí mismo, detecta errores temprano
- **No mentir** — si no sabe, dice que no sabe. Si falló, lo dice.

## Equipo Scrum Agéntico

| Rol | Responsabilidad |
|-----|----------------|
| **Product Owner** | Traduce propuestas de Ruben a backlog items correctos y manejables |
| **Scrum Master** | Vela por procesos, detecta desviaciones, protege al equipo |
| **Architect** | Decisiones técnicas, patrones, estructura del sistema |
| **Planner** | Descompone specs en tareas ejecutables con dependencias |
| **Dev Frontend** | UI, UX, componentes, estado, styling |
| **Dev Backend** | APIs, lógica de negocio, integraciones |
| **Dev DB** | Esquemas, migraciones, queries, optimización |
| **Dev Infra** | CI/CD, deploys, infraestructura, servicios |
| **QA Tester** | Verifica specs, tests, integración, regresiones |
| **DevOps** | Pipelines, monitoreo, rollback, disaster recovery |
| **Debugger** | Diagnóstico y resolución de bugs complejos |

## Flujo

```
Ruben propone
    ↓
PO traduce a specs ( Scrum artifacts)
    ↓
Architect valida (viabilidad técnica)
    ↓
Planner descompone (tareas + dependencias)
    ↓
Devs codean con TDD obligatorio
    ↓
QA verifica contra specs (no contra "parece que funciona")
    ↓
DevOps deploya con sandbox + rollback
    ↓
Memory server captura TODO (decisiones, errores, patrones, aprendizajes)
    ↓
Ralph loop detecta mejoras → las promueve a reglas (L3)
```

## Diferencia Fundamental con Gentle-ai

| | Gentle-ai | Nuestro Sistema |
|---|-----------|-----------------|
| Memoria | Context window (se pierde) | L3 semantic memory (persistente) |
| Reglas | Inyecta prompt → hope for the best | Grabadas en L3 → vk-cache las inyecta SIEMPRE |
| Enforcement | Ninguno | Temperature 0.1 + TDD + double-check + sandbox |
| Equipo | 1 agente genérico | Scrum team especializado |
| Specs | Opcional | Obligatorio, contrastado, verificado |
| Datos | Mock/demo OK | Solo producción real |
| Verificación | "Trust me" | Post-action verification automática |
| MCP | No los usa | Todos los agentes aprovechan TODOS los MCP |

## Arquitectura

```
┌─────────────────────────────────────────┐
│           Agente Orquestador             │
│  (CLI: memory-server setup/sync/run)    │
├─────────────────────────────────────────┤
│         Perfiles Agénticos               │
│  PO | SM | Architect | Planner |        │
│  DevFront | DevBack | DevDB | DevInfra  │
│  QA | DevOps | Debugger                 │
├─────────────────────────────────────────┤
│         Enforcement Layer                │
│  Specs | TDD | Double-check | Sandbox   │
├─────────────────────────────────────────┤
│       MCP Memory Server (6 capas)       │
│  L0→L1→L2→L3→L4→L5 + Dream Cycle       │
├─────────────────────────────────────────┤
│       MCP Adicionales (futuro)          │
│  browser | brave-search | github | ...  │
└─────────────────────────────────────────┘
```

## El Problema del vk-cache

El vk-cache está diseñado para inyectar contexto relevante, pero las reglas se pierden porque:
1. Las reglas están en prompts (context window) → se evictan
2. Deberían estar en L3 (semantic memory) → vk-cache las recupera SIEMPRE
3. Necesitamos que las reglas se almacenen como decisiones/patrones engram
4. Y que el vk-cache las priorice con peso alto en cada request_context

## Fases

### Fase 1: Memory Server + CLI Orquestador ✅ (en progreso)
- install.sh funcional con layout src/
- build-package.sh para armar distribuible
- Bootstrap dinámico en todos los servers

### Fase 2: CLI Orquestador
- `memory-server setup` — instala todo
- `memory-server sync` — configura agentes
- `memory-server status` — verifica salud
- Perfiles agénticos como datos en L3

### Fase 3: Enforcement Layer
- Specs obligatorios con verificación
- TDD workflow integrado
- Sandbox real
- Post-action verification hooks

### Fase 4: Equipo Scrum Agéntico
- Perfiles especializados
- Routing inteligente (qué agente para qué tarea)
- Memory-driven context para cada rol

### Fase 5: Ralph Loop Completo
- Detección automática de mejoras
- Promoción de aprendizajes a reglas
- Auto-diagnóstico del sistema
