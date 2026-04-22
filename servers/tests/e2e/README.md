# E2E Test Framework — MCP Memory Server

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Test Runner  │───▶│ Instrumentation  │───▶│  Event Store    │
│ (scenarios)  │    │ (proxy layer)    │    │  (JSONL logs)   │
└──────────────┘    └────────┬─────────┘    └────────┬────────┘
                             │                       │
                      ┌──────▼──────┐         ┌──────▼────────┐
                      │  Assertions │         │  Web Dashboard│
                      │ (pass/fail) │         │  (real-time)  │
                      └─────────────┘         └───────────────┘
```

## Scenarios

Cada escenario simula un flujo real de trabajo de un agente de IA:

1. **Onboarding** — Agente se conecta, descubre tools, hace heartbeat
2. **Memory Ingest** — Guarda hechos, decisiones, episodios
3. **Semantic Retrieve** — Busca por significado, no keywords
4. **Conversation Thread** — Guarda y busca conversaciones
5. **Context Assembly** — Arma contexto para LLM con retrieval
6. **Reminders** — Sistema push/pull de recordatorios
7. **Domain Shift** — Detecta cambio de contexto
8. **Compliance** — Verifica reglas del proyecto
9. **Mem0 Semantic** — Hechos y preferencias de usuario
10. **Dream Cycle** — Consolidación y pattern detection

## Instrumentation

Cada llamada MCP se intercepta y se loggea:
- Timestamp (µs precision)
- Tool name, arguments
- Response status, latency
- Error traces completas
- Scenario context (qué test lo llamó)

Output: JSONL en `tests/e2e/logs/run-{timestamp}.jsonl`

## Dashboard

Server HTTP en `http://127.0.0.1:8080` que muestra:
- Métricas en tiempo real (total calls, avg latency, error rate)
- Timeline de eventos con colores por tipo
- Detalle por herramienta (usage count, success rate, p50/p99 latency)
- Flujo visual: ingest → store → retrieve → use
- Assertions pass/fail con stack traces
- Export de logs para análisis offline
