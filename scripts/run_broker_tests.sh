#!/usr/bin/env bash
# TradeXV2 Broker Test Runner
#
# Provides convenient commands for running different test categories
# with appropriate flags and environment checks.
#
# Usage:
#   ./scripts/run_broker_tests.sh unit              # Run all unit tests
#   ./scripts/run_broker_tests.sh contract          # Run contract tests
#   ./scripts/run_broker_tests.sh integration       # Run integration tests
#   ./scripts/run_broker_tests.sh performance       # Run performance benchmarks
#   ./scripts/run_broker_tests.sh stress            # Run stress tests
#   ./scripts/run_broker_tests.sh e2e               # Run E2E tests
#   ./scripts/run_broker_tests.sh all               # Run all tests
#   ./scripts/run_broker_tests.sh coverage          # Run with coverage report

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Always use project venv Python (see README.md)
PYTHON="${PROJECT_DIR}/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo_error "Project venv not found at ${PYTHON}"
    echo_info "Run: python -m venv venv && venv/bin/pip install -e '.[dev]'"
    exit 1
fi
export PYTHONPATH="${PROJECT_DIR}${PYTHONPATH:+:$PYTHONPATH}"

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

# Ensure project venv Python is used for all pytest invocations
check_venv() {
    echo_info "Using ${PYTHON}"
}

# Run unit tests (path-based — excludes live integration directories)
run_unit_tests() {
    echo_info "Running unit tests (parallel)..."
    "$PYTHON" -m pytest -m "not integration and not sandbox and not live_readonly" \
        -n auto -v --tb=short \
        --ignore=brokers/dhan/tests/integration \
        --ignore=brokers/upstox/tests/integration
}

# Run contract tests (path-based contract suites)
run_contract_tests() {
    echo_info "Running broker contract tests..."
    "$PYTHON" -m pytest \
        brokers/dhan/tests/contract \
        brokers/upstox/tests/contract \
        brokers/paper/tests/contract \
        -v --tb=short
}

# Run integration tests (Dhan sandbox path + marker-based suites)
run_integration_tests() {
    echo_info "Running integration tests..."
    
    # Check for environment variables
    if [ -z "$DHAN_INTEGRATION" ] && [ -z "$UPSTOX_INTEGRATION" ]; then
        echo_warn "No broker integration enabled. Running marker-based integration tests only."
        echo_info "Set DHAN_INTEGRATION=1 or UPSTOX_INTEGRATION=1 to enable live broker paths."
    fi
    
    args=(-m "integration" -v --tb=short)
    if [ "${DHAN_INTEGRATION:-}" = "1" ]; then
        args+=(brokers/dhan/tests/integration/)
    fi
    "$PYTHON" -m pytest "${args[@]}"
}

# Auth integration — TOTP bootstrap (when creds present) + WS reconnect
run_auth_integration_tests() {
    echo_info "Running auth integration regression (TOTP + WebSocket reconnect)..."
    "$PYTHON" -m pytest -m "auth_integration" -v --tb=short \
        tests/integration/test_auth_totp_live.py \
        tests/integration/test_websocket_reconnect_failure.py
}

# Run performance tests
run_performance_tests() {
    echo_info "Running performance benchmarks..."
    "$PYTHON" -m pytest -m "performance" -v --tb=short --benchmark-only
}

# Run stress tests
run_stress_tests() {
    echo_warn "Stress tests may take 30-60 minutes to complete."
    echo_info "Running stress tests..."
    "$PYTHON" -m pytest -m "stress" -v --tb=short
}

# Run E2E tests
run_e2e_tests() {
    echo_info "Running E2E tests (Paper broker only)..."
    "$PYTHON" -m pytest -m "e2e" -v --tb=short
}

# Run all tests
run_all_tests() {
    echo_info "Running all tests (excluding live integration)..."
    "$PYTHON" -m pytest -m "not live_readonly and not sandbox" -n auto -v --tb=short
}

# Run tests with coverage
run_coverage() {
    echo_info "Running tests with coverage report..."
    "$PYTHON" -m pytest -m "not integration and not sandbox and not live_readonly" \
        -n auto \
        --cov=brokers \
        --cov=cli \
        --cov=datalake \
        --cov=analytics \
        --cov=tests/chaos \
        --cov-branch \
        --cov-report=term-missing \
        --cov-report=html:htmlcov \
        --cov-report=xml:coverage.xml \
        --junitxml=junit.xml \
        -v
    
    echo_success "Coverage report generated: htmlcov/index.html"
    echo_success "Coverage XML: coverage.xml"
    echo_success "JUnit results: junit.xml"
    
    # Show coverage summary
    echo_info ""
    echo_info "Coverage Summary:"
    "$PYTHON" -m coverage report --fail-under=80
}

# Run specific broker tests
run_broker_tests() {
    local broker=$1
    echo_info "Running $broker broker tests..."
    
    case $broker in
        dhan)
            "$PYTHON" -m pytest brokers/dhan/tests/ -v --tb=short
            ;;
        upstox)
            "$PYTHON" -m pytest brokers/upstox/tests/ -v --tb=short
            ;;
        paper)
            "$PYTHON" -m pytest brokers/paper/tests/ -v --tb=short
            ;;
        *)
            echo_error "Unknown broker: $broker"
            echo_info "Available: dhan, upstox, paper"
            exit 1
            ;;
    esac
}

# Main command handler
case "${1:-}" in
    unit)
        check_venv
        run_unit_tests
        ;;
    contract)
        check_venv
        run_contract_tests
        ;;
    integration)
        check_venv
        run_integration_tests
        ;;
    auth-integration)
        check_venv
        run_auth_integration_tests
        ;;
    performance)
        check_venv
        run_performance_tests
        ;;
    stress)
        check_venv
        run_stress_tests
        ;;
    e2e)
        check_venv
        run_e2e_tests
        ;;
    all)
        check_venv
        run_all_tests
        ;;
    coverage)
        check_venv
        run_coverage
        ;;
    broker)
        check_venv
        if [ -z "${2:-}" ]; then
            echo_error "Please specify broker name: dhan, upstox, or paper"
            exit 1
        fi
        run_broker_tests "$2"
        ;;
    help|--help|-h)
        echo "TradeXV2 Broker Test Runner"
        echo ""
        echo "Usage:"
        echo "  $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  unit          Run all unit tests (parallel)"
        echo "  contract      Run broker contract tests"
        echo "  integration   Run integration tests (set DHAN_INTEGRATION=1 for live Dhan sandbox)"
        echo "  auth-integration  TOTP bootstrap + WebSocket reconnect regression"
        echo "  performance   Run performance benchmarks"
        echo "  stress        Run stress tests (30-60 min)"
        echo "  e2e           Run E2E tests (Paper broker)"
        echo "  all           Run all tests (excluding live)"
        echo "  coverage      Run tests with coverage report"
        echo "  broker <name> Run specific broker tests (dhan|upstox|paper)"
        echo "  help          Show this help message"
        echo ""
        echo "Environment Variables:"
        echo "  DHAN_INTEGRATION=1      Enable Dhan live integration tests"
        echo "  UPSTOX_INTEGRATION=1    Enable Upstox live integration tests"
        echo "  PRE_PROD_GATE=1         Run pre-production gate tests"
        ;;
    "")
        echo_error "No command specified. Use 'help' for usage information."
        exit 1
        ;;
    *)
        echo_error "Unknown command: $1"
        echo_info "Use 'help' for usage information."
        exit 1
        ;;
esac

echo_success "Tests completed successfully!"
