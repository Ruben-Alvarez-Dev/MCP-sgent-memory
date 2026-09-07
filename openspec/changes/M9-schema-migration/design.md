# Diseño M9-Schema-Migration

## T1: Remoción de columna vector

### Opción A: ALTER TABLE DROP (agresivo)
```sql
ALTER TABLE points DROP COLUMN vector;
```
- **Pros**: Schema limpio, cero espacio desperdiciado
- **Cons**: Falla en SQLite < 3.35.0, rompe DBs existentes

### Opción B: Dead column (conservador)
- No tocar schema existente
- Solo dejar de usar en código
- **Pros**: Cero riesgo, compatible con todo
- **Cons**: Espacio desperdiciado (~4KB por punto)

**Decisión**: Opción A con guard
```python
def _ensure_schema(self):
    self._conn.execute("""
        CREATE TABLE IF NOT EXISTS points (...)
    """)
    # M9: Remove vector column if exists
    try:
        self._conn.execute("ALTER TABLE points DROP COLUMN vector")
    except sqlite3.OperationalError:
        pass  # Column doesn't exist or SQLite too old
```

### Código a eliminar
- `hash_vector()` function
- `_cosine()` function
- `_pack_vector()` method
- `_unpack_vector()` method
- Any vector-related imports

## T2: Rewriting tests

### Consolidation tests
Pattern nuevo:
```python
async def test_l1_l2_creates_episodes(db):
    await db.upsert("e1", payload={"content": "x", "agent_scope": "shared", "layer": 1})
    from shared.consolidation import consolidate_l1_l2
    ids = await consolidate_l1_l2(db)
    assert len(ids) == 1
    # Verify L2 point exists
    hits = await db.search_fts("test", limit=10)
    assert any(h["id"].startswith("ep-") for h in hits)
```

### Trunk test
```python
async def test_approve_promotion_tool_contract(db):
    # Use keyword args
    await db.upsert("s1", payload={"content": "...", "agent_scope": "shared"})
    result = await approve_promotion(["s1"], approved_by="user")
```

## T3: Eval fixture

### Estrategia
- Mantener 40 docs para parity con eval-40
- Reemplazar 4 chunks embedding.py con:
  - 2 docs de FTS5 implementation
  - 1 doc de entity extraction
  - 1 doc de consolidation pipeline

### Replacement sources
- `memory_db.py` → FTS5 triggers, two-phase search
- `entity.py` → extract_entities function
- `synonym.py` → dictionary expansion
- `consolidation.py` → dream_cycle function
