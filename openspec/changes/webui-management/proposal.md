# Proposal: webui-management

**Fecha:** 2026-09-07 · **Tipo:** nueva capacidad (superficie humana de administración)

## Problema

La memoria solo es gestionable vía MCP tools (para agentes) o sqlite3/curl
(para humanos). No existe forma cómoda y segura de: explorar qué sabe el
sistema, corregir/eliminar memorias erróneas, revisar decisiones del vault,
aprobar promociones al trunk, rotar credenciales de agentes, o ver la
telemetría de adopción/latencia — hoy repartida entre `metrics.py`, sqlite3 y
`grep`.

## Objetivo

UI web de administración (humano-admin) sobre TODO el sistema: dashboard de
salud y adopción, explorador de memorias con búsqueda FTS y edición/borrado,
decisiones del vault, conversaciones, sesiones Lx, reminders, cola de
aprobación trunk, registry de agentes y métricas.

## No-objetivos

- No sustituye al MCP (vía de los agentes): la UI es la vía del humano.
- No expone escritura para agentes (ellos siguen por MCP con identidad).
- Sin dependencias nuevas: Starlette + uvicorn (ya en venv) + front vanilla.

## Capabilities

- **new** `webui`: API JSON de administración + SPA estática.
- **modified** `storage`: solo lectura salvo operaciones ya existentes
  (delete/purge reutilizan `MemoryDB._delete_one` con su purga FTS).

## Impacto de aislamiento

La UI es **humano-admin**: ve todos los scopes (equivalente
a abrir la DB con sqlite3). Bind localhost-only por defecto + token opcional
(reutiliza `MEMORY_HTTP_TOKEN`); modo solo-lectura (`MEMORY_UI_READONLY=1`).
Ninguna escritura cruza scopes: el aislamiento de agentes no cambia.
Re-firma G-ISOLATION en el gate (lecturas engine-level, sin exponer filtration).

## Rollback

Servicio autónomo: `git revert` + no arrancar el daemon. No toca el camino de
los agentes (MCP) ni el schema.
