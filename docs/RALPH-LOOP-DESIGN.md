# Arquitectura del "Ralph Loop" & Integración Workspace

## 1. Visión Global
El sistema evoluciona de un "Memory Server" pasivo a un "Motor de Ejecución Autónomo" (Pack). El objetivo es tomar un requerimiento (PRD), aislarlo, planificarlo, ejecutarlo y verificarlo sin intervención humana, erradicando la "pereza" del LLM mediante un bucle de control estricto.

## 2. Componentes del Ecosistema

### 2.1. `src/workspace/` (Aislamiento Físico)
Reemplaza el `diff_sandbox` virtual.
- **Git Worktrees:** Cada tarea se ejecuta en un clon ligero y temporal (`git worktree add`).
- **Seguridad:** Los fallos críticos, borrados accidentales o bucles infinitos ocurren en el worktree. El repo principal queda intacto.
- **Ejecución Nativa:** Provee una interfaz para ejecutar comandos reales (`npm test`, `go build`, `make`) dentro del worktree y capturar el `stdout/stderr` para retroalimentación.

### 2.2. `src/steering/` (Máquina de Estados y Prevención de Estancamiento)
El cerebro controlador que guía al LLM.
- **Fases Estrictas:** `PLANNING` -> `CODING` -> `VERIFICATION` -> `DONE`. El LLM no puede avanzar de fase si las validaciones (tests, linters) fallan.
- **Gestión de Estado:** Mantiene sincronizados los artefactos de la tarea (`PLAN.md`, `PROGRESS.md`).
- **Detector de Estancamiento (Stagnation Monitor):** 
  - Métrica 1: N intentos consecutivos sin modificar archivos.
  - Métrica 2: N intentos consecutivos repetiendo exactamente el mismo error de compilación.
  - Intervención: Si N > 3, el loop limpia la ventana de contexto (para eliminar la "alucinación en bucle") e inyecta un prompt de corrección dura.

### 2.3. El Loop Central (`loop.py`)
El ciclo `while True` que envuelve al LLM.
1. **Ensamblaje de Contexto:** Llama a `vk-cache` para inyectar Code Maps relevantes y el estado actual de `PROGRESS.md`.
2. **Inferencia LLM:** El LLM propone comandos de terminal o ediciones de archivos vía *Tool Calling* estructurado.
3. **Ejecución Material:** El `workspace` aplica los cambios en el disco.
4. **Verificación:** Si el LLM cree que terminó, el Loop corre la suite de tests. 
5. **Retroalimentación:** Si hay error, el Loop se lo inyecta como contexto obligatorio para la siguiente iteración. Si hay éxito, avanza la fase.

## 3. Sinergia con la Memoria (RAG & AutoDream)
- **Code Maps Optimizados:** El Loop usa los mapas (ya desarrollados) para no saturar el contexto mientras el agente itera.
- **Memoria Semántica (AutoDream):** Cuando el agente resuelve un error tras varios intentos fallidos en el `workspace`, el Loop envía el diff exitoso y el error original a `autodream` para consolidar un "patrón de resolución" que se usará en futuras tareas.

## 4. Eficiencia y Calidad
- **Cero Alucinaciones de Archivos:** Al usar el disco duro real, el LLM usa herramientas de lectura reales (`cat`, `grep` o herramientas MCP nativas), asegurando que siempre ve la realidad.
- **Tokens Controlados:** El reseteo de contexto tras estancamiento ahorra miles de tokens y dinero, evitando que el agente arrastre un historial de errores inútiles.
