#!/bin/sh
set -eu

STATE_ROOT="${TRADEX_STATE_ROOT:-/var/lib/tradex/state}"
LAKE_ROOT="${TRADEX_DATA_ROOT:-/app/data/lake}"

mkdir -p "${STATE_ROOT}/session-recordings" "${LAKE_ROOT}"

cd /app
exec python scripts/run_api_server.py
