#!/bin/bash
# kb-editor.sh — Perfil agéntico de destilación (refinería de la KB).
#
# Drena la cola de borradores (20 Wiki/Borradores-agente/) reescribiendo la
# prosa con calidad profesional vía el LLM del agente (pi -p, headless).
# Idempotente: solo procesa notas con estado: borrador-agente.
#
# Agenda (ejemplo launchd/cron, tras cada ventana de consolidación):
#   */30 * * * * /Users/manu/.mcp-agent-memory/scripts/kb-editor.sh >> ~/.memory/kb-editor.log 2>&1
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="${MEMORY_OBSIDIAN_VAULT:-$HOME/.obsidian-vaults/principal}"
MAX="${MEMORY_KB_MAX_PER_RUN:-10}"
PI_BIN="${PI_BIN:-$(command -v pi || echo /usr/local/bin/pi)}"
PI_ARGS+=( -p )
[ -n "${PI_PROVIDER:-}" ] && PI_ARGS+=( --provider "$PI_PROVIDER" )
[ -n "${PI_MODEL:-}" ] && PI_ARGS+=( --model "$PI_MODEL" )

PENDIENTES=$(grep -rl "estado: borrador-agente" "$VAULT/20 Wiki/Borradores-agente/" 2>/dev/null | wc -l | tr -d ' ')
if [ "$PENDIENTES" = "0" ]; then
    echo "[$(date '+%F %T')] kb-editor: sin borradores pendientes"
    exit 0
fi
if [ "$PENDIENTES" -gt "$MAX" ]; then
    echo "[$(date '+%F %T')] kb-editor: $PENDIENTES pendientes > tope $MAX — procesando solo $MAX (el resto en la siguiente pasada)"
fi

PROMPT="$(cat "$REPO/prompts/kb-editor.md")

---
Ejecución headless: trabajas sobre ESTE vault (cwd actual). Máximo $MAX
borradores en esta pasada. Al terminar, devuelve el resumen en el formato
indicado en tus instrucciones."

echo "[$(date '+%F %T')] kb-editor: $PENDIENTES borradores pendientes, procesando..."
cd "$VAULT"
exec "$PI_BIN" "${PI_ARGS[@]}" "$PROMPT"
