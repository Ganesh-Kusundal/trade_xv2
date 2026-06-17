#!/bin/bash
# Smoke-test all tradex CLI commands and capture their first-line status.
# Usage: bash test_all_cli.sh 2>&1 | tee cli_smoke_results.txt

set +e

CMDS=(
  "help"
  "broker"
  "dashboard"
  "validate"
  "benchmark"
  "analytics"
  "compare"
  "quality-report"
  "instrument"
  "account"
  "holdings"
  "positions"
  "orders"
  "trades"
  "oms"
  "quote"
  "depth"
  "option-chain"
  "futures"
  "historical"
  "stream"
  "websocket"
  "events"
  "search"
  "instruments"
  "doctor"
  "load-test"
  "news"
  "journal"
  "views"
  "options-sync"
)

for c in "${CMDS[@]}"; do
  echo "==================================================="
  echo "[tradex $c]"
  echo "==================================================="
  ./tradex "$c" 2>&1 | tail -n 6
  echo
done
