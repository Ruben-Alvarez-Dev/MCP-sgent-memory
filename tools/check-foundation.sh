#!/bin/sh
set -eu

EXPECTED_UV_VERSION="0.11.28"
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
ACTUAL_UV_VERSION=$(uv --version | awk '{print $2}')

if [ "$ACTUAL_UV_VERSION" != "$EXPECTED_UV_VERSION" ]; then
  echo "Expected uv $EXPECTED_UV_VERSION, found $ACTUAL_UV_VERSION" >&2
  exit 1
fi

cd "$REPOSITORY_ROOT"

uv sync --frozen --extra dev
uv run --frozen --extra dev pytest tests/contracts -q
uv run --frozen --extra dev ruff check tests/contracts
uv run --frozen --extra dev ruff format --check tests/contracts
