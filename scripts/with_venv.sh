#!/usr/bin/env bash
# Run a command with the project virtualenv Python (venv/).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${PROJECT_DIR}/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "Project venv not found at ${PYTHON}" >&2
  echo "Create with: python -m venv venv && venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi
exec "$PYTHON" "$@"
