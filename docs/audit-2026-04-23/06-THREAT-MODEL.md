# Threat Model — MCP-agent-memory

## Trust Boundaries

```
┌─────────────────────────────────────────────────────┐
│  TRUSTED ZONE (localhost, single-user Mac)          │
│                                                      │
│  ┌──────────┐    stdio    ┌──────────────┐          │
│  │  Pi / LLM │ ────────── │  MCP Gateway │          │
│  │  (Claude) │            │  (1MCP :3051)│          │
│  └──────────┘            └──────┬───────┘          │
│                                  │                   │
│                    ┌─────────────┼────────────┐     │
│                    │             │             │     │
│              ┌─────▼──┐  ┌──────▼──┐  ┌──────▼──┐  │
│              │ Qdrant  │  │ llama-  │  │ Engram  │  │
│              │ :6333   │  │ server  │  │ (files) │  │
│              │ (HTTP)  │  │ :8082   │  │          │  │
│              └─────────┘  └─────────┘  └─────────┘  │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Amenazas identificadas

### T1: LLM Prompt Injection → File Read/Write
- **Vector**: LLM recibe prompt malicioso que causa tool call con path traversal
- **Ejemplo**: `get_decision(file_path="/etc/passwd")` — ACTUALMENTE FUNCIONA
- **Mitigación**: SPEC-A1 (path confinement), SPEC-A2 (filename sanitize)
- **Severidad**: CRITICAL
- **Estado**: No mitigado

### T2: Qdrant Data Exfiltration
- **Vector**: Cualquier proceso local puede leer/escribir Qdrant via HTTP :6333
- **Ejemplo**: `curl http://localhost:6333/collections/automem/points/scroll` lee todas las memorias
- **Mitigación**: Ninguna actualmente. Qdrant no tiene auth.
- **Severidad**: MEDIUM (requiere acceso local)
- **Estado**: Aceptado (localhost-only, single-user)

### T3: Embedding Poisoning
- **Vector**: Inserción de vectores vacíos o corruptos contamina búsquedas futuras
- **Ejemplo**: `_embed()` falla, retorna `[]`, se almacena en Qdrant
- **Mitigación**: SPEC-B1 (rechazar vectores vacíos), SPEC-B2 (safe_embed)
- **Severidad**: HIGH
- **Estado**: No mitigado

### T4: Denial of Service (Memory Exhaustion)
- **Vector**: LLM llama memorize() en loop → Qdrant crece sin límite
- **Ejemplo**: 100K memorias insertadas, cada una con vector 1024d
- **Mitigación**: SPEC-B4 (purga periódica), rate limiting (SEC-L1)
- **Severidad**: LOW
- **Estado**: Parcialmente mitigado por watchdog

### T5: Secret Exposure via .env
- **Vector**: config/.env world-readable (644)
- **Ejemplo**: Otro usuario en la máquina lee API keys (actualmente no hay, pero futuro)
- **Mitigación**: SPEC-A4 (chmod 600)
- **Severidad**: LOW (actualmente no hay secrets reales)
- **Estado**: No mitigado

## Supuestos de seguridad

1. **Single-user machine**: Solo Ruben usa este Mac
2. **Trusted LLM**: El LLM (Claude) no es adversarial — no inyecta paths maliciosos intencionalmente
3. **Localhost only**: Qdrant y llama-server solo escuchan en 127.0.0.1
4. **No internet exposure**: El gateway MCP es stdio, no HTTP
5. **Trusted filesystem**: No hay otros procesos maliciosos en la máquina

## Recomendaciones

1. **Inmediato**: SPEC-A1 + SPEC-A2 (path confinement) — elimina T1
2. **Corto plazo**: SPEC-A4 (chmod 600) — elimina T5
3. **Medio plazo**: SPEC-B1 + SPEC-B2 (vector validation) — elimina T3
4. **Largo plazo**: Qdrant API key si se expone a red
