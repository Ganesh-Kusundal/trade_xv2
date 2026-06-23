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

# Check if virtual environment is activated
check_venv() {
    if [ -z "$VIRTUAL_ENV" ]; then
        echo_warn "Virtual environment not activated. Using system Python."
        echo_info "Recommended: source .venv/bin/activate"
    fi
}

# Run unit tests
run_unit_tests() {
    echo_info "Running unit tests (parallel)..."
    pytest -m "unit" -n auto -v --tb=short
}

# Run contract tests
run_contract_tests() {
    echo_info "Running broker contract tests..."
    pytest -m "contract" -v --tb=short
}

# Run integration tests
run_integration_tests() {
    echo_info "Running integration tests..."
    
    # Check for environment variables
    if [ -z "$DHAN_INTEGRATION" ] && [ -z "$UPSTOX_INTEGRATION" ]; then
        echo_warn "No broker integration enabled. Running Paper broker tests only."
        echo_info "Set DHAN_INTEGRATION=1 or UPSTOX_INTEGRATION=1 to enable live tests."
    fi
    
    pytest -m "integration" -v --tb=short
}

# Run performance tests
run_performance_tests() {
    echo_info "Running performance benchmarks..."
    pytest -m "performance" -v --tb=short --benchmark-only
}

# Run stress tests
run_stress_tests() {
    echo_warn "Stress tests may take 30-60 minutes to complete."
    echo_info "Running stress tests..."
    pytest -m "stress" -v --tb=short
}

# Run E2E tests
run_e2e_tests() {
    echo_info "Running E2E tests (Paper broker only)..."
    pytest -m "e2e" -v --tb=short
}

# Run all tests
run_all_tests() {
    echo_info "Running all tests (excluding live integration)..."
    pytest -m "not live_readonly and not sandbox" -n auto -v --tb=short
}

# Run tests with coverage
run_coverage() {
    echo_info "Running tests with coverage report..."
    pytest -m "not integration and not sandbox and not live_readonly" \
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
    coverage report --fail-under=80
}

# Run specific broker tests
run_broker_tests() {
    local broker=$1
    echo_info "Running $broker broker tests..."
    
    case $broker in
        dhan)
            pytest brokers/dhan/tests/ -v --tb=short
            ;;
        upstox)
            pytest brokers/upstox/tests/ -v --tb=short
            ;;
        paper)
            pytest brokers/paper/tests/ -v --tb=short
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
        echo "  integration   Run integration tests"
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
