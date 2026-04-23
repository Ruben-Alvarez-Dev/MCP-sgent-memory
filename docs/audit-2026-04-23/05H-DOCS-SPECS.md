# Grupo H — Documentación

## Especificaciones

### SPEC-H1: Corregir README vs Realidad

**ID auditoría**: Múltiples
**Severidad**: MEDIUM

**Discrepancias a corregir**:

| README | Realidad | Fix |
|---|---|---|
| "51 tools" | 50 tools | Contar y actualizar |
| "One-liner install" | No copia scripts/, no crea LaunchAgents completos | Documentar pasos post-install |
| "Automatic dream-cycle" | Requiere llamada manual (heartbeat, dream) | Aclarar que es "triggered" no "scheduled" |
| No documenta watchdog.sh | Existe y funciona | Añadir sección "Services & Daemons" |
| No documenta lifecycle.sh | Existe y funciona | Añadir sección "Lifecycle Management" |
| No documenta health check | shared/health.py | Añadir sección "Health Monitoring" |
| "Private repository" | Público | Eliminar o actualizar badge |

**Criterio de aceptación**:
- [ ] Tool count verificado y correcto
- [ ] Post-install steps documentados
- [ ] Arquitectura de servicios documentada (launchd, watchdog, lifecycle)
- [ ] Dream cycle documentado como "triggered" no "automatic"

---

### SPEC-H2: Añadir sección de arquitectura de datos

**Severidad**: LOW

**Spec**: Documentar:

1. Flujo de datos L0 → L1 → L2 → L3 → L4 con condiciones de promoción
2. Schema de cada payload (MemoryItem, ThreadMessage, etc.)
3. Política de retención por layer
4. Qué se embebe vs qué se almacena (SPEC-D3)

---

### SPEC-H3: Añadir sección de troubleshooting

**Severidad**: LOW

**Spec**: Documentar:

1. "Qdrant connection refused" → verificar launchd, puerto 6333
2. "Embedding timeout" → verificar llama-server, modelo descargado
3. "Collection not found" → reiniciar gateway para auto-init
4. "Empty search results" → verificar dim=1024, colección tiene puntos
5. LaunchAgent debugging: `launchctl print gui/$(id -u)/com.agent-memory.*`
6. Log locations: `~/.memory/*.log`, `/tmp/llama-*.log`
