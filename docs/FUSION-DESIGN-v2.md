# Fusión Memory Server + Plandex: Diseño de Implementación v2

**Fecha**: 2026-04-18
**Estado**: Diseño arquitectónico detallado
**Autor**: Análisis profundo basado en código fuente de ambos proyectos

---

## 1. DIAGNÓSTICO: Qué tenemos vs Qué necesitamos

### Stack actual (production venv)
```
httpx 0.28.1      → HTTP client (Qdrant REST, Ollama API)
pydantic 2.12     → Models/validation
mcp 1.27.0        → MCP server SDK
pydantic-settings → Env config
python-dotenv     → .env loading
Pygments 2.20     → Syntax highlighting (ya disponible!)
rich              → Pretty printing
starlette         → ASGI framework
```

**No hay**: tree-sitter, qdrant-client, numpy, torch, sentence-transformers
**Sí hay**: Python AST built-in, Pygments (30+ lenguajes), regex, REST directo a Qdrant

### Gap analysis: Lo que Plandex hace mejor

| Capacidad | Plandex | Memory Server | Gap |
|-----------|---------|---------------|-----|
| Code parsing | tree-sitter (30+ langs, syntax-aware) | Python AST + regex | **CRÍTICO** |
| Context selection | AI Architect decide qué cargar | Determinista (classify_intent) | **ALTO** |
| Model routing | 9 roles con modelo/temp diferente | 1 modelo | **ALTO** |
| Diff management | Sandbox aislado + validación | No existe | **MEDIO** |
| Plan branching | Git-like branches | No existe | **BAJO** (nice-to-have) |
| Token efficiency | Maps (10% del archivo) | Archivos completos | **CRÍTICO** |

---

## 2. ARQUITECTURA: Cómo absorber Plandex sin reimplementarlo

### Principio: NO forkear, NO traducir Go→Python, ABSORBER conceptos

Plandex tiene 76K líneas de Go. No las vamos a reescribir. Vamos a implementar los **conceptos** usando nuestro stack existente, optimizado para nuestro caso de uso (backpack de memoria de agentes).

### 2.1 Code Maps: Tree-sitter → Pygments + AST mejorado

**Plandex usa**: Go bindings de tree-sitter para parsear 30+ lenguajes
**Nosotros**: Ya tenemos Pygments 2.20 (pip installado) + Python AST built-in

**Estrategia**: 3-tier code mapping

```
Tier 1: Python → ast.parse() (built-in, perfecto, 0ms)
Tier 2: 30+ lenguajes → Pygments lexer (ya instalado, extrae tokens)
Tier 3: Estructura → regex patterns (fallback universal)
```

**Por qué NO tree-sitter Python bindings**:
- Requiere compilar C bindings por lenguaje
- Añade dependencias pesadas (tree-sitter + 30+ grammars)
- Pygments ya está instalado y hace 90% del trabajo
- Para backpack de memoria, no necesitamos parseo perfecto — necesitamos MAPAS

#### Implementación: `shared/retrieval/code_map.py`

```python
"""Code Map Generator — Plandex-inspired syntax-aware code mapping.

Uses Pygments (already installed) for 30+ language support.
Extracts: functions, classes, methods, imports, types, constants.
Output: Compact map (~10% of original file size).

Performance target: <5ms per file (vs ~50ms for tree-sitter).
"""

from __future__ import annotations
import ast
import re
from pathlib import Path
from pygments import lex
from pygments.lexers import get_lexer_for_filename, ClassNotFound
from pygments.token import Token

def generate_map(file_path: str, project_root: str | None = None) -> CodeMap:
    """Generate a compact code map for any file.
    
    Returns a CodeMap with:
    - symbols: [{name, type, line, signature}]
    - imports: [str]
    - summary: compressed string (~10% of file)
    - sha: for cache invalidation
    """
    path = Path(file_path)
    if not path.exists():
        return None
    
    content = path.read_text(encoding="utf-8", errors="replace")
    sha = hashlib.sha256(content.encode()).hexdigest()[:12]
    
    # Tier selection
    if path.suffix == ".py":
        return _python_map(content, path, sha)  # AST (perfect)
    else:
        return _pygments_map(content, path, sha)  # Pygments (good)
```

**Optimización clave**: El map se cachea por SHA. Solo se regenera si el archivo cambió.
Se almacena en Qdrant como tipo `code_map` en L2 con embedding del summary.

### 2.2 Model Packs → Perfiles de Agente (Engram L3)

**Plandex usa**: 9 roles con modelo/temperature/topP diferente
**Nosotros**: 1 LLM para todo

**Estrategia**: Model Packs como engram decisions (L3)

```python
# Stored in engram as a decision pattern
MODEL_PACKS = {
    "default": {
        "architect": {"temp": 0.5, "role": "context_selection"},
        "planner":   {"temp": 0.7, "role": "planning"},
        "coder":     {"temp": 0.1, "role": "implementation"},
        "validator": {"temp": 0.1, "role": "validation"},
        "summarizer":{"temp": 0.3, "role": "summarization"},
    },
    "conservative": {
        "architect": {"temp": 0.3},
        "planner":   {"temp": 0.5},
        "coder":     {"temp": 0.0},  # deterministic
        "validator": {"temp": 0.0},
    }
}
```

**NO es un server nuevo**. Es un engram pattern que el vk-cache consulta.
Los "model packs" se almacenan como archivos YAML/JSON en `data/memory/engram/model-packs/`.

### 2.3 Architect AI → vk-cache mejorado

**Plandex usa**: 2 fases (Context → Implementation)
**Nosotros**: 1 fase (request_context retorna todo)

**Estrategia**: El vk-cache YA es el architect. Mejorar `classify_intent` con LLM ranking.

```
Flujo actual:
  query → classify_intent (determinista) → retrieve → pack

Flujo mejorado:
  query → classify_intent (determinista, <1ms)
        → si needs_ranking=True:
            → LLM ranking (micro-LLM, ~50ms)
            → reordenar resultados
        → retrieve con code maps (no archivos completos)
        → pack con token budget inteligente
```

**Optimización**: El LLM ranking solo se usa cuando `needs_ranking=True` (detectado por classify_intent). El 80% de las queries NO necesitan ranking.

### 2.4 Diff Sandbox → `shared/diff_sandbox.py`

**Plandex usa**: git diff + tree-sitter validation + auto-fix loop
**Nosotros**: git diff (ya disponible) + Pygments syntax check

**Estrategia**: Módulo shared, no server separado

```python
"""Diff Sandbox — isolated change management with syntax validation.

Inspired by Plandex's build-validate-fix loop.
Does NOT touch project files until explicitly approved.
"""

def create_sandbox(project_root: str) -> Sandbox:
    """Create isolated sandbox for pending changes."""
    
def propose_change(sandbox, file_path, new_content) -> Change:
    """Propose a change. Returns diff + validation status."""
    
def validate_syntax(content, language) -> ValidationResult:
    """Validate syntax using Pygments lexer (0 external deps)."""
    
def apply_change(sandbox, change_id) -> ApplyResult:
    """Apply approved change to project."""
    
def reject_change(sandbox, change_id) -> None:
    """Discard a proposed change."""
```

**Se invoca desde** el sequential-thinking server cuando implementa código.
Cada diff se almacena en L3 (engram) para autoaprendizaje.

---

## 3. NUEVO DISEÑO: 7 servers → 7 servers (misma cantidad, más capaces)

### No añadimos servers — MEJORAMOS los existentes

| Server | Antes | Después (fusión) |
|--------|-------|-------------------|
| **vk-cache** | Retrieval + context assembly | + Architect AI + code maps + LLM ranking |
| **automem** | Ingest events | + Diff tracking + build validation events |
| **autodream** | Dream cycle consolidation | + Code map regeneration + pattern mining |
| **engram** | Decisions + patterns | + Model packs + diff history + code patterns |
| **mem0** | Semantic memory CRUD | Sin cambios (ya funciona bien) |
| **conversation-store** | Thread management | + Plan tracking (plan_id in threads) |
| **sequential-thinking** | Step-by-step reasoning | + Model pack integration + diff sandbox |

### Fluxograma completo (post-fusión)

```
AGENTE (pi/Claude/etc)
    │
    ├─ "Necesito contexto para implementar X"
    │     │
    │     ▼
    │   vk-cache.request_context(query, intent="plan")
    │     │
    │     ├─ classify_intent()         → determinista, <1ms
    │     │    └─ entities: [AuthService, JWT, verify]
    │     │    └─ intent: code_lookup
    │     │    └─ needs_ranking: true
    │     │
    │     ├─ code_maps.lookup(entity)  → SHA-cached maps
    │     │    └─ AuthService:
    │     │         def __init__(self, secret_key)
    │     │         def verify(token) → TokenPayload
    │     │         def refresh(token) → str
    │     │
    │     ├─ retrieve_hybrid()         → Dense + BM25 + RRF
    │     │    └─ L1: 3 items (working memory)
    │     │    └─ L2: 5 items (episodic + repo symbols)
    │     │    └─ L3: 3 items (engram decisions)
    │     │    └─ L4: 2 items (consolidated patterns)
    │     │
    │     ├─ [IF needs_ranking]        → LLM ranking (~50ms)
    │     │    └─ Reorder by relevance to specific task
    │     │
    │     └─ pack_context()            → Token budget allocation
    │          └─ 8000 tokens de contexto óptimo
    │
    ├─ "Implementa la función X"
    │     │
    │     ▼
    │   sequential-thinking.create_plan(task, model_pack="default")
    │     │
    │     ├─ planner role (temp 0.7) → Plan de subtasks
    │     │
    │     ├─ Para cada subtask:
    │     │    ├─ coder role (temp 0.1) → Código propuesto
    │     │    ├─ diff_sandbox.propose_change() → Diff aislado
    │     │    ├─ validator role (temp 0.1) → Validación
    │     │    └─ automem.ingest("diff_proposed", ...)
    │     │
    │     └─ diff_sandbox.apply_all() → Aplicar cambios aprobados
    │
    ├─ "Aprendizaje automático (dream cycle)"
    │     │
    │     ▼
    │   autodream.consolidate()
    │     │
    │     ├─ Scan diffs en L1 (últimas 24h)
    │     │    └─ Accepted diffs → "successful patterns"
    │     │    └─ Rejected diffs → "anti-patterns"
    │     │
    │     ├─ Regenerar code maps stale
    │     │    └─ SHA mismatch → regenerate + re-embed
    │     │
    │     └─ Promote patterns to L3/L4
    │          └─ "Python: import modules at top of file"
    │          └─ "React: use useCallback for event handlers"
    │
    └─ Siguiente sesión → vk-cache inyecta patrones aprendidos
```

---

## 4. OPTIMIZACIÓN EXTREMA: Velocidad, Rendimiento, Eficiencia

### 4.1 Code Map Caching (10x más rápido que leer archivos)

```
Primera vez (cold start):
  1. Generate map con Pygments: ~5ms/file
  2. Embed map summary: ~15ms (llama_server) o ~1s (subprocess)
  3. Store en Qdrant L2: ~10ms
  Total: ~30ms/file (llama_server) o ~1s (subprocess)

Segunda vez (cached):
  1. SHA del archivo → lookup en Qdrant: ~5ms
  2. SHA match → usar cached map: 0ms
  Total: ~5ms/file

Tercera vez (embedding cached en LRU):
  1. SHA lookup: ~5ms
  2. Map retrieved from Qdrant: ~5ms
  Total: ~10ms/file
```

**Resultado**: Context loading para un proyecto de 100 archivos:
- Cold: ~3s (acceptable, solo primera vez)
- Warm: ~0.5s (10x más rápido que cargar archivos completos)
- Hot: ~0.1s (LRU cache hit)

### 4.2 Embedding Pipeline (72x faster con llama_server)

```
Subprocess (actual):    ~1,087ms per embedding
llama_server HTTP:       ~15ms per embedding
LRU cache hit:           ~0.01ms per embedding

Para 100 archivos:
  Subprocess: 108,700ms (~2 min) ❌
  llama_server: 1,500ms (1.5s)  ✅
  LRU cached: 1ms              🚀
```

**Acción**: Asegurar que llama_server esté corriendo como daemon (ya implementado en embedding.py).

### 4.3 Token Budget Intelligence

Plandex maneja hasta 2M tokens de contexto. Nosotros necesitamos ser más inteligentes.

```python
def allocate_token_budget(query_intent, total_budget=8000):
    """Token budget allocation by intent type."""
    
    BUDGET_PROFILES = {
        "code_lookup":  {  # "¿Dónde está AuthService.verify()?"
            "maps": 1000,      # Code maps (símbolos)
            "context": 3000,   # Archivo relevante (no completo)
            "memory": 2000,    # Memorias L1-L4
            "rules": 1000,     # Compliance rules
            "buffer": 1000,    # Breathing room
        },
        "plan": {  # "Implementa sistema de auth"
            "maps": 2000,      # Maps de múltiples archivos
            "context": 2000,   # Archivos clave
            "memory": 2500,    # Decisiones pasadas + patrones
            "rules": 1000,
            "buffer": 500,
        },
        "debug": {  # "Error en AuthService.verify()"
            "maps": 500,       # Map del archivo con error
            "context": 3000,   # Archivo completo + stack trace
            "memory": 2500,    # Errores pasados + fixes
            "rules": 500,
            "buffer": 1500,
        },
    }
```

**Clave**: Para `code_lookup`, el map ocupa solo 1000 tokens vs 3000+ del archivo completo.
Para `debug`, se necesita el archivo completo + stack trace.

### 4.4 Diff Sandbox Learning Loop

```
diff_sandbox.propose_change()
    │
    ├─ Si ACCEPTED:
    │    automem.ingest("diff_accepted", {file, diff, context})
    │    → L1 → L3 (pattern: "esta transformación funcionó")
    │
    ├─ Si REJECTED:
    │    automem.ingest("diff_rejected", {file, diff, reason})
    │    → L1 → L3 (anti-pattern: "este tipo de cambio falla")
    │
    └─ Dream cycle (L3 → L4):
         "En archivos Python, imports siempre al principio"
         "En React, usar useCallback para handlers en useEffect"
         "Patrón común: interface → implementation → test"
```

---

## 5. PLAN DE IMPLEMENTACIÓN (por prioridad)

### Fase 1: Code Maps (impacto MÁS alto, effort MEDIO)

**Archivos a crear/modificar**:
1. `shared/retrieval/code_map.py` (NUEVO) — Generador de maps con Pygments
2. `shared/retrieval/repo_map.py` (MODIFICAR) — Usar code_map.py en vez de regex
3. `shared/retrieval/index_repo.py` (MODIFICAR) — Indexar code maps en Qdrant
4. `vk-cache/server/main.py` (MODIFICAR) — Usar maps en context assembly

**Dependencias**: 0 nuevas (Pygments ya instalado)

**Optimización**:
- Cache por SHA en Qdrant
- Solo re-generar si SHA cambió
- LRU para maps frecuentes

### Fase 2: Model Packs (impacto ALTO, effort BAJO)

**Archivos a crear/modificar**:
1. `engram/server/main.py` (MODIFICAR) — Add model pack CRUD tools
2. `data/memory/engram/model-packs/default.yaml` (NUEVO) — Default pack
3. `sequential-thinking/server/main.py` (MODIFICAR) — Use model packs

**Dependencias**: 0 nuevas (YAML ya soportado por PyYAML)

### Fase 3: Diff Sandbox (impacto MEDIO, effort MEDIO)

**Archivos a crear/modificar**:
1. `shared/diff_sandbox.py` (NUEVO) — Sandbox aislado
2. `automem/server/main.py` (MODIFICAR) — Track diff events
3. `autodream/server/main.py` (MODIFICAR) — Mine diff patterns

**Dependencias**: 0 nuevas (git diff + Pygments syntax check)

### Fase 4: LLM Ranking (impacto ALTO, effort BAJO)

**Archivos a crear/modificar**:
1. `shared/llm/config.py` (MODIFICAR) — Add ranking function
2. `shared/retrieval/__init__.py` (MODIFICAR) — Integrate ranking

**Dependencias**: 0 nuevas (ya tenemos LLM backend)

### Fase 5: Architect AI (impacto ALTO, effort MEDIO)

**Archivos a crear/modificar**:
1. `vk-cache/server/main.py` (MODIFICAR) — Architect mode
2. `shared/retrieval/__init__.py` (MODIFICAR) — 2-phase retrieval

**Dependencias**: 0 nuevas

---

## 6. MÉTRICAS DE ÉXITO

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| Context assembly time | ~2-5s | ~0.3-0.5s | 5-10x |
| Token efficiency | 100% (archivo completo) | ~10% (solo map) | 10x |
| Code map coverage | Python only | 30+ lenguajes | ∞ |
| Model routing | 1 modelo | N roles con temps | Precisión ↑ |
| Diff management | Manual | Sandbox + validation | Calidad ↑ |
| Auto-aprendizaje | Básico | Diffs + patterns + maps | Inteligencia ↑ |
| Dependencias nuevas | — | 0 | 🎯 |

---

## 7. LO QUE NO HACEMOS (y por qué)

| Feature de Plandex | Decisión | Razón |
|--------------------|----------|-------|
| PostgreSQL DB | ❌ No | Ya tenemos Qdrant (REST), no necesitamos SQL |
| Go CLI Bubble Tea | ❌ No | Nuestros agentes son headless (MCP protocol) |
| tree-sitter C bindings | ❌ No | Pygments cubre 90% del caso de uso con 0 deps |
| SaaS cloud auth | ❌ No | Todo es local/self-contained |
| 2M token context | ❌ No | Optimizamos para 8-48K tokens (smart selection) |
| Plan branching | ⏸️ Después | Nice-to-have, no crítico para MVP |
| Streaming responses | ❌ No | MCP protocol es request-response |
| Custom providers | ❌ No | Ya tenemos Ollama/llama.cpp/LM Studio |

---

## 8. AUTOAPRENDIZAJE: El Backpack Inteligente

El concepto central: cada agente carga su backpack (memory server) que **aprende** de cada interacción.

### Capas de aprendizaje

```
L0 (Raw Events):
  automem.ingest("diff_proposed", {file, diff, timestamp})
  automem.ingest("diff_accepted", {file, diff, timestamp})
  automem.ingest("diff_rejected", {file, diff, reason, timestamp})
  automem.ingest("build_succeeded", {file, diff, timestamp})
  automem.ingest("build_failed", {file, diff, error, timestamp})

L1 (Working Memory — sesión actual):
  "Última propuesta: AuthService.py → agregar verify()"
  "Estado: pendiente aprobación"
  "Último error: missing import 'datetime'"

L2 (Episodic Memory — últimos 7 días):
  "Sesión 2026-04-18: implementé auth system, 3 diffs accepted, 1 rejected"
  "Code map de AuthService: 5 símbolos, 3 dependencias"

L3 (Semantic Memory — permanente):
  Pattern: "Python auth patterns"
    - Always import datetime, hashlib, secrets
    - Use bcrypt for passwords, JWT for tokens
    - Verify tokens in middleware, not in routes
  Anti-pattern: "Common Python errors"
    - Missing imports (70% of rejected diffs)
    - Wrong indentation (15% of rejected diffs)
    - Missing self parameter (10% of rejected diffs)

L4 (Consolidated — dream cycle):
  "For Python authentication modules, the checklist is:
   1. Import: datetime, hashlib, secrets, bcrypt, jwt
   2. Define constants at module level
   3. Use class-based service pattern
   4. Always include verify() and refresh()
   5. Add type hints to all methods
   This pattern has 95% acceptance rate across 23 implementations."

L5 (Context Assembly — vk-cache):
  Cuando el agente dice "implementa auth":
  → L3 pattern: "Python auth patterns" (confidence: 0.92)
  → L4 consolidated: "Auth checklist" (confidence: 0.95)
  → Code map: existing auth files
  → Inject into context window
```

### Loop de mejora continua

```
    ┌─────────────────────────────────────┐
    │                                     │
    ▼                                     │
  Agente pide tarea                       │
    │                                     │
    ▼                                     │
  vk-cache inyecta contexto               │
  (L3 patterns + L4 consolidated          │
   + code maps + recent memory)           │
    │                                     │
    ▼                                     │
  Agente implementa                       │
    │                                     │
    ├─ Éxito → automem.ingest(success) ──►┤ → dream cycle → L3/L4
    │                                     │
    └─ Fracaso → automem.ingest(fail) ──►─┘ → dream cycle → L3/L4
                                           (anti-patterns)
```

---

## 9. RESUMEN EJECUTIVO

### Qué hacemos
1. **Code Maps** con Pygments (0 deps nuevas, 30+ lenguajes, 10x token efficiency)
2. **Model Packs** como engram patterns (roles con temps optimizados)
3. **Diff Sandbox** con git diff + Pygments validation
4. **LLM Ranking** para queries complejas (micro-LLM ~50ms)
5. **Architect AI** como vk-cache mejorado (2-phase retrieval)

### Qué NO hacemos
- No añadimos servers (7 → 7)
- No añadimos dependencias (0 nuevas)
- No forkeamos Plandex
- No traducimos Go → Python

### Impacto esperado
- **Velocidad**: 5-10x más rápido (code maps + SHA cache + llama_server)
- **Tokens**: 10x más eficiente (maps vs archivos completos)
- **Calidad**: Model packs + diff validation + autoaprendizaje
- **Inteligencia**: Dream cycle mina diffs → patterns → auto-injected context

### Esfuerzo total estimado
- Fase 1 (Code Maps): ~4h de implementación
- Fase 2 (Model Packs): ~2h
- Fase 3 (Diff Sandbox): ~3h
- Fase 4 (LLM Ranking): ~2h
- Fase 5 (Architect AI): ~3h
- **Total: ~14h**

---

## APÉNDICE A: Plandex Prompt System (referencia)

### Roles y sus prompts (para nuestros model packs)

| Rol | Temp | Propósito | Tokens típicos |
|-----|------|-----------|----------------|
| Architect | 0.5 | Seleccionar contexto relevante | 2K-4K |
| Planner | 0.7 | Dividir tarea en subtasks | 1K-2K |
| Coder | 0.1 | Generar código (determinístico) | 2K-8K |
| Builder | 0.1 | Validar builds (determinístico) | 500-1K |
| Validator | 0.1 | Syntax check + fix | 500-1K |
| Summarizer | 0.3 | Resumir cambios | 200-500 |
| Namer | 0.3 | Nombrar planes/branches | 50-100 |
| CommitMsg | 0.3 | Commit messages | 50-100 |
| ExecStatus | 0.1 | Evaluar resultado de comandos | 100-200 |

## APÉNDICE B: Code Map Output Format

### Input (archivo Python):
```python
"""Authentication service for the application."""

import hashlib
import jwt
from datetime import datetime, timedelta

class AuthService:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    def create_token(self, user_id: str, expires_hours: int = 24) -> str:
        payload = {
            "user_id": user_id,
            "exp": datetime.utcnow() + timedelta(hours=expires_hours)
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> dict:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
```

### Output (code map, ~15% del tamaño original):
```
`auth/service.py` (24 lines, 621 chars)
  imports: hashlib, jwt, datetime, timedelta
  class AuthService
    __init__(self, secret_key: str, algorithm: str = "HS256")
    create_token(self, user_id: str, expires_hours: int = 24) → str
    verify_token(self, token: str) → dict
```

### Tokens: 60 (map) vs 400 (archivo completo) = **85% reducción**

## APÉNDICE C: Flujo Completo con Diffs

```
1. Agente: "Agrega refresh_token a AuthService"

2. vk-cache.request_context("refresh_token AuthService"):
   → code_map: AuthService (3 métodos existentes)
   → L3 pattern: "JWT refresh pattern" (confidence 0.88)
   → L4 consolidated: "Auth module checklist"
   → Total: ~2000 tokens (vs ~8000 del archivo + memories)

3. sequential-thinking.create_plan("Agregar refresh_token"):
   → planner (temp 0.7): "Subtask 1: Add refresh method, Subtask 2: Update tests"
   
4. Implementación:
   → coder (temp 0.1): genera código
   → diff_sandbox.propose_change("auth/service.py", new_content)
   → validator (temp 0.1): verifica syntax + imports
   → automem.ingest("diff_proposed", ...)

5. Agente revisa diff → approve
   → diff_sandbox.apply_change(change_id)
   → automem.ingest("diff_accepted", ...)
   → code_map regenera (SHA cambió)

6. Dream cycle (noche):
   → "Refresh token pattern: 95% success rate"
   → "Python: agregar método a clase existente → agregar self parameter"
   → Store en L4 (consolidated)
```
