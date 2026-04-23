#!/bin/bash
# start-all.sh - Launcher unificado para el ecosistema de memoria

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_ROOT/embedding-server.log"

echo "🧠 Iniciando ecosistema de memoria..."

# 1. Levantar el servidor de embeddings si no está corriendo
if ! curl -s http://localhost:8080/health > /dev/null; then
    echo "🚀 Levantando servidor de embeddings (llama-server)..."
    # Rotamos el log (empezamos de cero para no acumular basura)
    echo "--- Start Session: $(date) ---" > "$LOG_FILE"
    
    # Usamos el script existente que ya tiene la lógica de búsqueda de modelos
    "$SCRIPT_DIR/start-embedding-server.sh"
    
    # Esperamos a que esté listo
    MAX_RETRIES=30
    COUNT=0
    while ! curl -s http://localhost:8080/health > /dev/null; do
        sleep 1
        COUNT=$((COUNT+1))
        if [ $COUNT -ge $MAX_RETRIES ]; then
            echo "❌ Error: El servidor de embeddings no arrancó a tiempo."
            exit 1
        fi
    done
    echo "✅ Servidor de embeddings listo."
else
    echo "✅ Servidor de embeddings ya está corriendo."
fi

# 2. Exportar variables de entorno para que el sistema sepa que tiene el backend rápido
export EMBEDDING_BACKEND="llama_server"
export EMBEDDING_SERVER_URL="http://localhost:8080"

echo "✨ Ecosistema listo. Podés usar Pi Agent o el Gateway ahora."
