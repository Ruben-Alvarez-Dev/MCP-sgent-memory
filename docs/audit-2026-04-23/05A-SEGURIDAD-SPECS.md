# Grupo A — Seguridad Crítica

## Especificaciones

### SPEC-A1: Confine get_decision() a ENGRAM_PATH

**ID auditoría**: SEC-C1
**Severidad**: CRITICAL
**Módulo**: `src/engram/server/main.py`
**Archivo afectado**: línea `get_decision()`

**Problema**:
```python
async def get_decision(file_path: str) -> dict:
    p = Path(file_path)
    return _read(p) if p.exists() else {"status": "not_found"}
```
Acepta cualquier path absoluto. Un LLM o agente malicioso puede leer `/etc/passwd`, `~/.ssh/id_rsa`, etc.

**Spec de fix**:
```python
async def get_decision(file_path: str) -> dict:
    p = Path(file_path).resolve()
    engram_root = ENGRAM_PATH.resolve()
    if not str(p).startswith(str(engram_root)):
        return {"status": "forbidden", "error": "Path outside engram root"}
    if not p.exists():
        return {"status": "not_found"}
    return _read(p)
```

**Criterio de aceptación**:
- [ ] `get_decision("/etc/passwd")` → `{"status": "forbidden"}`
- [ ] `get_decision("../../../../etc/passwd")` → `{"status": "forbidden"}`
- [ ] `get_decision("/Users/ruben/MCP-servers/MCP-agent-memory/data/memory/engram/general/archivo.md")` → lee correctamente
- [ ] Symlinks fuera de engram son seguidos y bloqueados por resolve()

**Test**:
```python
def test_get_decision_path_traversal():
    result = await get_decision("/etc/passwd")
    assert result["status"] == "forbidden"
    
    result = await get_decision("../../../etc/shadow")
    assert result["status"] == "forbidden"
```

---

### SPEC-A2: Sanitizar name en set_model_pack()

**ID auditoría**: SEC-C2
**Severidad**: CRITICAL
**Módulo**: `src/engram/server/main.py`
**Archivo afectado**: línea `set_model_pack()`

**Problema**:
```python
async def set_model_pack(name: str, content: str) -> ModelPackResult:
    d = ENGRAM_PATH / "model-packs"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(content)
```
`name` no se sanitiza. `name="../../.bashrc"` escribe fuera de engram.

**Spec de fix**:
```python
async def set_model_pack(name: str, content: str) -> ModelPackResult:
    safe_name = sanitize_filename(name, field="model_pack_name")
    d = ENGRAM_PATH / "model-packs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{safe_name}.yaml").write_text(content, encoding="utf-8")
    return ModelPackResult(name=safe_name, status="set")
```

**Criterio de aceptación**:
- [ ] `set_model_pack("test", "...")` → crea `model-packs/test.yaml`
- [ ] `set_model_pack("../../.bashrc", "...")` → sanitiza a `bashrc.yaml` dentro de model-packs/
- [ ] `set_model_pack("my/model", "...")` → sanitiza a `model.yaml`
- [ ] Reutiliza `sanitize_filename()` existente en `shared/sanitize.py`

---

### SPEC-A3: Añadir sanitize a sequential-thinking

**ID auditoría**: SEC-H1
**Severidad**: HIGH (subido de medium por ser el único módulo sin sanitize)
**Módulo**: `src/sequential-thinking/server/main.py`

**Problema**: 0 llamadas a validate_ o sanitize_. Recibe `steps_json`, `title`, `session_id`, `thought` sin validación.

**Spec de fix**:
```python
from shared.sanitize import sanitize_text, sanitize_filename, validate_json_field

# En sequential_thinking():
title = sanitize_text(problem, max_length=500, field="problem")

# En record_thought():
thought = sanitize_text(thought, field="thought")

# En create_plan():
title = sanitize_text(title, max_length=500, field="title")
steps = validate_json_field(steps_json, field="steps_json")

# En propose_change_set():
title = sanitize_text(title, max_length=500, field="title")
```

**Criterio de aceptación**:
- [ ] Todos los parámetros string pasan por sanitize
- [ ] `steps_json` validado con validate_json_field (depth check, size check)
- [ ] session_id pasa por sanitize_thread_id

---

### SPEC-A4: Permisos .env a 600

**ID auditoría**: SEC-H2
**Severidad**: HIGH

**Problema**: `config/.env` es world-readable (644)

**Fix**:
```bash
chmod 600 ~/MCP-servers/MCP-agent-memory/config/.env
```

**Criterio de aceptación**:
- [ ] `stat -f "%Lp" config/.env` → `600`
- [ ] Install script debe crear .env con permisos 600

---

### SPEC-A5: Documentar modelo de amenazas

**Severidad**: LOW (documentación)
**Problema**: No existe threat model

**Spec**:
Crear `TEMP/06-THREAT-MODEL.md` documentando:
- Superficie de ataque (stdio MCP, Qdrant HTTP, filesystem)
- Trust boundaries (LLM ↔ MCP ↔ Qdrant ↔ filesystem)
- Amenazas conocidas y mitigaciones
- Asumptions (localhost-only, single-user, trusted LLM)
