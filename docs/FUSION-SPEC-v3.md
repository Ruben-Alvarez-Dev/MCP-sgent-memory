# SPEC: Fusión Memory Server + Plandex
## Spec-Driven Implementation Plan — v3.0

**Fecha**: 2026-04-18
**Estado**: SPEC — Aprobación pendiente
**Principio**: Spec primero, código después

---

## 0. INVARIANTES (no se negocian)

```
INV-1: 0 dependencias nuevas (pip install = 0)
INV-2: 7 servers → 7 servers (no se añaden servers)
INV-3: Stack actual: httpx, pydantic, mcp SDK, Pygments, PyYAML
INV-4: Todo self-contained dentro de MEMORY_SERVER_DIR
INV-5: Sin hardcoded paths, sin Path.home()
INV-6: Protocolo: MCP (stdin/stdout JSON-RPC)
INV-7: Vector store: Qdrant (REST, no client library)
INV-8: Embeddings: llama.cpp (subprocess o server HTTP)
INV-9: LLM: Ollama / llama.cpp / LM Studio (shared/llm/*)
```

---

## 1. CAPACIDAD: Code Maps

### SPEC-1.1: Code Map Generator

**Problema**: El retrieval actual carga archivos completos (100% tokens).
Plandex carga maps (símbolos + firmas) = ~10% tokens.

**Solución**: Generar maps con Pygments + Python AST, cacheados por SHA.

#### Archivo: `shared/retrieval/code_map.py` (NUEVO)

```
DEPENDS ON: Pygments (instalado), ast (built-in), hashlib (built-in)
MODIFICA: Nada (archivo nuevo)
AFECTA A: shared/retrieval/__init__.py (importa y usa)
```

#### Modelo de datos

```python
class CodeSymbol(BaseModel):
    """Un símbolo extraído de un archivo."""
    name: str               # "AuthService", "verify_token", "JWT_SECRET"
    type: str               # "class" | "function" | "method" | "constant" | "import" | "variable"
    line: int               # Número de línea donde empieza
    signature: str          # "def verify_token(self, token: str) -> dict"
    parent: str = ""        # Para métodos: nombre de la clase padre
    visibility: str = ""    # "public" | "private" | "protected"

class CodeMap(BaseModel):
    """Mapa compacto de un archivo de código."""
    file_path: str
    sha: str                # SHA-256[:12] del contenido completo
    language: str           # "python", "typescript", "go", etc.
    lines_total: int
    imports: list[str]      # ["hashlib", "jwt", "datetime"]
    exports: list[str]      # ["AuthService", "verify_token"] (solo los que exporta)
    symbols: list[CodeSymbol]
    summary: str            # "auth/service.py: 24 lines, 1 class (AuthService), 3 methods"
    map_text: str           # Representación compacta para injection (< 15% del original)
    created_at: str
```

#### Algoritmo por lenguaje

```
Lenguaje    │ Método          │ Librería     │ Precisión
────────────┼─────────────────┼──────────────┼──────────
Python      │ ast.parse()     │ built-in     │ 100%
TypeScript  │ Pygments lexer  │ pygments     │ ~85%
JavaScript  │ Pygments lexer  │ pygments     │ ~85%
Go          │ Pygments lexer  │ pygments     │ ~80%
Rust        │ Pygments lexer  │ pygments     │ ~80%
Java        │ Pygments lexer  │ pygments     │ ~80%
C/C++       │ Pygments lexer  │ pygments     │ ~75%
YAML/JSON   │ Regex parsing   │ built-in     │ ~90%
Markdown    │ Regex headings  │ built-in     │ ~95%
Otros       │ Fallback regex  │ built-in     │ ~60%
```

#### Funciones públicas

```
generate_code_map(file_path: str) → CodeMap | None
    Genera map para un archivo.
    Side effects: Ninguno (puro).
    Cache: No (responsabilidad del caller).
    Errores: Retorna None si no puede parsear.
    Tiempo: <5ms por archivo (Python AST), <20ms (Pygments).

format_map_text(code_map: CodeMap) → str
    Genera la representación compacta para injection.
    Ejemplo output:
        auth/service.py (24 lines, 1 class)
          imports: hashlib, jwt, datetime, timedelta
          class AuthService
            __init__(self, secret_key: str, algorithm: str = "HS256")
            create_token(self, user_id: str, expires_hours: int = 24) → str
            verify_token(self, token: str) → dict

generate_project_maps(project_root: str, 
                      suffixes: list[str] = [".py",".ts",".tsx",".js",".go",".rs",".java"],
                      exclude: list[str] = [".git","node_modules","__pycache__",".venv","qdrant"]
                     ) → dict[str, CodeMap]
    Genera maps para todos los archivos del proyecto.
    Tiempo: ~100ms para 50 archivos.

get_map_from_cache(file_path: str, current_sha: str) → CodeMap | None
    Busca map en Qdrant L2 por file_path + sha.
    Si sha match → retorna cached map.
    Si sha mismatch → None (caller debe regenerar).
    Tiempo: ~10ms (Qdrant search).

upsert_map_to_cache(code_map: CodeMap, embedding: list[float]) → None
    Almacena map en Qdrant L2.
    Reemplaza si ya existe (por file_path).
    Tiempo: ~15ms.
```

#### Formato del map_text (ejemplo)

Input: auth/service.py (621 chars, 24 lines)
```python
"""Auth service."""
import hashlib, jwt
from datetime import datetime, timedelta

class AuthService:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    def create_token(self, user_id: str, expires_hours: int = 24) -> str:
        payload = {"user_id": user_id, "exp": datetime.utcnow() + timedelta(hours=expires_hours)}
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> dict:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
```

Output map_text (~60 tokens, 85% reducción):
```
auth/service.py (24 lines, 621 chars, python)
  imports: hashlib, jwt, datetime, timedelta
  class AuthService
    __init__(self, secret_key: str, algorithm: str = "HS256")
    create_token(self, user_id: str, expires_hours: int = 24) → str
    verify_token(self, token: str) → dict
```

#### Criterios de aceptación

```
AC-1.1.1: generate_code_map("file.py") retorna CodeMap con symbols correctos
AC-1.1.2: map_text tiene <20% de los tokens del archivo original
AC-1.1.3: generate_code_map("file.xyz") con lenguaje desconocido retorna None (no crash)
AC-1.1.4: SHA se recalcula correctamente (mismo contenido = mismo SHA)
AC-1.1.5: Funciona para al menos: .py, .ts, .js, .go, .rs, .java, .yaml, .md
AC-1.1.6: <5ms por archivo Python, <20ms por archivo con Pygments
AC-1.1.7: 0 dependencias nuevas (solo Pygments + stdlib)
```

---

### SPEC-1.2: Code Map Indexación en Qdrant

**Problema**: Los maps generados necesitan ser buscables por embedding.

**Solución**: Almacenar maps en Qdrant L2 como tipo `code_map`.

#### Modificación: `shared/retrieval/index_repo.py`

```
CAMBIOS:
  - Añadir _build_code_map_points() que usa code_map.py
  - Integrar en build_repo_index_points() existente
  - Usar tipo "code_map" (no "repo_symbol") para maps nuevos
  - Mantener backward compatibility con repo_symbol existente
```

#### Qdrant payload para code_map

```json
{
    "memory_id": "sha256(auth/service.py:code_map:AuthService)",
    "layer": 2,
    "type": "code_map",
    "file_path": "auth/service.py",
    "sha": "a1b2c3d4e5f6",
    "language": "python",
    "lines_total": 24,
    "symbol_count": 4,
    "class_count": 1,
    "function_count": 3,
    "imports": ["hashlib", "jwt", "datetime", "timedelta"],
    "exports": ["AuthService"],
    "content": "auth/service.py (24 lines, 621 chars, python)\n  imports: hashlib, jwt, datetime, timedelta\n  class AuthService\n    __init__(self, secret_key: str, algorithm: str = \"HS256\")\n    create_token(self, user_id: str, expires_hours: int = 24) → str\n    verify_token(self, token: str) → dict",
    "summary": "auth/service.py: 1 class (AuthService), 3 methods",
    "created_at": "2026-04-18T12:00:00Z",
    "source": "code_map_indexer"
}
```

#### Búsqueda de maps

```
Búsqueda por embedding:
  query_embedding → Qdrant search → top-K maps → filtrar por type="code_map"

Búsqueda directa (sin embedding):
  GET qdrant/collections/automem/points/scroll
  filter: { "type": "code_map", "file_path": "auth/service.py" }
  → Retorna map si existe con SHA matching

Invalidación:
  Si file SHA cambió → borrar map viejo + generar nuevo + upsert
```

#### Criterios de aceptación

```
AC-1.2.1: index_repo.py genera puntos code_map además de repo_symbol
AC-1.2.2: Los maps son buscables por embedding (semantic search)
AC-1.2.3: Los maps son recuperables por file_path (direct lookup)
AC-1.2.4: SHA mismatch → regeneración automática
AC-1.2.5: Backward compatible: repo_symbol existentes siguen funcionando
```

---

### SPEC-1.3: vk-cache usa Code Maps en Context Assembly

**Problema**: vk-cache carga archivos completos. Con maps usa 10x menos tokens.

**Solución**: Para queries tipo `code_lookup`, usar map_text en vez de archivo completo.

#### Modificación: `vk-cache/server/main.py`

```
CAMBIOS en request_context():
  - Antes de retrieval, buscar code maps relevantes
  - Para code_lookup: map_text + archivo solo si es necesario
  - Para debug: archivo completo + error trace
  - Para plan: maps de múltiples archivos + L3 patterns
```

#### Lógica de selección

```
if intent == "code_lookup":
    1. Buscar code maps por entities (embedding search)
    2. Inyectar map_text (no archivo completo)
    3. Si necesita más detalle → cargar solo la función relevante
    
elif intent == "debug":
    1. Buscar code map del archivo con error
    2. Cargar archivo completo (necesita ver el código real)
    3. Buscar errores pasados (L1/L2)
    
elif intent == "plan":
    1. Buscar code maps de archivos relacionados
    2. Inyectar maps (visión general)
    3. Buscar patrones L3/L4 (cómo se hizo antes)
    
elif intent == "decision_recall":
    1. Buscar engram decisions
    2. Code maps como contexto adicional
    3. No cargar archivos completos
```

#### Criterios de aceptación

```
AC-1.3.1: request_context con intent=code_lookup retorna maps, no archivos completos
AC-1.3.2: Tokens devueltos <20% vs cargar archivos completos
AC-1.3.3: Para intent=debug, se incluye archivo completo
AC-1.3.4: Maps stale (SHA mismatch) se regeneran automáticamente
AC-1.3.5: Si no hay maps, fallback a comportamiento actual (backward compatible)
```

---

## 2. CAPACIDAD: Model Packs

### SPEC-2.1: Model Pack Definition y Storage

**Problema**: Un solo modelo/temp para todo. Plandex usa 9 roles optimizados.

**Solución**: Model packs como archivos YAML en engram, consultados por sequential-thinking.

#### Archivo: `data/memory/engram/model-packs/default.yaml` (NUEVO)

```yaml
# Model Pack: default
# Configuración de roles para agentes de coding

name: default
description: "Balanced model pack for general coding tasks"

roles:
  architect:
    temperature: 0.5
    purpose: "Context selection — decide what to load"
    max_tokens: 2000
    use_for:
      - classify_context_needs
      - rank_relevance
      - decide_file_loading

  planner:
    temperature: 0.7
    purpose: "Break tasks into subtasks, think creatively"
    max_tokens: 4000
    use_for:
      - create_plan
      - decompose_problem
      - evaluate_approaches

  coder:
    temperature: 0.1
    purpose: "Generate deterministic code"
    max_tokens: 8000
    use_for:
      - implement_subtask
      - fix_bug
      - write_test

  validator:
    temperature: 0.1
    purpose: "Verify code correctness, syntax, logic"
    max_tokens: 2000
    use_for:
      - validate_syntax
      - check_compliance
      - review_diff

  summarizer:
    temperature: 0.3
    purpose: "Condense information"
    max_tokens: 1000
    use_for:
      - summarize_changes
      - write_commit_msg
      - brief_status
```

#### Criterios de aceptación

```
AC-2.1.1: YAML se parsea correctamente con PyYAML (ya instalado)
AC-2.1.2: Roles tienen temperature, purpose, max_tokens, use_for
AC-2.1.3: Múltiples packs pueden coexistir (default.yaml, conservative.yaml, etc.)
AC-2.1.4: Si YAML no existe, fallback a valores hardcoded (no crash)
```

### SPEC-2.2: Model Pack Lookup desde Engram

**Modificación**: `engram/server/main.py`

```
NUEVAS TOOLS:
  - get_model_pack(name: str = "default") → str
      Lee YAML de data/memory/engram/model-packs/{name}.yaml
      Retorna JSON del pack.

  - list_model_packs() → str
      Lista YAMLs disponibles en data/memory/engram/model-packs/

  - set_model_pack(name: str, yaml_content: str) → str
      Escribe nuevo YAML o actualiza existente.
```

#### Criterios de aceptación

```
AC-2.2.1: get_model_pack("default") retorna YAML parseado como JSON
AC-2.2.2: get_model_pack("nonexistent") retorna defaults hardcoded (no error)
AC-2.2.3: list_model_packs() lista los .yaml en el directorio
AC-2.2.4: set_model_pack() valida YAML antes de escribir
```

### SPEC-2.3: Sequential-Thinking usa Model Packs

**Modificación**: `sequential-thinking/server/main.py`

```
CAMBIOS en create_plan():
  - Consultar model pack (leer YAML directamente)
  - Incluir temperatures recomendadas en el plan output
  - NO cambiar el modelo (eso lo decide el caller/pi)
  
CAMBIOS en sequential_thinking():
  - Añadir parámetro model_pack: str = "default"
  - Incluir temperatures del pack en el framework output
```

**NOTA IMPORTANTE**: El memory server NO cambia modelos directamente.
Eso lo hace el agente (pi/Claude/etc) que consume el MCP tool.
El memory server SOLO recomienda temperatures y roles.

#### Criterios de aceptación

```
AC-2.3.1: create_plan() incluye temperatures del model pack en output
AC-2.3.2: sequential_thinking() acepta model_pack parameter
AC-2.3.3: Si pack no existe, usa defaults sin crash
AC-2.3.4: El server NO llama a ningún LLM directamente (solo lee config)
```

---

## 3. CAPACIDAD: Diff Sandbox

### SPEC-3.1: Módulo de Diff Aislado

**Problema**: No hay tracking de cambios propuestos/aplicados/rechazados.

**Solución**: Módulo shared que trackea diffs con metadata de resultado.

#### Archivo: `shared/diff_sandbox.py` (NUEVO)

```
DEPENDS ON: subprocess (git diff), Pygments (syntax check)
MODIFICA: Nada (archivo nuevo)
AFECTA A: sequential-thinking (usa DiffSandbox)
           automem (ingesta diff events)
```

#### Modelo de datos

```python
class DiffChange(BaseModel):
    """Un cambio propuesto."""
    change_id: str          # UUID
    file_path: str          # "auth/service.py"
    original_sha: str       # SHA del archivo original
    diff_text: str          # unified diff
    language: str           # "python"
    status: str             # "proposed" | "accepted" | "rejected" | "applied" | "failed"
    validation: ValidationResult | None
    metadata: dict          # {task, session_id, model_pack_role, etc.}
    created_at: str
    resolved_at: str | None = None

class ValidationResult(BaseModel):
    """Resultado de validación de un diff."""
    valid: bool
    syntax_ok: bool
    compliance_ok: bool
    errors: list[str]       # ["SyntaxError: invalid syntax on line 15"]
    warnings: list[str]     # ["Unused import: hashlib"]

class DiffSession(BaseModel):
    """Sesión de cambios aislados."""
    session_id: str
    project_root: str
    changes: list[DiffChange]
    created_at: str
```

#### Funciones públicas

```
class DiffSandbox:
    def __init__(self, project_root: str, staging_dir: str):
        """Crear sandbox para un proyecto."""
    
    def propose(self, file_path: str, new_content: str, 
                language: str = "", metadata: dict = None) → DiffChange:
        """Proponer un cambio.
        1. Leer archivo original (si existe)
        2. Generar unified diff (git diff --no-index)
        3. Validar syntax con Pygments
        4. Guardar en staging_dir/{change_id}.json
        5. Retornar DiffChange con status="proposed"
        
    def validate(self, change: DiffChange) → ValidationResult:
        """Validar un cambio propuesto.
        1. Syntax check: intentar lexer con Pygments, buscar errores
        2. Compliance check: usar shared/compliance (si aplica)
        3. Retornar ValidationResult
        
    def accept(self, change_id: str) → DiffChange:
        """Marcar como accepted (listo para aplicar)."""
    
    def reject(self, change_id: str, reason: str = "") → DiffChange:
        """Marcar como rejected."""
    
    def apply(self, change_id: str) → DiffChange:
        """Aplicar cambio al filesystem.
        1. Leer diff de staging
        2. Escribir archivo
        3. Validar que se aplicó correctamente
        4. Marcar status="applied"
        
    def apply_all_accepted(self) → list[DiffChange]:
        """Aplicar todos los changes accepted."""
    
    def get_pending(self) → list[DiffChange]:
        """Retornar changes con status="proposed" o "accepted"."""
    
    def get_history(self, file_path: str = "", limit: int = 50) → list[DiffChange]:
        """Historial de cambios (para autoaprendizaje)."""
    
    def cleanup(self, older_than_hours: int = 168) → int:
        """Limpiar staging de changes antiguos resueltos."""
```

#### Syntax validation con Pygments

```python
def _validate_syntax(content: str, language: str) → tuple[bool, list[str]]:
    """Validar syntax usando Pygments lexer.
    
    Método: Si Pygments puede tokenizar todo el contenido sin
    errores de lexer, la syntax es probablemente correcta.
    
    No es un parser completo (para eso es tree-sitter),
    pero detecta la mayoría de errores syntax.
    
    Returns: (is_valid, error_messages)
    """
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        # Fallback: buscar por extensión
        try:
            lexer = guess_lexer(content)
        except ClassNotFound:
            return (True, [])  # No podemos validar, asumimos OK
    
    tokens = list(lex(content, lexer))
    # Check for error tokens
    errors = []
    for token_type, token_value in tokens:
        if token_type in Token.Error or str(token_type).endswith('.Error'):
            errors.append(f"Syntax error near: {token_value[:50]}")
    
    return (len(errors) == 0, errors)
```

#### Criterios de aceptación

```
AC-3.1.1: propose() genera diff sin tocar el archivo original
AC-3.1.2: apply() solo funciona si status="accepted"
AC-3.1.3: reject() no elimina el diff (queda para autoaprendizaje)
AC-3.1.4: validate() usa Pygments (0 deps nuevas)
AC-3.1.5: Staging se guarda en data/staging_buffer/ (ya existe)
AC-3.1.6: cleanup() elimina changes >7 días con status resuelto
AC-3.1.7: Thread-safe: múltiples proposes en paralelo no se pisan
```

### SPEC-3.2: Diff Tracking en AutoMem

**Modificación**: `automem/server/main.py`

```
CAMBIOS en ingest_event():
  - Añadir soporte para event_type: "diff_proposed", "diff_accepted", 
    "diff_rejected", "diff_applied", "diff_failed"
  - Content = JSON del DiffChange
  - Layer = L1 (working memory)
  - Type = STEP
  - Metadata incluye: file_path, language, model_pack_role, session_id
```

#### Criterios de aceptación

```
AC-3.2.1: ingest_event("diff_proposed", ...) crea MemoryItem en L1
AC-3.2.2: Los diff events son buscables por embedding
AC-3.2.3: Autodream puede consolidar diff patterns de L1 → L3 → L4
```

### SPEC-3.3: Sequential-Thinking usa Diff Sandbox

**Modificación**: `sequential-thinking/server/main.py`

```
CAMBIOS en propose_change_set():
  - Usar shared/diff_sandbox.py en vez de implementación ad-hoc
  - Añadir validation automática (syntax + compliance)
  - Añadir metadata de model pack role

CAMBIOS en apply_sandbox():
  - Delegar a DiffSandbox.apply()
  - Trackear resultado (success/failure) en automem
```

#### Criterios de aceptación

```
AC-3.3.1: propose_change_set() valida syntax automáticamente
AC-3.3.2: apply_sandbox() trackea resultado en automem
AC-3.3.3: Diffs rechazados se guardan con reason
AC-3.3.4: No rompe API existente de propose_change_set/apply_sandbox
```

---

## 4. CAPACIDAD: LLM Ranking

### SPEC-4.1: Ranking de Resultados con Micro-LLM

**Problema**: classify_intent es determinista. Para queries complejas, el ranking
de resultados no es óptimo.

**Solución**: Cuando needs_ranking=True, usar micro-LLM para reordenar resultados.

#### Modificación: `shared/llm/config.py`

```
NUEVA FUNCIÓN:
  rank_by_relevance(query: str, items: list[ContextItem], top_k: int = 10) → list[ContextItem]
  
  Algoritmo:
    1. Si len(items) <= top_k → retornar sin ranking (no necesario)
    2. Si get_small_llm() no disponible → retornar sin ranking (graceful)
    3. Construir prompt:
       "Rank these items by relevance to: {query}\n
        Items:\n{numbered list of content[:200]}\n
        Return ONLY the numbers in order of relevance, comma-separated."
    4. Parsear respuesta (números separados por coma)
    5. Reordenar items
    6. Retornar top_k
  
  Tiempo: ~50-200ms (micro-LLM)
  Fallback: Si LLM falla, usar combined_score original
```

#### Modificación: `shared/retrieval/__init__.py`

```
CAMBIOS en _rank_and_fuse():
  - Después de scoring, si intent.needs_ranking == True:
    - Llamar rank_by_relevance(query, all_items, profile.token_budget // 500)
    - Reordenar por ranking LLM
  - Si needs_ranking == False: comportamiento actual (sin cambios)
```

#### Criterios de aceptación

```
AC-4.1.1: rank_by_relevance retorna items reordenados
AC-4.1.2: Si small LLM no disponible, no falla (usa score original)
AC-4.1.3: Solo se invoca cuando needs_ranking=True (no siempre)
AC-4.1.4: <200ms overhead por ranking
AC-4.1.5: No rompe retrieval sin ranking (backward compatible)
```

---

## 5. CAPACIDAD: Architect AI (vk-cache mejorado)

### SPEC-5.1: Two-Phase Context Selection

**Problema**: vk-cache hace una sola fase. Plandex tiene 2 fases (context → implementation).

**Solución**: Añadir modo "architect" a request_context que hace selección más inteligente.

#### Modificación: `vk-cache/server/main.py`

```
CAMBIOS en request_context():
  - Nuevo parámetro: mode: str = "standard" | "architect"
  - mode="standard": comportamiento actual
  - mode="architect": 
    1. Fase 1: Buscar code maps de archivos relevantes
    2. Fase 2: Decidir qué archivos cargar completos
    3. Fase 3: Inyectar maps + archivos seleccionados + memories
```

#### Nueva función interna

```python
async def _architect_select(
    query: str, 
    available_maps: list[CodeMap],
    token_budget: int,
) -> list[dict]:
    """Architect selection: decide QUÉ cargar.
    
    1. Embed query
    2. Search maps by similarity
    3. Prioritize: maps con más símbolos relevantes
    4. Decidir: map solo vs archivo completo
       - Si query es "dónde está X" → map solo
       - Si query es "implementa X" → archivo completo de X
    5. Fill remaining budget with memories
    """
```

#### Criterios de aceptación

```
AC-5.1.1: request_context(mode="architect") retorna contexto más preciso
AC-5.1.2: Para code_lookup: solo maps (no archivos completos)
AC-5.1.3: Para plan: maps + archivos clave + patterns L3/L4
AC-5.1.4: Para debug: archivos completos + error trace
AC-5.1.5: mode="standard" funciona igual que antes (backward compatible)
AC-5.1.6: Architect mode usa code maps cacheados (no regenera)
```

---

## 6. CAPACIDAD: Autoaprendizaje via Diff Patterns

### SPEC-6.1: Dream Cycle mina Diffs

**Problema**: El dream cycle consolida texto. Debería también consolidar
patrones de código (qué funciona, qué no).

**Solución**: Autodream escanea diff events y genera code patterns.

#### Modificación: `autodream/server/main.py`

```
CAMBIOS en consolidate():
  - Añadir paso: _mine_diff_patterns(L1_diffs) → list[str]
  - Escanear diff events en L1 (últimas 24h)
  - Para cada diff_accepted: generar pattern "en {language}, {change_type} funciona"
  - Para cada diff_rejected: generar anti-pattern "en {language}, {mistake_type} falla"
  - Almacenar como MemoryItem type=PATTERN en L3
```

#### Pattern mining

```python
def _mine_diff_patterns(diffs: list[dict]) -> list[dict]:
    """Mina patrones de diffs aceptados/rechazados.
    
    Output:
    [
        {
            "type": "pattern",
            "language": "python",
            "pattern": "Adding methods to existing class: always include self parameter",
            "evidence_count": 3,
            "success_rate": 1.0,
            "source": "diff_mining"
        },
        {
            "type": "anti_pattern", 
            "language": "python",
            "pattern": "Missing imports: hashlib, jwt, datetime are commonly forgotten",
            "evidence_count": 5,
            "failure_rate": 1.0,
            "source": "diff_mining"
        }
    ]
    """
```

#### Criterios de aceptación

```
AC-6.1.1: Autodream detecta diff events en L1
AC-6.1.2: Genera patterns para diffs aceptados (success patterns)
AC-6.1.3: Genera anti-patterns para diffs rechazados (failure patterns)
AC-6.1.4: Patterns se almacenan en L3 con type=PATTERN
AC-6.1.5: vk-cache puede inyectar patterns relevantes en context
AC-6.1.6: No rompe consolidación existente
```

---

## 7. PLAN DE EJECUCIÓN (orden de implementación)

### Dependencia entre specs

```
SPEC-1.1 (code_map.py)          ← Sin dependencias (nuevo archivo)
  └─→ SPEC-1.2 (index_repo)    ← Depende de 1.1
       └─→ SPEC-1.3 (vk-cache) ← Depende de 1.2

SPEC-2.1 (YAML)                 ← Sin dependencias
  └─→ SPEC-2.2 (engram tools)   ← Depende de 2.1
       └─→ SPEC-2.3 (seq-think) ← Depende de 2.2

SPEC-3.1 (diff_sandbox.py)     ← Sin dependencias
  └─→ SPEC-3.2 (automem)       ← Depende de 3.1
       └─→ SPEC-3.3 (seq-think) ← Depende de 3.1 + 3.2

SPEC-4.1 (LLM ranking)         ← Depende de shared/llm (existe)

SPEC-5.1 (architect mode)      ← Depende de 1.3 + 4.1

SPEC-6.1 (dream patterns)      ← Depende de 3.2
```

### Orden óptimo (considerando dependencias + impacto)

```
Sprint 1 (Foundation):     ~4h
  [1] SPEC-1.1: code_map.py
  [2] SPEC-2.1: default.yaml
  [3] SPEC-3.1: diff_sandbox.py

Sprint 2 (Integration):    ~4h  
  [4] SPEC-1.2: index_repo usa code_maps
  [5] SPEC-2.2: engram CRUD for model packs
  [6] SPEC-3.2: automem tracks diffs

Sprint 3 (Activation):     ~3h
  [7] SPEC-1.3: vk-cache usa maps
  [8] SPEC-2.3: sequential-thinking usa packs
  [9] SPEC-3.3: sequential-thinking usa sandbox

Sprint 4 (Intelligence):   ~3h
  [10] SPEC-4.1: LLM ranking
  [11] SPEC-5.1: Architect mode
  [12] SPEC-6.1: Dream patterns

TOTAL: ~14h
```

### Archivos nuevos (3)
```
shared/retrieval/code_map.py      ~200 lines
shared/diff_sandbox.py             ~300 lines
data/memory/engram/model-packs/default.yaml  ~40 lines
```

### Archivos modificados (7)
```
shared/retrieval/__init__.py       +50 lines (ranking integration)
shared/retrieval/index_repo.py     +40 lines (code_map points)
shared/llm/config.py               +60 lines (rank_by_relevance)
vk-cache/server/main.py            +80 lines (architect mode + maps)
engram/server/main.py              +40 lines (model pack tools)
automem/server/main.py             +20 lines (diff event types)
sequential-thinking/server/main.py  +60 lines (model packs + sandbox)
autodream/server/main.py           +50 lines (diff pattern mining)
```

### Líneas totales: ~900 líneas nuevas, 0 dependencias nuevas

---

## 8. RIESGOS Y MITIGACIONES

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Pygments no parsea bien lenguaje X | Media | Bajo | Fallback a regex (ya existe) |
| Syntax validation con Pygments da falsos positivos | Media | Bajo | Es advisory, no blocking |
| LLM ranking tarda >500ms | Baja | Medio | Timeout + fallback a scoring normal |
| SHA mismatch en maps (archivo cambió externamente) | Alta | Ninguno | Regeneración automática es el comportamiento correcto |
| Staging buffer llena disco | Baja | Bajo | cleanup() elimina >7 días |
| YAML de model pack corrupto | Baja | Bajo | Fallback a defaults hardcoded |

---

## 9. TEST PLAN

### Test unitarios (por spec)

```
SPEC-1.1: test_code_map_generator.py
  - test_python_ast_map()
  - test_typescript_pygments_map()
  - test_unknown_language_returns_none()
  - test_map_text_token_reduction()
  - test_sha_consistency()

SPEC-2.1: test_model_packs.py
  - test_parse_default_yaml()
  - test_missing_yaml_fallback()
  - test_multiple_packs()

SPEC-3.1: test_diff_sandbox.py
  - test_propose_creates_diff()
  - test_validate_catches_syntax_error()
  - test_apply_only_if_accepted()
  - test_reject_preserves_history()
  - test_cleanup_old_changes()

SPEC-4.1: test_llm_ranking.py
  - test_rank_reorders_by_relevance()
  - test_fallback_when_no_llm()
  - test_handles_malformed_response()

SPEC-5.1: test_architect_mode.py
  - test_code_lookup_returns_maps()
  - test_debug_returns_full_file()
  - test_plan_returns_maps_and_patterns()

SPEC-6.1: test_dream_patterns.py
  - test_mine_accepted_diff_pattern()
  - test_mine_rejected_diff_anti_pattern()
  - test_patterns_stored_in_l3()
```

### Test de integración

```
test_fusion_e2e.py:
  1. Generar code maps de un proyecto de prueba
  2. Almacenar en Qdrant
  3. request_context con intent=code_lookup
  4. Verificar: retorna maps, no archivos completos
  5. propose_change_set con diff
  6. Verificar: validation funciona
  7. apply_sandbox
  8. Verificar: diff trackeado en automem
  9. consolidate (dream)
  10. Verificar: pattern generado en L3
```
