# M9-Schema-Migration

## Problem
La columna `vector` permanece en el schema aunque ya no se usa:
- Insertions ignoran la columna (NULL implícito)
- SELECTs no la leen
- Persiste en el archivo .db como espacio desperdiciado
- Tests skippeados bloquean validación completa

## Why Now
M6+M7+M8 eliminaron todas las dependencias funcionales.
Es seguro limpiar el schema.

## Success Criteria
- [ ] Columna `vector` removida del CREATE TABLE
- [ ] Migración upward-compatible (fallback a dead column)
- [ ] 423 tests passing, 0 skipped
- [ ] README actualizado con arquitectura FTS5-first
- [ ] GATE_M9 firmado

## Risks
- DBs existentes tendrán columna huérfana (inofensiva)
- Migración ALTER TABLE DROP puede fallar en SQLite antiguo
- Algunos tests legacy pueden depender de columna
