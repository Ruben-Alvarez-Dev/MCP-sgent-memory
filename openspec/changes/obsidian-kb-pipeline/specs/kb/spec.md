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

## KB-03 — Captura en el inbox del usuario con frontmatter Dataview

**Given** un hecho capturado por MCP con importance/importance registrada,
**When** se materializa la captura,
**Then** aparece como nota en `00 Inbox/` con frontmatter Dataview-compatible
(source: memory:<id>, agent, created, importance, estado: captura,
tags: [memoria, origin/agent, <mem_type>]) y título destilado del contenido.
Test: `test_kb_capture_lands_in_inbox_with_frontmatter`

## KB-04 — Promoción a BORRADOR de wiki (supervisada, no invasiva)

**Given** un hecho L3 con `importance ≥ 0.8` superviviente de ≥2 ciclos de
consolidación,
**When** el ciclo termina,
**Then** se materializa en `20 Wiki/` como borrador que CONFORMA con la
plantilla Wiki.md del usuario (secciones Concepto/Gotchas/Relacionadas),
frontmatter `estado: borrador-agente, verificado: false`, ensamblado
estructuralmente desde hechos (sin prosa generada); el refinado a
"destilado propio" (estado: verificado) es humano. Re-consolidar no duplica.
Test: `test_kb_promotion_idempotent_and_template_conformant`

## KB-05 — Integridad con alcance al flujo del agente

**Given** el vault contiene notas del usuario y notas del agente,
**When** `integrity_check` corre,
**Then** solo audita las notas con `tags: [memoria]` / `origin/agent`
(frontmatter válido, source resoluble, enlaces internos del agente) y NUNCA
reporta ni toca las notas del humano.
Test: `test_kb_integrity_scoped_to_agent_notes`

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
