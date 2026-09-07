# Proposal: two-tier-memory

**Fecha:** 2026-09-07 · **Tipo:** capacidad nueva `retention` + modified `storage`/`kb`

## Requisito del propietario (textual, interpretado)

Separar el **conocimiento del día a día** (que debe poder olvidarse) del
**conocimiento sensible/experiencial** (destilado de verdad, tecnologías,
investigación) que **nunca debe olvidarse**: es el producto de la experiencia y
la función delegada al sistema es **segundo cerebro-almacén** — los humanos
olvidamos y reutilizamos; el sistema complementa siendo fiel donde nosotros
somos flexibles.

## Fundamento científico (no es capricho: es consolidación)

La distinción reproduce la memoria humana real:
- **Memoria de trabajo/episódica**: capacidad limitada, decae sin refuerzo
  (curva de olvido de Ebbinghaus: R = e^(-t/S)).
- **Consolidación**: el contenido re-usado o importante se estabiliza en
  memoria de largo plazo (proceso activo, no automático).
- **Spaced repetition**: el recall ES refuerzo (ser recordado protege de
  olvidar).
- Y la pieza de diseño elegante: **la destilación hace seguro el olvido** —
  cuando una verdad está destilada en la KB (nota verificada), el apunte crudo
  puede expirar sin pérdida de conocimiento.

Hoy el sistema VIOLA esto: nada caduca (los efímeros se acumulan para siempre
y los hechos rotos "caducan" en silencio volviéndose falsos). Dos fallos
opuestos, misma raíz: ausencia de política de retención por clase.

## Objetivo

Dos clases de memoria con políticas diferenciales:

| | EFÍMERA (calle) | DURABLE (experiencia) |
|---|---|---|
| Origen | captura por defecto | destilación a la KB, o marca explícita |
| Decay | Ebbinghaus: importancia efectiva decae si no se recusa | NUNCA decae |
| Destino al expirar | archivo (traza) → borrado del índice vivo | solo quirúrgico con trace |
| Caducidad de verdad | n/a | bi-temporal: marcada inválida, nunca borrada |
| Olvidar | es una FEATURE (libera contexto) | es un INCIDENTE (requiere gate) |

## Capabilities

- **new** `retention`: clases, decay, reaper, archivo (TIER-01…08)
- **modified** `storage`: campos persistence/last_recalled/reinforce_count
- **modified** `kb` (KB-11): la destilación marca la fuente como archivable

## Impacto de aislamiento

El reaper solo toca memoria del propio agente (scope propio+shared según
identidad); el archivo conserva scope; durable jamás cruza sin approve trunk.
G-ISOLATION re-firmada.

## Rollback

Reaper flaggeado (`MEMORY_RETENTION_ENABLED=0`); los archivos son restaurables
(undo quirúrgico reutilizado).
