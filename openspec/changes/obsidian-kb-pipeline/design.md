# Design — obsidian-kb-pipeline (v3: refinería autónoma)

## 0. Hallazgos que cambiaron el diseño (investigación del vault real)

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

**Decisión del usuario**: el sistema se AUTOGESTIONA — sin promociones
manuales. La destilación y la prosa profesional corren vía perfiles agénticos
(LLM del harness), nunca modelos locales (restricción dura memory-zero).

## 1. Arquitectura final

```
Agente (MCP)                    Vault del usuario (su flujo Para)
────────────                    ─────────────────────────────────
captura (L0/L3) ──────────────> 00 Inbox/<tipo>-<slug>.md
                                  estado: captura · tags: [memoria, origin/agent]
        │
consolidación: importance ≥ 0.8
+ superviviente ≥2 ciclos ──────> 20 Wiki/Borradores-agente/<slug>.md
                                  estado: borrador-agente (plantilla Wiki.md)
        │
kb-editor (perfil agéntico:
pi -p, LLM de plan) ───────────> estado: pulido-agente
                                  prosa profesional, hechos citados
        │
humano (OPCIONAL) ─────────────> estado: verificado (destilado propio)

Diario · Investigacion · Proyectos · _Adjuntos: TERRITORIO HUMANO —
jamás se escribe (fase 2 opcional: indexación read-only para recall).
```

**Cumplimiento de la restricción memory-zero**: la prosa la escribe el LLM del
agente vía harness CLI headless (`pi -p`), jamás un modelo local. Los pasos 1-2
son 100% deterministas (plantilla + hechos literales); el paso 3 solo REESCRIBE
prosa sobre hechos ya citados (grounding) con gate de cobertura de citas.

## 2. Config

| Env | Valor | Rol |
|---|---|---|
| `MEMORY_OBSIDIAN_VAULT` | `~/.obsidian-vaults/principal` | destino real; vacío = fallback legacy |
| `MEMORY_KB_INBOX` | `00 Inbox` | carpeta de capturas (flujo Para del usuario) |
| `MEMORY_KB_WIKI` | `20 Wiki/Borradores-agente` | destino de borradores |
| `MEMORY_KB_IMPORTANCE` | `0.8` | umbral de promoción |
| `MEMORY_KB_MIN_AGE_DAYS` | `1` | supervivencia mínima antes de promover |
| `MEMORY_KB_MAX_PER_RUN` | `10` | techo de escrituras por pasada del editor |

## 3. Formato de notas (conforma con la plantilla Wiki.md del usuario)

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

Borrador (20 Wiki/Borradores-agente):
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
<hecho(s) fundidos>

## Gotchas y cosas que la doc no cuenta
<hechos tipo bug_fix/config agrupados>

## Relacionadas
- [[<entidad>]]
```

El borrador inicial lo ensambla el motor ESTRUCTURALMENTE desde hechos
(agrupación por entidades/tags, frases literales ya capturadas) — sin prosa
generada. El editor agéntico reescribe la prosa con calidad profesional SIN
alterar frontmatter ni hechos, y sube a `estado: pulido-agente`.

## 4. Dataview (regalo al MOC del usuario)

```dataview
TABLE source, importance, created FROM "00 Inbox"
WHERE contains(tags, "memoria") SORT created DESC LIMIT 10
```
```dataview
TABLE estado, created FROM "20 Wiki"
WHERE contains(tags, "memoria") SORT created DESC
```

## 5. Índice de trazabilidad (idempotencia + moves humanos)

`00 Inbox/.memory-index.json` — memory_id → {path, sha256, estado}. Si el
humano MUEVE una nota, el frontmatter `source:` sobrevive → `reconcile()`
(re-escaneo en cada pasada) actualiza el índice sin duplicar. Mover = su forma
de curar; el sistema lo respeta y re-rastrea.

## 6. Refinería autónoma — el editor agéntico

`scripts/kb-editor.sh` → `pi -p "$(cat prompts/kb-editor.md)"` ejecutado en el
cwd del vault. El prompt (perfil agéntico kb-editor) instruye:
1. Listar `20 Wiki/Borradores-agente/*.md` con `estado: borrador-agente`
2. Para cada uno (tope `MEMORY_KB_MAX_PER_RUN`): reescribir la prosa con
   calidad profesional MANTENIENDO los hechos EXACTOS y el frontmatter;
   subir estado a `pulido-agente`
3. Nunca tocar ficheros fuera de esa carpeta ni notas sin tag `memoria`

Agendado: launchd/cron tras cada ventana de consolidación, o invocado por el
agente en sesión. Idempotente: solo procesa borradores nuevos.

## 7. Estados de una nota de conocimiento

| estado | quién | significado |
|---|---|---|
| captura | engine | aterrizada en 00 Inbox |
| borrador-agente | engine | promovida a 20 Wiki con plantilla |
| pulido-agente | editor agéntico | prosa profesional, hechos citados |
| verificado | humano (opcional) | destilado propio — el sistema no lo requiere |

## 8. Gate de calidad del editor (KB-10)

Secciones de plantilla presentes · todo `source:` citado existe en la DB ·
sin duplicados por slug · markdown básico válido · los hechos del texto deben
mapear a memory_ids fuente (cobertura de citas). Fallo → la nota vuelve a
`borrador-agente` y se registra.

## 9. Modos de fallo y adversarios

| Amenaza | Defensa |
|---|---|
| Alucinación del editor | grounding: solo cita memory_ids del cluster; gate de cobertura de citas |
| Editor toca notas humanas | prompt + jail de carpeta; test hash pre/post |
| Doble pulido / carreras | estados + lock por slug; idempotente |
| Quema de cuota LLM | cola acotada por run; solo borradores nuevos |
| CLI headless ausente | fallback: los borradores deterministas ya son válidos sin pulir |
| Vault sin `.obsidian` / inexistente | warn + fallback legacy; no crash |
| Escribir fuera de Inbox/Wiki | jail resolve()+startswith; adversarial KB-08 |
| Duplicados por re-consolidación | índice idempotente + reconcile ante moves |
| Escrituras parciales | tmp+rename atómico |

## 10. Grupos de implementación (serializados)

- **A — Cableado**: config + KBEngine (`shared/kb.py`): capture_to_inbox,
  candidates, write_wiki_draft, promote_pending, reconcile, índice idempotente
  (KB-01/03/04/06)
- **B — No-invasión**: jail de rutas + adversarial hash pre/post (KB-05/08)
- **C — Editor agéntico**: prompts/kb-editor.md + scripts/kb-editor.sh + gate
  de calidad (KB-09/10)
- **D — Integración**: hook en consolidación + tools del vault delegando +
  deprecación de data/vault y data/Lx-persistent (E.2)
- **E — E2E contra el vault real + GATE** (KB-07)
