# Diseño M8-Cleanup

## T1: Eliminación de archivos
```bash
rm src/shared/embedding.py
rm src/shared/embedding_cache.py
```
Verificación:
```bash
grep -r "from shared.embedding" src/ || echo "OK: no imports"
```

## T2: Migración de schema
Opciones:
1. **ALTER TABLE DROP** - requiere SQLite 3.35+, puede fallar si hay datos
2. **CREATE TABLE nuevo + COPY** - más seguro pero complejo
3. **Dejar columna como dead column** - menos agresivo

Decisión: Opción 3 (dead column) para M8. M9 migración completa.

Justificación:
- No hay datos críticos en columna vector
- Eliminación puede romper DBs existentes
- La columna ya no se usa (ignorada en INSERT/SELECT)

## T3: Rewriting tests
Nuevos patterns:
```python
# Antes: db.upsert(id, vector, payload)
# Después: db.upsert(id, payload=payload)

# Antes: db.search(vector, limit)
# Después: db.search_fts(query, limit)
```

## T4: README
Secciones a actualizar:
- "Architecture" → FTS5-first
- "Installation" → Sin EMBEDDING_* vars necesarias
- "API" → search_fts vs search
