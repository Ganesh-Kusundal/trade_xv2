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

# Run certification suite (aggregated pass/fail report)
run_certification() {
    local broker=$1
    echo_info "Running $broker certification suite..."
    "$PYTHON" -m brokers.common.tests.certify_broker $broker --live
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
        args+=(tests/integration/brokers/dhan/)
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

# ── Dhan regression suite helpers ─────────────────────────────────────────

run_regression_off_market() {
    echo_info "Running Dhan off-market regression (REST/read-only)..."
    echo_info "Safe to run anytime — no WebSocket tests included."
    check_env_creds
    mkdir -p reports
    "$PYTHON" -m pytest \
        -m "dhan and off_market_safe and regression" \
        tests/integration/brokers/dhan/test_regression_suite.py \
        tests/integration/brokers/dhan/regression/test_e2e_smoke.py \
        --tb=short -v \
        --junitxml=reports/off_market_regression.xml \
        --timeout=120
    "$PYTHON" scripts/dhan_regression_report.py \
        --junit reports/off_market_regression.xml \
        --output docs/audits/DHAN_REGRESSION_REPORT.md \
        --fail-on P0
}

run_regression_market_hours() {
    echo_info "Running Dhan market-hours regression (WebSocket/streaming)..."
    echo_warn "Requires NSE trading hours (09:15–15:30 IST) or FORCE_MARKET_OPEN=1."
    check_env_creds
    mkdir -p reports
    FORCE_MARKET_OPEN="${FORCE_MARKET_OPEN:-0}" \
    "$PYTHON" -m pytest \
        -m "dhan and market_hours and regression" \
        tests/integration/brokers/dhan/test_regression_suite.py \
        tests/integration/brokers/dhan/regression/test_e2e_smoke.py \
        --tb=short -v \
        --junitxml=reports/market_hours_regression.xml \
        --timeout=120
}

run_regression_full() {
    echo_info "Running full Dhan regression suite (all tiers)..."
    echo_warn "Requires PRE_PROD_GATE=1 and live NSE hours for streaming tests."
    check_env_creds
    mkdir -p reports
    PRE_PROD_GATE="${PRE_PROD_GATE:-1}" \
    FORCE_MARKET_OPEN="${FORCE_MARKET_OPEN:-0}" \
    "$PYTHON" -m pytest \
        -m "dhan and regression" \
        tests/integration/brokers/dhan/ \
        --tb=short -v \
        --junitxml=reports/full_regression.xml \
        --timeout=180
    "$PYTHON" scripts/dhan_regression_report.py \
        --junit reports/full_regression.xml \
        --output docs/audits/DHAN_REGRESSION_REPORT.md \
        --fail-on P0
}

run_regression_sandbox() {
    echo_info "Running Dhan sandbox order E2E..."
    echo_warn "Requires DHAN_SANDBOX_CLIENT_ID and DHAN_SANDBOX_ACCESS_TOKEN."
    if [ -z "${DHAN_SANDBOX_CLIENT_ID:-}" ] || [ -z "${DHAN_SANDBOX_ACCESS_TOKEN:-}" ]; then
        echo_error "DHAN_SANDBOX_CLIENT_ID and DHAN_SANDBOX_ACCESS_TOKEN must be set."
        exit 1
    fi
    mkdir -p reports
    DHAN_INTEGRATION=1 DHAN_SANDBOX=1 \
    "$PYTHON" -m pytest \
        -m sandbox \
        tests/e2e/test_sandbox_real_broker.py \
        cli/tests/test_order_sandbox_integration.py \
        --tb=short -v \
        --junitxml=reports/sandbox_orders.xml \
        --timeout=60
}

check_env_creds() {
    if [ -z "${DHAN_CLIENT_ID:-}" ] && [ ! -f ".env.local" ]; then
        echo_warn "DHAN_CLIENT_ID not set and .env.local not found."
        echo_info "Live integration tests will be auto-skipped."
    fi
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
    regression-off-market)
        check_venv
        run_regression_off_market
        ;;
    regression-market-hours)
        check_venv
        run_regression_market_hours
        ;;
    regression-full)
        check_venv
        run_regression_full
        ;;
    regression-sandbox|sandbox)
        check_venv
        run_regression_sandbox
        ;;
    broker)
        check_venv
        if [ -z "${2:-}" ]; then
            echo_error "Please specify broker name: dhan, upstox, or paper"
            exit 1
        fi
        run_broker_tests "$2"
        ;;
    certification)
        check_venv
        if [ -z "${2:-}" ]; then
            echo_error "Please specify broker name: dhan, upstox, or paper"
            exit 1
        fi
        run_certification "$2"
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
        echo "  coverage                Run tests with coverage report"
        echo "  broker <name>           Run specific broker tests (dhan|upstox|paper)"
        echo "  certification <name>    Run broker certification suite (dhan|upstox|paper)"
        echo "  regression-off-market   Dhan REST/read-only regression (anytime with creds)"
        echo "  regression-market-hours Dhan WebSocket regression (NSE hours or FORCE_MARKET_OPEN=1)"
        echo "  regression-full         Full pre-release Dhan regression (all tiers)"
        echo "  regression-sandbox      Dhan sandbox order E2E (needs DHAN_SANDBOX_* vars)"
        echo "  help                    Show this help message"
        echo ""
        echo "Environment Variables:"
        echo "  DHAN_INTEGRATION=1           Enable Dhan live integration tests"
        echo "  UPSTOX_INTEGRATION=1         Enable Upstox live integration tests"
        echo "  PRE_PROD_GATE=1              Run pre-production gate tests"
        echo "  FORCE_MARKET_OPEN=1          Force WebSocket tests regardless of market hours"
        echo "  DHAN_SANDBOX_CLIENT_ID=...   Sandbox credentials for order E2E"
        echo "  DHAN_SANDBOX_ACCESS_TOKEN=.. Sandbox access token for order E2E"
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
