#!/usr/bin/env bash
# Run mutation tests with incremental approach
#
# This script runs mutmut on critical modules and enforces a 90% kill rate.
# Designed to run nightly (not on every PR) to avoid slow CI.
#
# Usage:
#   ./scripts/run_mutation_tests.sh
#   ./scripts/run_mutation_tests.sh --module brokers/common/broker_port.py

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

PYTHON="${PROJECT_DIR}/venv/bin/python"

# Check if venv exists
if [ ! -x "$PYTHON" ]; then
    echo "✗ Project venv not found at ${PYTHON}"
    echo "ℹ Run: python -m venv venv && venv/bin/pip install -e '.[dev]'"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

echo_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

echo_warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

echo_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Default modules to test
MODULES_TO_TEST=(
    "brokers/common/broker_port.py"
    "domain/entities/order.py"
    "application/oms/risk_manager.py"
)

# Parse command line arguments
if [ "$1" = "--module" ] && [ -n "$2" ]; then
    MODULES_TO_TEST=("$2")
    echo_info "Testing single module: $2"
fi

# Phase 1: Quick mutation test on critical modules only
echo_info "Running quick mutation test on critical modules..."
echo_info "Target mutation score: 90%"
echo ""

TOTAL_KILLED=0
TOTAL_SURVIVED=0
TOTAL_MODULES=${#MODULES_TO_TEST[@]}
CURRENT_MODULE=0

for module in "${MODULES_TO_TEST[@]}"; do
    CURRENT_MODULE=$((CURRENT_MODULE + 1))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo_info "Testing module [$CURRENT_MODULE/$TOTAL_MODULES]: $module"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Check if module exists
    if [ ! -f "$module" ]; then
        echo_warn "Module not found: $module (skipping)"
        continue
    fi
    
    # Run mutmut on single module
    echo_info "Running mutmut..."
    "$PYTHON" -m mutmut run --paths-to-mutate "$module" --test-runner "pytest tests/ -x -q" 2>&1 || true
    
    # Get results
    echo_info "Collecting results..."
    "$PYTHON" -m mutmut results > /tmp/mutmut_results_${CURRENT_MODULE}.txt 2>&1 || true
    
    # Display results
    cat /tmp/mutmut_results_${CURRENT_MODULE}.txt
    
    # Parse results (simplified - adjust based on actual mutmut output format)
    KILLED=$(grep -oP "Killed\s*:\s*\K\d+" /tmp/mutmut_results_${CURRENT_MODULE}.txt || echo 0)
    SURVIVED=$(grep -oP "Survived\s*:\s*\K\d+" /tmp/mutmut_results_${CURRENT_MODULE}.txt || echo 0)
    
    TOTAL_KILLED=$((TOTAL_KILLED + KILLED))
    TOTAL_SURVIVED=$((TOTAL_SURVIVED + SURVIVED))
    
    echo ""
    echo_info "Module results: Killed=$KILLED, Survived=$SURVIVED"
done

# Calculate overall score
TOTAL_MUTANTS=$((TOTAL_KILLED + TOTAL_SURVIVED))

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo_info "Overall Mutation Testing Results"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $TOTAL_MUTANTS -gt 0 ]; then
    SCORE=$((TOTAL_KILLED * 100 / TOTAL_MUTANTS))
    echo "Mutation Score: ${SCORE}% (${TOTAL_KILLED}/${TOTAL_MUTANTS})"
    echo "  Killed:   $TOTAL_KILLED"
    echo "  Survived: $TOTAL_SURVIVED"
    echo ""
    
    if [ $SCORE -ge 90 ]; then
        echo_success "Mutation score meets 90% threshold - PASSED"
        exit 0
    else
        echo_error "Mutation score below 90% threshold - FAILED"
        echo_warn "Target: 90%, Actual: ${SCORE}%"
        exit 1
    fi
else
    echo_warn "No mutants tested"
    echo_info "This could mean:"
    echo_info "  - Modules don't have testable code"
    echo_info "  - mutmut is not installed correctly"
    echo_info "  - Test suite is not running"
    exit 1
fi
