#!/usr/bin/env bash
# install/pull-models.sh — pull the 2026 model stack into Ollama (ADR-0006).
#
# Model downloads are ALWAYS explicit (adaptive-model-tier non-goal:
# "no automatic model downloads"). Run this by hand when provisioning
# a machine; the tier resolver degrades explicitly until models exist.
#
# Usage:
#   OLLAMA_URL=http://127.0.0.1:11434 ./install/pull-models.sh
#
# Requires: ollama CLI on PATH, curl, a running Ollama daemon.

set -euo pipefail

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

# Role→model matrix for tier T2 (see openspec/specs/model-stack/spec.md):
#   primary   qwen3.5:4b
#   small     qwen3.5:2b
#   embedding qwen3-embedding:0.6b
#   reranker  qwen3-reranker:0.6b (pulled once change `reranker-real` lands)
MODELS=(
  "qwen3.5:4b"
  "qwen3.5:2b"
  # If the official tag is not published in the Ollama library, use the
  # community GGUF build instead: dengcao/Qwen3-Embedding-0.6B
  "qwen3-embedding:0.6b"
  # "qwen3-reranker:0.6b"   # pending change `reranker-real` — do not pull yet
)

echo "==> Checking Ollama daemon at ${OLLAMA_URL}"
if ! curl -sf --max-time 5 "${OLLAMA_URL}/api/tags" > /dev/null; then
  echo "ERROR: Ollama is not reachable at ${OLLAMA_URL}. Start it first." >&2
  exit 1
fi

for model in "${MODELS[@]}"; do
  echo "==> Pulling ${model}"
  ollama pull "${model}"
done

echo "==> Verifying pulled models against ${OLLAMA_URL}/api/tags"
TAGS_JSON="$(curl -sf --max-time 5 "${OLLAMA_URL}/api/tags")"
MISSING=0
for model in "${MODELS[@]}"; do
  if echo "${TAGS_JSON}" | grep -q "\"${model}"; then
    echo "    ok: ${model}"
  else
    echo "    MISSING: ${model}" >&2
    MISSING=1
  fi
done

if [ "${MISSING}" -ne 0 ]; then
  echo "ERROR: some models did not appear in /api/tags after pull." >&2
  exit 1
fi

echo "==> Done. Re-probe the tier with: curl -s http://127.0.0.1:8890/api/model-tier"
