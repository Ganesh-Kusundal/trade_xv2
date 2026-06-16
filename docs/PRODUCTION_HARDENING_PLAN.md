# Production Hardening Plan

**Date**: 2026-06-16  
**Status**: Planning  
**Goal**: Elevate TradeXV2 from production-ready to production-excellent

---

## Current State Assessment

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Test Coverage | ~60% (threshold) | 80% | +20% |
| MyPy Errors | 411 (warnings only) | 0 (strict mode) | -411 errors |
| Load Testing | CLI command exists | CI integration | Missing from CI |
| Security Scanning | Ruff bandit rules | bandit + safety CLI | Incomplete |
| Performance Tests | None | Regression suite | Missing |
| API Contract Tests | None | OpenAPI validation | Missing |

---

## Phase 1: Increase Coverage to 80%

### Strategy
Target modules with lowest coverage first. Focus on critical paths:
1. Broker adapters (Dhan, Upstox, Paper)
2. CLI commands (analytics, market, oms)
3. Analytics modules (indicators, strategy, backtest)
4. Data lake (loader, converter, updater)

### Execution Plan
1. **Identify gaps**: Run coverage report with `--show-missing`
2. **Prioritize by criticality**: OMS > Market Data > Analytics > CLI
3. **Write targeted tests**: Focus on edge cases, error paths, integration
4. **Set threshold**: Update `--fail-under=80` in CI

### Exclusions (What NOT to test)
- Frontend (TypeScript, separate test suite)
- E2E sandbox tests (require live broker credentials)
- Performance/load tests (covered in Phase 3)
- Documentation/examples

### Estimated Effort
- **Scope**: ~200 new tests
- **Time**: 2-3 hours
- **Risk**: Low (purely additive, no refactoring)

---

## Phase 2: Enable MyPy Strict Mode

### Current State
- **411 errors** across codebase (tracked in MYPY.md)
- `strict = false` in pyproject.toml
- 5 warning flags enabled but non-blocking

### Gradual Migration Strategy

#### Step 1: Baseline and Categorize (15 min)
```bash
mypy brokers/ --show-error-codes > mypy-errors.txt
# Categorize by error code:
# - arg-type, return-value, assignment
# - attr-defined, call-arg, union-attr
# - import-untyped, import-not-found
```

#### Step 2: Fix Easy Wins (30 min)
- Add missing type annotations to functions
- Fix obvious type mismatches
- Add `# type: ignore` for legitimate cases (3rd party libs)

#### Step 3: Enable Strict Module-by-Module (1 hour)
```toml
# pyproject.toml
[[tool.mypy.overrides]]
module = ["brokers.common.core.*", "brokers.common.resilience.*"]
strict = true
```

**Order**: common/core → common/resilience → common/oms → common/event_bus → dhan → upstox → paper → cli

#### Step 4: Enable Global Strict (30 min)
- Set `strict = true` in `[tool.mypy]`
- Add per-module overrides for remaining problem areas
- Update MYPY.md with final error count (target: 0)

### Strict Mode Flags (what gets enabled)
```toml
strict = true  # enables:
# - warn_unused_configs
# - disallow_any_generics
# - disallow_subclassing_any
# - disallow_untyped_calls
# - disallow_untyped_defs
# - disallow_incomplete_defs
# - check_untyped_defs
# - disallow_untyped_decorators
# - no_implicit_optional
# - warn_redundant_casts
# - warn_unused_ignores
# - warn_return_any
# - no_implicit_reexport
# - strict_equality
```

### Estimated Effort
- **Scope**: 411 errors → 0
- **Time**: 2-3 hours
- **Risk**: Medium (may reveal bugs, but type-safe)

---

## Phase 3: Add Load Testing to CI

### Current State
- ✅ `cli/load_testing/runner.py` exists (async load test runner)
- ✅ `cli/commands/load_test.py` exists (CLI command)
- ❌ Not integrated into CI pipeline

### CI Integration Plan

#### Step 1: Create Load Test Workflow
```yaml
# .github/workflows/load-test.yml
name: Load Testing
on:
  schedule:
    - cron: '0 2 * * 1'  # Every Monday at 2 AM
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run load tests (paper broker)
        run: |
          python -m cli.main load-test --broker paper --duration 10 --concurrency 10
```

#### Step 2: Add Performance Budget
```python
# cli/load_testing/budget.py
PERFORMANCE_BUDGET = {
    "quote": {"max_latency_ms": 500, "min_rps": 10},
    "historical": {"max_latency_ms": 2000, "min_rps": 5},
    "option_chain": {"max_latency_ms": 1000, "min_rps": 5},
}
```

#### Step 3: Generate Report
- Output JSON with latency percentiles (p50, p95, p99)
- Fail CI if budget exceeded
- Upload as artifact for trend analysis

### Estimated Effort
- **Scope**: 1 workflow, 1 budget file, CI integration
- **Time**: 1 hour
- **Risk**: Low (isolated to paper broker, no live API calls)

---

## Phase 4: Add Security Scanning

### Current State
- ✅ Ruff includes `S` (flake8-bandit) rules
- ✅ `bandit` in dev dependencies
- ❌ Not running as standalone scanner
- ❌ No dependency vulnerability scanning (safety)

### Implementation Plan

#### Step 1: Add Bandit to CI
```yaml
# .github/workflows/ci.yml (add to lint job)
- name: Bandit security scan
  run: bandit -r brokers/ cli/ datalake/ analytics/ -ll -f txt -o bandit-report.txt
  continue-on-error: true  # warnings only initially
```

#### Step 2: Add Safety for Dependencies
```yaml
- name: Safety check
  run: |
    pip install safety
    safety check --json --output safety-report.json
  continue-on-error: true
```

#### Step 3: Configure Bandit
```yaml
# .bandit (or pyproject.toml)
[tool.bandit]
exclude_dirs = ["tests", ".cache", "venv"]
skips = ["B101", "B104"]  # assert, hardcoded_bind
```

#### Step 4: Review and Fix Findings
- Run `bandit -r .` locally
- Fix high/critical severity issues
- Document acceptable risks

### Estimated Effort
- **Scope**: 2 new CI steps, configuration, review
- **Time**: 1 hour
- **Risk**: Low (read-only scanning, no code changes)

---

## Phase 5: Add Performance Regression Tests

### Strategy
Create benchmarks for critical paths and track over time:

1. **Market Data Latency**: quote(), ltp(), history()
2. **Order Placement**: place_order() → TRADE round-trip
3. **PnL Calculation**: PnLCalculator.compute() for 100 positions
4. **Event Bus**: publish() → handler dispatch latency
5. **Data Lake**: Parquet read/write throughput

### Implementation

#### Step 1: Create Benchmark Suite
```python
# tests/performance/test_benchmarks.py
import pytest
from brokers.common.core.pnl_calculator import PnLCalculator

class TestPnLBenchmark:
    @pytest.mark.performance
    def test_compute_100_positions(self, benchmark):
        positions = [create_test_position(i) for i in range(100)]
        result = benchmark(PnLCalculator.compute, positions)
        assert result.total_pnl is not None
```

#### Step 2: Use pytest-benchmark
```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "performance: marks tests as performance benchmarks",
]

[tool.pytest-benchmark]
min_rounds = 5
max_time = 1.0
```

#### Step 3: Store Baselines
- Save benchmark results to `benchmarks/baseline.json`
- Compare against baseline in CI
- Fail if regression > 10%

#### Step 4: CI Integration
```yaml
- name: Run performance benchmarks
  run: pytest tests/performance/ --benchmark-only --benchmark-compare
```

### Estimated Effort
- **Scope**: 10-15 benchmark tests, baseline storage, CI
- **Time**: 2 hours
- **Risk**: Low (isolated tests, no production impact)

---

## Phase 6: Add API Contract Tests

### Strategy
Validate that broker adapters conform to the MarketDataGateway contract:

1. **Contract Tests**: Verify all abstract methods implemented
2. **Schema Validation**: Verify return types match spec
3. **Error Handling**: Verify exceptions raised correctly
4. **Integration Tests**: Verify end-to-end flows

### Implementation

#### Step 1: Create Contract Test Suite
```python
# tests/integration/test_gateway_contract.py
import pytest
from brokers.common.gateway import MarketDataGateway

class TestGatewayContract:
    """Verify all broker adapters implement MarketDataGateway."""
    
    @pytest.fixture(params=["dhan", "upstox", "paper"])
    def gateway(self, request):
        # Return instantiated gateway for each broker
        ...
    
    def test_all_abstract_methods_implemented(self, gateway):
        """Verify no NotImplementedError raised."""
        for method_name in MarketDataGateway.__abstractmethods__:
            assert hasattr(gateway, method_name)
    
    def test_quote_returns_canonical_type(self, gateway):
        from brokers.common.core.domain import Quote
        quote = gateway.quote("RELIANCE", "NSE")
        assert isinstance(quote, Quote)
```

#### Step 2: Add Schema Validation
```python
def test_history_returns_canonical_schema(self, gateway):
    df = gateway.history("RELIANCE", timeframe="1D", lookback_days=7)
    required_columns = ["timestamp", "open", "high", "low", "close", "volume"]
    assert all(col in df.columns for col in required_columns)
```

#### Step 3: CI Integration
```yaml
# Already in CI as unit-and-contract job
# Just need to add new test file to test discovery
```

### Estimated Effort
- **Scope**: 20-30 contract tests across 3 brokers
- **Time**: 1.5 hours
- **Risk**: Low (test-only, may reveal adapter bugs)

---

## Execution Order & Dependencies

```
Phase 1: Coverage (no dependencies) ──────────────────┐
Phase 2: MyPy (no dependencies) ──────────────────────┤
Phase 3: Load Testing (needs Phase 1 for coverage) ───┼── Parallel
Phase 4: Security (no dependencies) ──────────────────┤
Phase 5: Performance (needs Phase 1 for coverage) ────┤
Phase 6: Contract Tests (no dependencies) ────────────┘
```

**Recommended Order**:
1. Phase 4 (Security) — Quick win, 1 hour
2. Phase 6 (Contract Tests) — Quick win, 1.5 hours
3. Phase 3 (Load Testing) — Medium, 1 hour
4. Phase 1 (Coverage) — Large, 2-3 hours
5. Phase 2 (MyPy) — Large, 2-3 hours
6. Phase 5 (Performance) — Medium, 2 hours

**Total Estimated Time**: 10-11.5 hours

---

## Success Criteria

| Phase | Pass Criteria |
|-------|---------------|
| Phase 1 | Coverage ≥ 80%, CI threshold updated |
| Phase 2 | MyPy strict = true, 0 errors (or documented overrides) |
| Phase 3 | Load test workflow runs weekly, budget enforced |
| Phase 4 | Bandit + Safety in CI, 0 critical findings |
| Phase 5 | 10+ benchmarks, regression detection in CI |
| Phase 6 | 20+ contract tests, all brokers pass |

---

## What NOT to Build Yet

1. **Distributed tracing** (OpenTelemetry) — Overkill for single-process system
2. **A/B testing framework** — Not needed for trading platform
3. **Feature flags** — Premature optimization
4. **Multi-region deployment** — Single-region fine for now
5. **Chaos engineering in production** — Chaos tests exist, don't run in prod yet
6. **GraphQL API** — REST + CLI sufficient
7. **WebSocket market data proxy** — Direct broker connections work fine
8. **ML model serving** — Analytics module covers current needs

---

## Rollback Plan

Each phase is independent and can be reverted:
- **Phase 1**: Remove new tests (no production impact)
- **Phase 2**: Set `strict = false` (revert pyproject.toml)
- **Phase 3**: Delete workflow file
- **Phase 4**: Remove CI steps, keep config
- **Phase 5**: Delete benchmark tests
- **Phase 6**: Delete contract tests

No phase modifies production code paths — all changes are additive (tests, CI, config).

---

## Next Steps

1. ✅ Review and approve this plan
2. ⏳ Start with Phase 4 (Security) — quickest win
3. ⏳ Execute phases in recommended order
4. ⏳ Commit after each phase with test results
5. ⏳ Update this document with actual metrics
