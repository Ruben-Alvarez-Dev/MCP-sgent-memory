# PLAN MAESTRO — Spec-Driven Fix Program

## Principios
1. **Spec primero**: cada fix tiene spec → implementación → verificación
2. **Critical antes que High**: ordenar por severidad
3. **No regression**: cada fix incluye test de regresión
4. **Un commit por spec**: atómico, revertible

---

## Grupos de Actuación

### Grupo A: Seguridad Crítica (SEC-C1, SEC-C2)
### Grupo B: Integridad de Datos (DAT-C1, DAT-C2, REL-C2)
### Grupo C: Fiabilidad & Resilencia (REL-C1, REL-H1..H4)
### Grupo D: Rendimiento (PER-H1, PER-H2)
### Grupo E: Calidad de Código (QUA-H1, QUA-H2, QUA-H3)
### Grupo F: Observabilidad (OBS-H1..H4)
### Grupo G: API & Config (API-H1, API-H2, config drift)
### Grupo H: Documentación (README vs realidad)

---

## Orden de ejecución (prioridad)

```
Grupo A (Seguridad)     ← Primero: vulnerabilidades activas
Grupo B (Integridad)    ← Segundo: datos corruptos se acumulan
Grupo C (Fiabilidad)    ← Tercero: sistema cae silenciosamente
Grupo D (Rendimiento)   ← Cuarto: UX degradada
Grupo E (Calidad)       ← Quinto: deuda técnica
Grupo F (Observabilidad)← Sexto: visibilidad para debug
Grupo G (API/Config)    ← Séptimo: sostenibilidad
Grupo H (Docs)          ← Último: documentar lo construido
```

Ver archivos 05-A por grupo para specs detalladas.
