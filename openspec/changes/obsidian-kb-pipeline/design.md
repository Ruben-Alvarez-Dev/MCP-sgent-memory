# Design — obsidian-kb-pipeline

## 1. Cableado correcto (el triángulo roto → cerrado)

```
Hoy (roto):
  tools vault_* ──escritura naive──> data/vault/ (huérfano)
  VaultManager (bilingüe completo) ── código muerto
  Obsidian real (~/.obsidian-vaults/principal) ── sin conexión

Objetivo:
  tools vault_* ──> VaultManager ──> <principal>/Memory/  (KB viva en Obsidian)
  consolidación L3 ──promoción──> Memory/Wiki/
  hooks/inbox ──clasificación tags──> Memory/{Conocimiento,Decisiones,…} + espejo EN
```

## 2. Config

| Env | Valor propuesto | Rol |
|---|---|---|
| `MEMORY_OBSIDIAN_VAULT` | `~/.obsidian-vaults/principal` | destino real (KB-01); vacío = fallback legacy |
| `VAULT_PATH` | queda como legacy de tools L3 internas | deprecado progresivamente |
| `MEMORY_KB_NAMESPACE` | `Memory` (default) | subcarpeta propia dentro del vault |

Estructura dentro del vault: `Memory/{Inbox,Conocimiento,Decisiones,Episodios,
Entidades,Notas,People,Archive,Wiki}` + espejos EN (`knowledge`, `decisions`,
…). El VaultManager ya tiene los mapas ES↔EN.

## 3. Resurrección de VaultManager (cambios mínimos)

- Constructor acepta path externo (ya lo hace) — instanciado por las tools
  con `MEMORY_OBSIDIAN_VAULT`.
- `write_note_bilingual` ya genera ES+EN; se añade frontmatter de trazabilidad
  (`source: memory:<id>`, `agent_scope`, `created`) si no lo lleva.
- `process_inbox` ya clasifica por tags (mapa del README del KB) — respetar
  y testear contra la realidad del documento.

## 4. Promoción L3→wiki (KB-04)

En el ciclo de consolidación (L0_to_L4), tras promover: los hechos con
`importance ≥ 0.8` generan/actualizan nota wiki:

```
Memory/Wiki/<slug>.md
---
source: memory:<memory_id>
agent_scope: <scope>
created: <iso>
tags: [wiki, <mem_type>]
---
<content>

## Origen
[[Memory/Conocimiento/L3_KNOWLEDGE_…_ES]]
```

Idempotencia: índice `Memory/Wiki/.index.json` (memory_id → path+hash);
si el hash del contenido no cambió, no se reescribe.

## 5. Fallos y adversarios

| Amenaza | Defensa |
|---|---|
| Escribir fuera de `Memory/` | validación de ruta con resolve()+startswith (jail), test adversarial KB-08 |
| Vault no existe / no es vault (sin `.obsidian`) | warn al arrancar + fallback legacy; no crash |
| Duplicados por re-consolidación | índice idempotente KB-04 |
| Nota del usuario con nombre colisionado | prefijo de namespace + slug con timestamp |
| Vault en iCloud/latencias | escritura atómica (tmp+rename) |
| Traducción EN sin LLM | el sistema no inventa traducción: ES canonico, EN espejo con marcador `translation: pending` si no hay traductor — decisión explícita anti-alucinación |

## 6. Tareas serializadas (grupos orgánicos)

- **A — Cableado**: config + VaultManager resucitado + tools delegando (KB-01/02) · test jail
- **B — Flujo Inbox bilingüe** (KB-03) · test clasificación+espejo
- **C — Promoción L3→wiki** (KB-04/06) · índice idempotente · test
- **D — Integridad con alcance** (KB-05) + adversarial no-invasión (KB-08) · hash pre/post
- **E — E2E contra el vault real + GATE** (KB-07)
