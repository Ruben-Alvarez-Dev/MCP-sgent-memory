# Proposal: obsidian-kb-pipeline

**Fecha:** 2026-09-07 · **Tipo:** integración crítica corregida (capacidad nueva `kb` + modified `HAR`)

## Problema verificado (evidencia, 2026-09-07)

El conocimiento capturado por MCP **NO llega al Obsidian real del usuario**:

1. El vault de Obsidian es `~/.obsidian-vaults/principal` (abierto, estructura
   Para: 00 Inbox, 20 Wiki, 30 Investigacion…). El sistema escribe en
   `data/vault/` — un directorio huérfano que nadie abre (`VAULT_PATH` env mal
   cableado; el default del código era `data/Lx-persistent`, otro huérfano).
2. `VaultManager` (`shared/vault_manager/`) implementa el flujo completo
   diseñado — Inbox → clasificación por tags → renombrado canónico
   `L3_<TIPO>_<ts>_<id>_ES.md` → espejo `_EN.md` → integrity — y está **muerto**:
   ninguna tool lo instancia.
3. Las tools `vault_*` de L3_decisions reimplementan escritura naive sin
   bilingüe, sin clasificación, sin el layout del KB.
4. No existe promoción conocimiento-acumulado→KB: los hechos L3 de alta
   importancia mueren en SQLite sin materializarse en la wiki.

## Objetivo

Que todo lo capturado por MCP tenga camino a la KB real:
- Las tools del vault pasan por `VaultManager` (resucitado) apuntando al vault
  de Obsidian (`MEMORY_OBSIDIAN_VAULT`).
- El conocimiento entra por `00 Inbox`-equivalente del namespace Memory/ y se
  clasifica con el flujo bilingüe existente.
- Los hechos L3 importantes se **promocionan** a notas wiki durante la
  consolidación (proceso MCP, no manual).
- Todo verificado E2E: MCP → fichero en el vault real con formato correcto.

## Principio de no-invasión (sobre el vault personal)

El vault `principal` es territorio del usuario: se escribe SOLO bajo
`Memory/` (namespace propio, estructura espejo del KB), jamás se tocan notas
propias del usuario, nunca se borra nada del vault. `integrity_check` se
ciñe al namespace Memory/.

## Capabilities

- **new** `kb`: promoción L3→wiki y clasificación bilingüe real (KB-01…KB-08).
- **modified** `HAR`: las tools del vault usan el arnés de config correcto
  (`MEMORY_OBSIDIAN_VAULT`), no `VAULT_PATH` heredado.

## Impacto de aislamiento

El vault de Obsidian es del usuario (no multi-tenant): las notas llevan
`agent_scope` en frontmatter como metadato; la UI/REST solo escribe bajo
`Memory/`. Sin exposición multi-tenant nueva. G-ISOLATION no cambia
(escrituras fuera del motor de recovery de agentes).

## Rollback

Env `MEMORY_OBSIDIAN_VAULT` vacío → comportamiento actual (data/vault) sin
tocar el vault personal. Revert del commit = desactivación limpia.
