# Specs — kb (capacidad nueva)

## KB-01 — Destino real configurable

**Given** `MEMORY_OBSIDIAN_VAULT` apunta al vault de Obsidian del usuario,
**When** cualquier tool del vault escribe,
**Then** el fichero aterriza bajo `<vault>/Memory/…` (namespace propio) y
NUNCA fuera de él. Sin env → fallback al comportamiento actual (fail-safe).
Test: `test_kb_writes_under_memory_namespace`

## KB-02 — Tools del vault pasan por VaultManager

**Given** las tools `vault_write/process_inbox/integrity_check/list/read`,
**When** se invocan,
**Then** delegan en `VaultManager` (resucitado) — clasificación, renombrado
canónico y sanidad idénticos al flujo documentado en el README del KB.
Test: `test_kb_tools_use_vault_manager`

## KB-03 — Flujo Inbox bilingüe real

**Given** una nota en `Memory/Inbox/` con tag `#conocimiento` en español,
**When** `process_inbox` corre,
**Then** la nota se renombra a `L3_KNOWLEDGE_<ts>_<id>_ES.md` en
`Memory/Conocimiento/` y se crea el espejo `…_EN.md` traducido en la
estructura EN equivalente.
Test: `test_kb_inbox_classification_bilingual`

## KB-04 — Promoción L3→wiki durante consolidación

**Given** un hecho L3 con `importance ≥ 0.8` (o marcado `promote=true`) que
sobrevive a un ciclo de consolidación,
**When** el ciclo termina,
**Then** se materializa como nota wiki en `Memory/Wiki/` con frontmatter
(source: memory_id, scope, created, tags), enlace `[[…]]` a su origen y
marcador idempotente (re-consolidar no duplica notas).
Test: `test_kb_promotion_idempotent`

## KB-05 — Integridad con alcance al namespace

**Given** el vault personal contiene notas propias del usuario,
**When** `integrity_check` corre,
**Then** solo audita `Memory/` (formato frontmatter, enlaces rotos internos,
espejos ES/EN sincronizados) y NUNCA reporta ni toca notas del usuario.
Test: `test_kb_integrity_scoped_to_memory_namespace`

## KB-06 — Trazabilidad bidireccional

**Given** una nota de la KB derivada de una memoria,
**When** se consulta la memoria (por memory_id) o la nota (por frontmatter
`source`),
**Then** ambas direcciones resuelven (memoria→nota, nota→memoria) — vía
campo `source: memory:<id>` en frontmatter y búsqueda.
Test: `test_kb_bidirectional_trace`

## KB-07 — Verificación E2E del pipeline

**Given** el flujo completo (captura MCP → L3 → promoción → vault),
**When** se ejecuta el test E2E,
**Then** el fichero existe en el vault REAL con frontmatter correcto,
espejo EN, y el integrity del namespace pasa.
Test: `test_kb_pipeline_end_to_end`

## KB-08 — No invasión verificada (adversarial)

**Given** notas propias del usuario en el vault,
**When** se ejecutan todas las operaciones del KB,
**Then** sus ficheros quedan byte-a-byte intactos (hash pre/post).
Test: `test_kb_never_touches_user_notes`
