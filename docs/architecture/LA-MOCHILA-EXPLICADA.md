# La Mochila — Explicada de Verdad

> Última actualización: 2026-04-27
> Estado: DOCUMENTO HONESTO — muestra lo que funciona Y lo que no

---

## 1. ¿Qué es La Mochila?

Imaginate que sos un programador que trabaja todo el día. Tenés un asistente que:
- Te escucha todo lo que decís
- Anota cada decisión que tomás
- Te recuerda qué hiciste ayer, la semana pasada, el mes pasado
- Te AVISA si estás por cometer un error

**Eso es La Mochila.** Un sistema de memoria para asistentes de programación (agents) que usan IA.

No es un chatbot. Es la **memoria** del chatbot.

---

## 2. Las Piezas del Sistema

```
┌─────────────────────────────────────────────────┐
│                    TÚ                            │
│           (Ruben, el programador)                │
│                                                  │
│              ┌──────────┐                        │
│              │ OpenCode │  ← Tu editor con IA    │
│              └─────┬────┘                        │
│                    │                             │
└────────────────────┼────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│              CLI-agent-memory                    │
│         (El tractor — dirige todo)               │
│                                                  │
│   ┌──────────────────────────────────────┐       │
│   │     MCP-agent-memory                 │       │
│   │     (El motor — 53 herramientas)     │       │
│   │                                      │       │
│   │  ┌──────────┐  ┌──────────┐         │       │
│   │  │ automem  │  │autodream │         │       │
│   │  │ (eventos)│  │ (sueños) │         │       │
│   │  └──────────┘  └──────────┘         │       │
│   │  ┌──────────┐  ┌──────────┐         │       │
│   │  │ vk-cache │  │ mem0     │         │       │
│   │  │ (búsqueda│  │ (memorias│         │       │
│   │  │  intelig)│  │  semánt) │         │       │
│   │  └──────────┘  └──────────┘         │       │
│   │  ┌──────────┐  ┌──────────┐         │       │
│   │  │ engram   │  │ conv-    │         │       │
│   │  │ (decision│  │ store    │         │       │
│   │  │  +vault) │  │ (hilos)  │         │       │
│   │  └──────────┘  └──────────┘         │       │
│   │  ┌──────────┐                       │       │
│   │  │ seq-     │                       │       │
│   │  │ thinking │                       │       │
│   │  │ (razón)  │                       │       │
│   │  └──────────┘                       │       │
│   └──────────────────────────────────────┘       │
│                                                  │
│   ┌──────────────────────────────────────┐       │
│   │  backpack-orchestrator (plugin)      │       │
│   │  (Automatiza todo lo que puede)      │       │
│   └──────────────────────────────────────┘       │
│                                                  │
└─────────────────────────────────────────────────┘
```

### ¿Qué hace cada pieza?

| Pieza | Función | Estado REAL |
|-------|---------|-------------|
| **automem** | Captura eventos, heartbeats, working memory | ✅ Funciona |
| **autodream** | Consolida memorias, sueña, promueve entre capas | ✅ Funciona |
| **vk-cache** | Búsqueda inteligente con ranking y frescura | ⚠️ Parcial — Qdrant caído |
| **mem0** | CRUD semántico de memorias | ⚠️ Depende de Qdrant |
| **engram** | Decisiones de arquitectura + vault Obsidian | ✅ Funciona |
| **conversation-store** | Guarda hilos de conversación | ❌ ROTO — ISSUE-002 |
| **sequential-thinking** | Cadenas de razonamiento | ✅ Funciona |
| **backpack-orchestrator** | Automatiza todo vía hooks | ✅ Funciona (gates apagados) |

---

## 3. Las Capas de Memoria

```
  TIEMPO ──→

  L0           L1            L2           L3          L4
  RAW ────→ WORKING ────→ EPISODIC ──→ SEMANTIC ──→ CONSOLIDATED
  (crudo)   (trabajo)    (episodios)  (conceptos)  (resúmenes)

  "git       "arreglé     "Sesión de   "Decisión:   "v1.5 shipped
   commit    bug en       debugging    usar SQLite   con 6 gates
   abc123"   auth.py"     auth.py"     para conv."   de seguridad"

  Cada 1     Cada 5       Cada 1h      Cada noche   Permanente
  segundo    minutos
```

### Estado REAL de cada capa

| Capa | Storage | Estado |
|------|---------|--------|
| L0 Raw | JSONL (archivo plano) | ✅ Funciona — 3600+ eventos |
| L1 Working | Qdrant | ⚠️ Qdrant caído |
| L2 Episodic | Qdrant | ⚠️ Qdrant caído |
| L3 Semantic | Qdrant | ⚠️ Qdrant caído |
| L4 Consolidated | Qdrant | ⚠️ Qdrant caído |

**Problema: Las capas L1-L4 usan el mismo Qdrant. Si cae Qdrant, cae todo.**
**Decisión: Separar. L0→JSONL, L1/L2→SQLite, L3/L4→Qdrant.**

---

## 4. Qué Funciona de Verdad

```
  ┌─────────────────────────────────────────────┐
  │           ✅ FUNCIONA (verificado)            │
  │                                              │
  │  • Event capture (raw_events.jsonl)          │
  │  • Heartbeats automáticos                    │
  │  • Engram decisions + vault                  │
  │  • Sequential thinking                       │
  │  • Backpack hooks (auto-capture)             │
  │  • Sidecar HTTP (puerto 8890)                │
  │  • Gates de código (cuando están activos)    │
  │  • Ingest de eventos user_prompt/tool_call   │
  └─────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────┐
  │           ⚠️ PARCIAL (condicionado)          │
  │                                              │
  │  • vk-cache search (si Qdrant vive)          │
  │  • mem0 CRUD (si Qdrant vive)                │
  │  • Context injection (si vk-cache funciona)  │
  │  • Freshness scoring (existe, sin datos)     │
  │  • Background verification (hook existe,     │
  │    pero consolidar ≠ verificar)              │
  └─────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────┐
  │           ❌ NO FUNCIONA                     │
  │                                              │
  │  • conversation_store (ISSUE-002)            │
  │  • Entity graph (ISSUE-005)                  │
  │  • Timeline backbone (ISSUE-006)             │
  │  • Relationships (ISSUE-005)                 │
  │  • Integration tests (ISSUE-003)             │
  │  • Cualquier cosa que toque Qdrant           │
  │    (ISSUE-001)                               │
  └─────────────────────────────────────────────┘
```

---

## 5. Los Issues (Problemas Reales)

```
  PRIORIDAD DE ARREGLO:

  1. ISSUE-001  Qdrant caído          ┐
  2. ISSUE-002  Conversations rotas    │ Primero — sin esto
  3. ISSUE-004  Storage por capas     ┘ no hay nada más
  4. ISSUE-003  Tests son mocks      ── Después — saber la verdad
  5. ISSUE-006  Timeline backbone     ┐
  6. ISSUE-005  Entities + Relations  │─ La cuerda guía
  7. ISSUE-009  Conversaciones íntegras┘
  8. ISSUE-008  VK Cache Quantization ┐ Futuro
  9. ISSUE-010  Agent Hive            ┘
```

---

## 6. Cómo Sabemos Si Algo Funciona

### HOY: No lo sabemos
- Los tests son mocks → siempre verde
- Qdrant caído → nadie se entera
- Conversation_store falla → error silencioso

### MAÑANA (lo que necesitamos):

```
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ SMOKE    │    │INTEGRA-  │    │  UNIT    │
  │ TEST     │    │ TION     │    │  TEST    │
  │          │    │ TEST     │    │  (mocks) │
  │ ¿Vivo?   │    │ ¿Ciclo   │    │ ¿Lógica  │
  │          │    │ completo?│    │ ok?      │
  │ ping     │    │ save→    │    │ función  │
  │ Qdrant   │    │ search→  │    │ aislada  │
  │ ping     │    │ retrieve │    │          │
  │ SQLite   │    │          │    │          │
  │ ping     │    │ Servicios│    │          │
  │ API      │    │ REALES   │    │          │
  └──────────┘    └──────────┘    └──────────┘
      30s             5min            1min
   Al arrancar    Al deployar      Al commit
```

---

## 7. El Camino (Roadmap)

```
  ESTAMOS ACÁ                          VAMOS ACÁ
       │                                    │
       ▼                                    ▼
  v1.5 (gates)  →  v1.5.1  →  v1.6  →  v1.6.1  →  v1.7  →  v2.0
  (hecho)        (conv     (VK      (timeline   (ctx    (colmena
                 integro)  cache)   cuerda guía) monitor) agentes)

                 ISSUE-002  ISSUE-008  ISSUE-006          ISSUE-010
                 ISSUE-004             ISSUE-005
```

---

## 8. La Verdad Sobre los Tests

```
  LO QUE TENEMOS:                    LO QUE PARECE:

  mock_client = AsyncMock()          80 tests ✅✅✅
  mock_client.put = AsyncMock()
  test: assert mock.called           ¡TODO VERDE!

  → No toca Qdrant real              → Sistema "perfecto"
  → No toca archivos reales          → Confianza falsa
  → No toca red real
  → El mock SIEMPRE devuelve OK

  LO QUE NECESITAMOS:

  qdrant = QdrantClient(REAL_URL)
  qdrant.upsert(REAL_DATA)
  result = qdrant.search(REAL_QUERY)
  assert result != []
  → Falla si Qdrant está caído       ← ESO es un test de verdad
```

---

## 9. El Investigación Estado del Arte (Resumen)

De la investigación realizada el 2026-04-27, los hallazgos clave:

| Enfoque | Qué hace | Aplicable? |
|---------|----------|------------|
| **Claude Code Hooks** | PreToolUse bloquea con exit code 2 | ✅ Ya lo tenemos (backpack gates) |
| **CRAG** | Evaluador entrenado scoring → corrective action | ✅ Aplicable a memoria |
| **Self-RAG** | Reflection tokens: IsRel, IsSup, IsUse | ✅ Memory verification tokens |
| **Chain-of-Verification** | Draft → plan verification → execute independently | ✅ Verificar memorias independientemente |
| **TMS (Truth Maintenance)** | Dependency graph + justification tracking | ✅ CADA memoria necesita justificación |
| **Agent-as-Judge (2026)** | Judge con tools que verifica contra fuentes | ✅ Judge que ejecuta MCP tools |
| **FreshQA** | Clasificar hechos por velocidad de cambio | ✅ Ya tenemos change_speed (v1.4) |
| **Promptfoo MCP Proxy** | Red teaming contra MCP servers | ✅ Testear nuestros 53 tools |
| **FActScore** | Descomponer en atomic facts, verificar cada uno | ✅ Verificar memorias atómicamente |

**Hallazgo principal: No existe ningún sistema que combine enforcement por código + verificación continua + 53 tools MCP. Lo que estamos construyendo es nuevo.**

---

*Documento vivo. Actualizar cada vez que se arregle o se encuentre un issue.*
*La honestidad es la primera herramienta del sistema.*
