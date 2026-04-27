# La Mochila — CÓMO FUNCIONA POR DENTRO

  La mecánica. El plumbing. Lo que pasa cuando escribís un mensaje.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PARTE A: EL CABLEADO — Qué se conecta con qué

  Cuando escribís "arreglá el bug de auth", pasa ESTO:

  ┌─────────────────────────────────────────────────────┐
  │  OpenCode (editor con IA)                            │
  │                                                     │
  │  1. Tú escribes → OpenCode recibe el texto          │
  │                                                     │
  │  2. OpenCode le pasa al AGENTE (gentleman, glm-5.1) │
  │     El agente decide qué tools usar                  │
  │                                                     │
  │  3. ANTES de ejecutar cualquier tool:                │
  │     ┌─────────────────────────────┐                 │
  │     │ backpack-orchestrator.ts    │                 │
  │     │ Hook: tool.execute.before   │                 │
  │     │                             │                 │
  │     │ ¿Es write/edit? → Gate 1    │                 │
  │     │ ¿Es .env?        → Gate 3    │                 │
  │     │ ¿Es archivo largo?→ Gate 4   │                 │
  │     │ ¿6+ tools seguidas?→ Gate 5  │                 │
  │     │ ¿Escribir sin leer?→ Gate 6  │                 │
  │     └─────────────────────────────┘                 │
  │     Si un gate dice BLOCKED → el tool NO se ejecuta │
  │                                                     │
  │  4. El tool se ejecuta (bash, edit, read, MCP...)    │
  │                                                     │
  │  5. DESPUÉS de ejecutar:                             │
  │     ┌─────────────────────────────┐                 │
  │     │ backpack-orchestrator.ts    │                 │
  │     │ Hook: tool.execute.after    │                 │
  │     │                             │                 │
  │     │ POST http://127.0.0.1:8890  │                 │
  │     │ /api/ingest-event           │                 │
  │     │ {type:"tool_call",          │                 │
  │     │  content:"bash: git log"}   │                 │
  │     └─────────────────────────────┘                 │
  │     El evento va al sidecar → automem → raw_events  │
  │                                                     │
  └─────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PARTE B: EL MCP — Cómo OpenCode habla con La Mochila

  OpenCode no sabe nada de memoria. Habla MCP (Model Context Protocol).

  MCP = un protocolo que dice:
  - "Tengo estas herramientas disponibles"
  - "Cada herramienta acepta estos parámetros"
  - "El resultado viene en este formato"

  Nuestro servidor MCP tiene 53 herramientas organizadas así:

  ┌───────────────────────────────────────────────────┐
  │  MCP-agent-memory (un solo proceso Python)        │
  │                                                   │
  │  ├── automem (8 tools)                            │
  │  │   ├── memorize        → guardar algo           │
  │  │   ├── ingest_event    → capturar evento        │
  │  │   ├── heartbeat       → "estoy vivo, turno N"  │
  │  │   └── ...                                       │
  │  │                                                │
  │  ├── autodream (5 tools)                           │
  │  │   ├── dream           → soñar (consolidar)     │
  │  │   ├── consolidate     → forzar consolidación   │
  │  │   ├── get_semantic    → leer L3                │
  │  │   └── get_consolidated→ leer L4                │
  │  │                                                │
  │  ├── vk-cache (4 tools)                            │
  │  │   ├── request_context → "dame contexto para X" │
  │  │   ├── push_reminder   → recordar algo al agent │
  │  │   ├── check_reminders → hay recordatorios?     │
  │  │   └── detect_context_shift → cambió de tema?   │
  │  │                                                │
  │  ├── conversation-store (5 tools)                  │
  │  │   ├── save_conversation                        │
  │  │   ├── get_conversation                         │
  │  │   ├── search_conversations                     │
  │  │   ├── list_threads                             │
  │  │   └── status                                   │
  │  │                                                │
  │  ├── mem0 (4 tools)                                │
  │  │   ├── add_memory                               │
  │  │   ├── search_memory                            │
  │  │   ├── get_all_memories                         │
  │  │   └── delete_memory                            │
  │  │                                                │
  │  ├── engram (7 tools)                              │
  │  │   ├── save_decision                            │
  │  │   ├── search_decisions                         │
  │  │   ├── list_decisions                           │
  │  │   ├── vault_write / vault_read                 │
  │  │   └── ...                                      │
  │  │                                                │
  │  └── sequential-thinking (7 tools)                 │
  │      ├── sequential_thinking                      │
  │      ├── create_plan / update_plan_step           │
  │      ├── propose_change_set                       │
  │      └── ...                                      │
  │                                                   │
  │  Total: ~53 herramientas                           │
  │  Transporte: stdio (entrada/salida estándar)       │
  │  OpenCode lo lanza como proceso hijo               │
  └───────────────────────────────────────────────────┘

  PERO TAMBIÉN hay un SIDECAR HTTP (puerto 8890):

  ┌───────────────────────────────────────────────────┐
  │  El sidecar corre DENTRO del mismo proceso MCP    │
  │                                                   │
  │  El backpack-orchestrator.ts (TypeScript)         │
  │  NO puede llamar tools MCP directamente.          │
  │  Llama al sidecar por HTTP.                       │
  │                                                   │
  │  fetch("http://127.0.0.1:8890/api/ingest-event")  │
  │  fetch("http://127.0.0.1:8890/api/heartbeat")     │
  │  fetch("http://127.0.0.1:8890/api/request-context")│
  │  fetch("http://127.0.0.1:8890/api/save-conversation")│
  │                                                   │
  │  El sidecar recibe el HTTP y llama la función     │
  │  Python internamente. Sin pasar por MCP stdio.    │
  │                                                   │
  │  WHY: Los hooks de OpenCode son TypeScript.       │
  │  La memoria es Python. El puente es HTTP.         │
  └───────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PARTE C: STORAGE — Dónde vive cada cosa

  HOY (problemático):

  ┌──────────────┐
  │   Qdrant     │ ← VECTOR DB (búsqueda semántica)
  │              │
  │  automem     │    L1 working memory
  │  mem0        │    L3 semantic
  │  conv-store  │    conversaciones (NO PERTENECE ACÁ)
  └──────────────┘
  ┌──────────────┐
  │  JSONL file  │ ← raw_events.jsonl
  │              │    L0 eventos crudos
  └──────────────┘
  ┌──────────────┐
  │  filesystem  │ ← engram Markdown files
  │              │    decisiones + vault
  └──────────────┘

  Problema: 3 capas en Qdrant. Si cae, cae todo.
  Problema: Conversaciones son TEXTO, no VECTORES.

  MAÑANA (lo correcto):

  ┌──────────────┐
  │  JSONL       │ ← L0 eventos crudos (append-only)
  └──────────────┘
  ┌──────────────┐
  │  SQLite      │ ← L1/L2 working + episodic
  │              │    Conversaciones COMPLETAS
  │              │    Entities, relationships, timeline
  │              │    FTS5 para full-text search
  │              │    ACID, transacciones, WAL mode
  └──────────────┘
  ┌──────────────┐
  │  Qdrant      │ ← SOLO L3/L4 semantic + consolidated
  │              │    Solo vectores. Solo embeddings.
  │              │    No payloads gigantes.
  └──────────────┘
  ┌──────────────┐
  │  filesystem  │ ← engram (Markdown, perdurable)
  └──────────────┘

  SQLite + Qdrant se enlazan por IDs.
  El timeline vive en SQLite. Los embeddings en Qdrant.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PARTE D: LOS GATES — Cómo te protegen

  El backpack-orchestrator tiene 6 gates. Cada uno es
  una función TypeScript que corre ANTES o DESPUÉS de
  una tool call. Si lanza Error, la tool NO se ejecuta.

  Gate 1: CONTEXT VERIFICATION (v1.3)
  ────────────────────────────────────
  ¿El agente verificó contexto antes de escribir?
  Si no → BLOCKED. No podés modificar código sin
  saber qué hay en memoria sobre ese proyecto.

  Gate 2: CONVENTIONAL COMMITS (v1.2)
  ───────────────────────────────────
  ¿El commit message sigue el formato tipo(scope): desc?
  Si no → BLOCKED. "arreglé cositas" NO pasa.

  Gate 3: .ENV PROTECTION (v1.5)
  ──────────────────────────────
  ¿Estás editando .env, .pem, .key, credentials?
  → BLOCKED. Nunca tocar secrets.

  Gate 4: LONG FILE GUARD (v1.5)
  ──────────────────────────────
  ¿Estás leyendo un archivo de +1000 líneas sin offset/limit?
  → BLOCKED. Primero verificá el tamaño, luego leé por partes.

  Gate 5: CONTEXT SPIRAL (v1.5)
  ─────────────────────────────
  ¿Hiciste 6+ tool calls sin que el usuario hable?
  → BLOCKED. Probablemente entraste en un loop.

  Gate 6: BLIND WRITE (v1.5)
  ──────────────────────────
  ¿Estás escribiendo un archivo que no leíste primero?
  → BLOCKED. Leé primero, escribd después.

  Todos DESACTIVADOS ahora (defaults invertidos).
  Se activan con BACKPACK_GATE_*=true en el entorno.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PARTE E: LO QUE VIENE DEL ESTADO DEL ARTE

  Investigamos 20+ sistemas y papers. Lo que aplica:

  ┌──────────────────────┬─────────────────────────────┐
  │  PATRÓN              │  CÓMO LO APLICAMOS          │
  ├──────────────────────┼─────────────────────────────┤
  │                      │                             │
  │  TMS (Truth          │  Cada memoria guarda POR    │
  │  Maintenance System) │  QUÉ existe (justificación) │
  │                      │  Si la base cambia, las     │
  │                      │  dependientes se re-evalúan │
  │                      │                             │
  │  CRAG (Corrective    │  Scoring de relevancia →    │
  │  RAG)                │  si es bajo, buscar más     │
  │                      │  acción correctiva          │
  │                      │                             │
  │  Chain-of-           │  Verificar INDEPENDIENTE    │
  │  Verification        │  del draft original         │
  │                      │  Sin sesgo de lo que crees  │
  │                      │                             │
  │  Agent-as-Judge      │  Un agent con tools MCP     │
  │  (2026)              │  VERIFICA memorias contra   │
  │                      │  fuentes reales             │
  │                      │                             │
  │  FreshQA             │  Clasificar memorias por    │
  │                      │  velocidad de cambio:       │
  │                      │  never/slow/fast/realtime   │
  │                      │  Las fast se verifican más  │
  │                      │                             │
  │  PROV-O (W3C)        │  Cada memoria lleva:        │
  │                      │  wasGeneratedBy,            │
  │                      │  wasDerivedFrom,            │
  │                      │  wasRevisionOf              │
  │                      │  Lineaje completo           │
  │                      │                             │
  └──────────────────────┴─────────────────────────────┘

  Lo que NO existe en ningún lado:
  → Enforcement por código a nivel de tool call MCP
  → Verificación continua de memorias en un servidor de 53 tools
  → Timeline + entities + lifecycle en un sistema de memoria para agents
  → Lo que estamos construyendo es NUEVO.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PARTE F: LOS DOS ARCHIVOS QUE IMPORTAN

  El sistema se configura en DOS lugares:

  1. opencode.json (~/config/opencode/opencode.json)
     ├── agents (17, con temperatura 0.1)
     ├── providers (Z.AI, LMStudio, Mimo...)
     ├── MCP servers (cuáles conectar)
     └── permissions (qué está permitido)

  2. backpack-orchestrator.ts (~/config/opencode/plugins/)
     ├── hooks (chat.message, tool.execute.before/after, etc)
     ├── gates (6 reglas de enforcement)
     ├── BACKPACK_RULES (system prompt inyectado)
     └── engram integration (Go binary para decisiones)

  PROBLEMA ENCONTRADO HOY:
  → El archivo en el repo (adapters/opencode/) y el que corre
    (plugins/) estaban DESINCRONIZADOS.
    El repo tenía v1.2 (538 líneas). El running tenía v1.5 (690).
  → Hay que sincronizar o va a pasar otra vez.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PARTE G: RESUMEN EN UNA PÁGINA

  ┌───────────────────────────────────────────────────┐
  │  LA MOCHILA = Memoria para agents de programación │
  │                                                   │
  │  CÓMO: 53 MCP tools + sidecar HTTP + hooks TS    │
  │                                                   │
  │  QUÉ CAPTURA: eventos, decisiones, conversaciones │
  │                                                   │
  │  CÓMO ORDENA: L0→L1→L2→L3→L4 (consolidación)    │
  │                                                   │
  │  CÓMO BUSCA: vk-cache (embeddings + ranking)     │
  │                                                   │
  │  CÓMO PROTEGE: 6 gates de código (bloquean)      │
  │                                                   │
  │  QUÉ FALLA: Qdrant caído, conversations rotas,   │
  │             entities dormidas, tests = mocks      │
  │                                                   │
  │  PRÓXIMO: SQLite para storage + timeline +        │
  │           VK cache para Qwen 1M + colmena agents  │
  │                                                   │
  │  ARCHIVOS:                                        │
  │  ROADMAP.md → plan por versiones                  │
  │  LA-MOCHILA-4-ANIOS.md → esta explicación        │
  │  LA-MOCHILA-EXPLICADA.md → versión detallada     │
  │  engram/issues/ → problemas abiertos              │
  │  engram/architecture/ → decisiones de diseño      │
  │  engram/golden-rules/ → temperatura 0.1 forever   │
  └───────────────────────────────────────────────────┘
