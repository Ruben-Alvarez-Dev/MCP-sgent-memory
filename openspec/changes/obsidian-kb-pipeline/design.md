# Design — obsidian-kb-pipeline (v2, post-análisis del vault real)

## 0. Hallazgos que cambian el diseño (investigación del vault real)

- El vault `principal` es un **esqueleto Para recién creado y vacío** (0 notas
  en 00 Inbox/10 Diario/20 Wiki/30 Investigacion/50 Proyectos) — se construyó
  como DESTINO de este pipeline, no como territorio establecido a proteger.
- El flujo ya está diseñado por el usuario en su MOC (`🏠 Inicio.md`):
  **Capturas → 00 Inbox → refinado → 20 Wiki** ("lo que se concluye se
  refina: conocimiento estable → 20 Wiki").
- **Dataview instalado** → frontmatter bien formado = dashboards gratis.
- **Plantilla Wiki.md** define la epistemología: "destilado propio, no copia;
  lo que TÚ aprendiste: gotchas, configuraciones, lo que la doc no cuenta"
  con secciones fijas (Concepto en 3 líneas / Configuración que uso /
  Gotchas / Relacionadas) y frontmatter (tipo, verificado, tags[wiki]).

**Consecuencia arquitectónica**: el modelo correcto NO es "namespace cuarentena
Memory/" (el vault ES el destino) ni "integración invasiva" (rompería el flujo
Para). Es **respetar el flujo Para existente como interfaz**: la máquina
captura en la entrada del flujo (00 Inbox) y promociona borradores marcados a
20 Wiki; la denominación y refinado final son humanos — su epistemología
("destilado propio") lo exige.

## 1. Arquitectura final recomendada (v2)

## 1. Cableado correcto (el triángulo roto → cerrado)

```
Hoy (roto):
  tools vault_* ──escritura naive──> data/vault/ (huérfano)
  VaultManager (bilingüe completo) ── código muerto
  Obsidian real (~/.obsidian-vaults/principal) ── sin conexión

Objetivo (v2 — integrado con el Para del usuario):
  captura MCP ──> <principal>/00 Inbox/  (entrada al flujo Para, tags memoria)
  consolidación L3 (importance ≥0.8, ≥2 ciclos) ──> <principal>/20 Wiki/ (borrador-agente)
  humano refina ──> estado: verificado → wiki real (su epistemología)
```

## 2. Flujo y destino (v2 — integrado con el Para del usuario)

```
Agente (MCP)                    Vault del usuario (su flujo Para)
────────────                    ─────────────────────────────────
captura (L0/L3) ──────────────> 00 Inbox/<tipo>-<slug>.md
                                  tags: [memoria, origin/agent, …]
                                  frontmatter: source, agent, created,
                                  importance, estado: captura
       │
consolidación (importance ≥ 0.8
y superviviente de ≥2 ciclos) ─> 20 Wiki/<slug>.md  (BORRADOR AGENTE)
                                  sigue la plantilla Wiki.md del usuario
                                  (Concepto en 3 líneas / Gotchas / …)
                                  estado: borrador-agente, tags: [wiki, memoria]
       │
humano refina (destilado propio) ─> estado: verificado → wiki REAL

Diario / Investigacion / Proyectos / _Adjuntos: TERRITORIO HUMANO —
el agente no escribe jamás (fase 2 opcional: indexación read-only
para recall del agente, nunca escritura).
```

| Env | Valor | Rol |
|---|---|---|
| `MEMORY_OBSIDIAN_VAULT` | `~/.obsidian-vaults/principal` | destino real |
| `MEMORY_KB_INBOX` | `00 Inbox` | entrada al flujo Para del usuario |
| `MEMORY_KB_WIKI` | `20 Wiki` | destino de borradores promocionados |
| `MEMORY_KB_IMPORTANCE` | `0.8` | umbral de promoción automática |
| `MEMORY_KB_MIN_CYCLES` | `2` | supervivencia mínima antes de promocionar |
| `MEMORY_API_DISABLED`… | — | el resto de envs sin cambios |

Bilingüe ES/EN: **desactivado para el vault personal** (lector único, en
español; el espejo EN era del KB de sistema). La traducción, si algún día se
quiere, la hace el propio agente vía tool — no un proceso local.

## 2b. Notas del agente: formato (conforma con la plantilla Wiki.md del usuario)

Captura (00 Inbox):
```yaml
---
tipo: captura
source: memory:<memory_id>
agent: pi-agent
created: 2026-09-07
importance: 0.85
estado: captura
tags: [memoria, origin/agent, <mem_type>]
---
```

Borrador de wiki (20 Wiki):
```yaml
---
tipo: wiki
estado: borrador-agente
source: memory:<memory_id>
verificado: false
created: 2026-09-07
tags: [wiki, memoria]
---
# <título destilado>

## Concepto en 3 líneas
<hecho(s) fundidos, lenguaje llano — estructural, no generado>

## Gotchas y cosas que la doc no cuenta
<hechos tipo bug_fix/config agrupados>

## Relacionadas
- [[<entidad>]] …
```

El contenido del borrador se ENSAMBLA estructuralmente desde hechos
(agrupación por similitud de tags/entidades, frases literales ya capturadas) —
NO se genera prosa con modelos (restricción dura memory-zero). El refinado a
"destilado propio" es humano: para eso está `estado: borrador-agente`.

## 2c. Dataview (regalo al MOC del usuario)

Bloques listos para 🏠 Inicio.md:
```dataview
TABLE source, importance, created FROM "00 Inbox"
WHERE contains(tags, "memoria") SORT created DESC LIMIT 10
```
```dataview
TABLE verificado, created FROM "20 Wiki"
WHERE estado = "borrador-agente" SORT created DESC
```
```dataview
LIST FROM #memoria WHERE estado = "verificado"
```

## 2d. Índice de trazabilidad (idempotencia + moves humanos)

`00 Inbox/.memory-index.json` — memory_id → {path, sha256(contenido), estado}.
Si el humano MUEVE una nota (p.ej. la promueve a mano a otra carpeta), el
frontmatter `source:` sobrevive al move → la re-resolución por escaneo
(reconcile() en cada consolidación) actualiza el índice sin duplicar.
Las carpetas del vault son del usuario: mover = su forma de curar, el sistema
lo respeta y re-rastrea.

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
20 Wiki/<slug>.md
---
source: memory:<memory_id>
agent_scope: <scope>
created: <iso>
tags: [wiki, <mem_type>]
---
<content>

## Origen
[[00 Inbox/<captura-origen>]]
```

Idempotencia: índice `00 Inbox/.memory-index.json` (memory_id → path+hash);
si el hash del contenido no cambió, no se reescribe.

## 5. Fallos y adversarios

| Amenaza | Defensa |
|---|---|
| Escribir fuera de 00 Inbox / 20 Wiki (territorio humano) | jail resolve()+startswith sobre las dos rutas permitidas; test adversarial KB-08 |
| Vault no existe / no es vault (sin `.obsidian`) | warn al arrancar + fallback legacy; no crash |
| Duplicados por re-consolidación | índice idempotente KB-04 |
| Nota del usuario con nombre colisionado | prefijo de namespace + slug con timestamp |
| Vault en iCloud/latencias | escritura atómica (tmp+rename) |
| Traducción EN sin LLM | el sistema no inventa traducción: ES canonico, EN espejo con marcador `translation: pending` si no hay traductor — decisión explícita anti-alucinación |

## 6. Tareas serializadas (grupos orgánicos)

- **A — Cableado**: config + VaultManager resucitado + tools delegando (KB-01/02) · test jail
- **B — Flujo de captura e inbox** (KB-03) · test captura→00 Inbox con frontmatter Dataview
- **C — Promoción L3→borrador de wiki** (KB-04/06) · índice idempotente + reconcile ante moves humanos · test
- **D — Integridad con alcance** (KB-05) + adversarial no-invasión (KB-08) · hash pre/post
- **E — E2E contra el vault real + GATE** (KB-07)
