# Design: M6-deterministic — Cero embeddings, retrieval puramente lexical

## 1. Schema evolution — FTS5 + entities + relations

### 1.1 FTS5 en points table
Se añade una tabla virtual FTS5 sincronizada por triggers:
```sql
CREATE VIRTUAL TABLE points_fts USING fts5(
  content,
  body='points',
  content_rowid='rowid'
);
CREATE TRIGGER pts_ai AFTER INSERT ON points BEGIN
  INSERT INTO points_fts(rowid, content) VALUES (new.rowid,
    json_extract(new.payload, '$.content'));
END;
CREATE TRIGGER pts_ad AFTER DELETE ON points BEGIN
  INSERT INTO points_fts(points_fts, rowid, content) VALUES('delete', old.rowid, '');
END;
CREATE TRIGGER pts_au AFTER UPDATE ON points BEGIN
  INSERT INTO points_fts(points_fts, rowid, content) VALUES('delete', old.rowid, '');
  INSERT INTO points_fts(rowid, content) VALUES (new.rowid,
    json_extract(new.payload, '$.content'));
END;
```

### 1.2 Entities table
```sql
CREATE TABLE entities (
  id TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('class','function','module','concept','decision','pattern')),
  agent_scope TEXT NOT NULL,
  layer INTEGER NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  mention_count INTEGER DEFAULT 1,
  PRIMARY KEY(id)
);
CREATE INDEX idx_entities_scope ON entities(agent_scope);
CREATE INDEX idx_entities_type ON entities(type);
```

### 1.3 Relations table
```sql
CREATE TABLE relations (
  from_entity TEXT NOT NULL,
  to_entity TEXT NOT NULL,
  relation_type TEXT NOT NULL CHECK(relation_type IN (
    'depends_on','implements','extends','uses','decides','fixes','part_of'
  )),
  agent_scope TEXT NOT NULL,
  strength REAL DEFAULT 1.0,
  created_at TEXT NOT NULL,
  PRIMARY KEY (from_entity, to_entity, relation_type, agent_scope)
);
CREATE INDEX idx_relations_from ON relations(from_entity, agent_scope);
CREATE INDEX idx_relations_scope ON relations(agent_scope);
```

### 1.4 Synonyms table
```sql
CREATE TABLE synonyms (
  term TEXT PRIMARY KEY,
  synonyms TEXT NOT NULL  -- pipe-separated list
);
-- seeded with technical terminology at bootstrap
```

## 2. Retrieval redesign — Pure Lexical Router

### 2.1 Query pipeline
```
query → tokenize → expand_synonyms → FTS5 search → metadata filter →
        entity boost → recency decay → deterministic sort → limit
```

### 2.2 FTS5 search (reemplaza dense cosine)
```python
def _fts_search(query, agent_scope, limit):
    """BM25 ranking nativo de SQLite FTS5."""
    fts_query = _build_fts_query(query)
    sql = """
      SELECT p.id, p.payload, fts.rank
      FROM points_fts fts
      JOIN points p ON p.rowid = fts.rowid
      WHERE points_fts MATCH ?
        AND p.agent_scope IN (?, 'shared', 'merged')
      ORDER BY fts.rank
      LIMIT ?
    """
    return db.execute(sql, (fts_query, agent_scope, limit * 2))
```

### 2.3 Synonym expansion
```python
SYNONYM_MAP = {
    "auth": "authentication|authorization|jwt|token|login|oauth",
    "database": "db|store|persist|sqlite|postgres",
    "error": "exception|crash|bug|failure|fault",
    "user": "account|profile|member|customer",
    # ES
    "autenticación": "auth|jwt|login|oauth",
    "base de datos": "db|sqlite|postgres",
}
```

### 2.4 Entity graph boost
Las entidades extraídas de la query y de los resultados ganan score extra:
```python
def _entity_boost(results, query_entities):
    """Entidades que aparecen tanto en query como en resultado → +0.2."""
    for r in results:
        result_entities = json.loads(r["payload"]).get("entities", [])
        overlap = len(set(query_entities) & set(result_entities))
        if overlap > 0:
            r["score"] += 0.2 * overlap
    return results
```

## 3. Consolidación léxica (L1→L2→L3→L4)

### 3.1 L1→L2: Agrupación episódica
Group L1 memories by (scope_type, scope_id) within time window.
Groups with >= 2 events → L2 episode with lexical summary.

### 3.2 L2→L3: Extracción de entidades
Extract CamelCase + UPPER_SNAKE entities from L2 episodes.
Upsert into entities table with mention_count.

### 3.3 L3→L4: Clustering por co-ocurrencia
Find entities appearing together in >= 3 L3 points.
Create L4 narrative + relations.

### 3.4 Removal of NO-OPs
- `_promote_l2_l3`: replace NO-OP with `consolidate_l2_to_l3`
- `_promote_l3_l4`: replace NO-OP with `consolidate_l3_to_l4`
- `dream()`: replace NO-OP with `consolidate_l3_to_l4` (deep mode)

## 4. Eliminar embedding.py completamente

### 4.1 Archivos a borrar
- `src/shared/embedding.py` (700 líneas)
- `src/shared/embedding_cache.py` (90 líneas)
- Referencias a `hash_vector` en `memory_db.py`
- Referencias a `bm25_tokenize` en retrieval y servers

### 4.2 Migración de datos existentes
Script `scripts/migrate_to_fts5.py`:
1. Lee puntos de `points`
2. Inserta contenido en `points_fts`
3. Extrae entidades → inserts en `entities`
4. Construye relations por co-ocurrencia
5. Preserva columna `vector` (ignorado en reads)

### 4.3 Config cleanup
- Remover `llm_model` de `Config`
- Remover campos `embedding_*` de `Config`
- Remover env vars EMBEDDING_* del .env.example
- Actualizar config/mcp.json template

## 5. Failure modes + adversarial

### 5.1 FTS5 corruption
- FTS5 out of sync → fallback to points scan, logged WARN
- Test: corrupt FTS5 entry → search still works

### 5.2 Synonym injection
- SQL metacharacters in expanded query → FTS5 parameterized, safe
- Test: synonym expansion with `'; DROP TABLE; --`

### 5.3 Entity scope violation
- Cross-scope entity via relations → engine filter on agent_scope
- Test: agent A's relations invisible to agent B

### 5.4 Consolidation infinite loop
- L1→L2 creates L2, but L2 doesn't feed L1 → no loop
- Idempotent: running twice produces identical results
- Test: run consolidation twice → same counts

### 5.5 Migration safety
- Idempotent migration (UPSERT entities by id)
- Original points table untouched
- Test: run migration twice → same entity count
