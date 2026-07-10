#!/usr/bin/env bash
# scripts/validate_all.sh
#
# Run all architecture and code-quality checks locally.
# Usage: bash scripts/validate_all.sh
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

run_check() {
    local label="$1"
    shift
    echo -e "\n${YELLOW}── ${label} ──${NC}"
    if "$@"; then
        echo -e "${GREEN}✓ ${label} passed${NC}"
    else
        echo -e "${RED}✗ ${label} failed${NC}"
        FAILED=1
    fi
}

# ── 1. Exception hierarchy ────────────────────────────────────────
run_check "Exception hierarchy" \
    python scripts/architecture/check_exception_hierarchy.py

# ── 2. Architecture fitness tests ────────────────────────────────
run_check "Architecture tests" \
    python -m pytest tests/architecture/ -x -q --tb=short

# ── 3. Ruff lint ─────────────────────────────────────────────────
run_check "Ruff lint" \
    ruff check .

# ── 4. Ruff format check ────────────────────────────────────────
run_check "Ruff format" \
    ruff format --check .

# ── 5. Import smoke test ────────────────────────────────────────
run_check "Import smoke tests" \
    python -m pytest tests/architecture/test_imports.py -x -q --tb=short

# ── Summary ──────────────────────────────────────────────────────
echo ""
if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}All checks passed.${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed. See above for details.${NC}"
    exit 1
fi
