# Proposal: E2E-audit-remediation

**Fecha:** 2026-09-07 · **Origen:** auditoría E2E completa (spawn real del servidor
unificado por stdio + protocolo JSON-RPC contra DB production-shaped)

## Problema

La auditoría E2E encontró **4 tools MCP rotas en producción con la suite 403/0
en verde** — la capa mockeada por los tests unitarios no ejercita el protocolo
real ni las DBs pre-existentes:

| ID | Severidad | Hallazgo | Causa raíz |
|----|-----------|----------|------------|
| P0-1 | CRITICAL | `L3_facts_add_memory` muerta al 100% | `vector = await None` residual (M6/M7) |
| P0-2 | CRITICAL | L2 conversaciones muerta (save/get/list) | `_ensure_db` solo inicializaba DBs vírgenes; en producción `memory.db` nace points-first → `threads` nunca se creaba |
| P0-3 | HIGH | `L2_search_conversations` muerta | mismo patrón `await None` |
| P0-4 | HIGH | Deletes dejaban contenido en `points_fts` | `_delete_one` no purgaba el índice (retención/privacy) |
| P0-5 | MEDIUM | Tokens alfanuméricos partidos en FTS query (`E2E…`→`eprotocolsmoke`, `OAuth2`→`oa`+`uth2`) | regex de `_build_fts5_query` infiel al tokenizador unicode61 |
| P1-A | MEDIUM | Env muertos de embeddings inyectados por generador/instaladores | residuos pre-M9 |
| P1-B | MEDIUM | Identidad strict sin desplegar; el flujo documentado ponía el token en ficheros | sin launcher Keychain |

## Cambios (capabilities)

- **modified** `storage`: delete sincroniza `points_fts` (purge con rowid capturado
  pre-delete; purga solo si el delete aterriza).
- **modified** `retrieval`: `_build_fts5_query` con rama alfanumérica fiel a
  unicode61 (underscore = separador, mínimo 3 chars).
- **skip_specs**: los fixes de `await None` y `_ensure_db` son correcciones de
  bugs que restauran el comportamiento ya especificado (STO/ISO existentes), no
  capacidades nuevas.

## Impacto de aislamiento

Ninguno negativo. `_delete_one` mantiene su filtro anti-TOCTOU por scope; la
purga FTS elimina datos (no filtra); el smoke de protocolo re-verifica el
aislamiento cross-tenant (OWNER ve, INTRUDER no). **G-ISOLATION re-firmado**
en GATE.md con la batería adversarial completa.

## Rollback

Revert de los commits `69196e7` (P0) y los de P1 en main; los fixes son
independientes entre sí.
