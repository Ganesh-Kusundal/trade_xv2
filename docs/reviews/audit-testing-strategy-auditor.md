# Testing Strategy Audit — Trade_XV2

**Agent:** testing-strategy-auditor  
**Date:** 2026-06-23  
**Verification runs:** architecture 56 passed; OMS+execution+event_bus 177 passed; chaos 87 collected

---

## Executive Summary

Trade_XV2 has ~351 test files with a broad pyramid: heavy unit/contract base (brokers: 147, application: 20), mid integration layer (13), narrow e2e/chaos/stress peak. CI enforces 80–90% coverage gates, quant parity, and architecture deepening. Critical gaps: **e2e marker collects zero tests**, **integration CI non-blocking**, **infrastructure undertested (1/18 modules)**, **Upstox live fill path untested**, **duplicate shim test suites**.

---

## Test Pyramid

| Layer | Files | Location | Ratio |
|-------|-------|----------|-------|
| L1 Unit/Contract | ~258 module-colocated | `brokers/`, `application/`, `analytics/`, `cli/` | ~73% |
| L2 Integration | 13 | `tests/integration/` | ~4% |
| L3 System/E2E | 5 (143 cases) | `tests/e2e/` | ~1% |
| L4 Chaos/Stress/Perf | 9 | `tests/chaos/`, `stress/`, `performance/` | ~3% |
| Architecture/Quant | 12 | `tests/architecture/`, `tests/quant/` | ~3% |
| API tests | 26 | `tests/api/` | ~7% |

**Shape:** Wide base, thin top — appropriate for trading platform but **live broker paths underrepresented at L2/L3**.

---

## Critical Path Coverage

| Path | Tested? | Test Files |
|------|---------|------------|
| Order placement idempotency | Yes | `application/oms/tests/test_trade_idempotency.py` |
| Partial fill lifecycle | Yes | `application/oms/tests/test_partial_fill_lifecycle.py` |
| Concurrent rapid fills | Yes | `application/oms/tests/test_concurrent_rapid_fills.py` |
| Execution mode parity | Yes | `application/execution/tests/test_execution_mode_oms_parity.py` |
| Dhan WS ORDER_UPDATED/TRADE | Yes (unit) | `brokers/dhan/tests/unit/test_websocket.py` |
| Dhan cumulative fill bug | **No** | Tests use incremental qty (40+60), not cumulative |
| Upstox WS → OMS integration | **No** | `test_websocket_safety.py` checks raw event, not OMS handler |
| Paper double apply | **No** | `brokers/paper/tests/test_paper.py` does not assert single position |
| Processed trade persistence on CLI | **No** | `infrastructure/event_bus/tests/test_processed_trade_crash_recovery.py` exists but CLI path not wired |
| Multi-strategy runtime | **No** | `application/trading/multi_strategy_runtime.py` — zero tests |
| Runtime stale event_bus import | **No** | No test for `build_for_api()` import path |
| Kill switch atomic flip | Yes | `tests/integration/test_kill_switch_atomic_flip.py` (not in default CI) |
| Broker disconnect during order | Partial | `tests/chaos/test_failure_modes.py` |
| Token expiry during trading | Partial | Dhan token scheduler unit tests only |

---

## CI Pipeline Assessment

| Job | Blocking? | Finding |
|-----|-----------|---------|
| lint (import-linter, ruff) | Yes | Pass |
| MyPy brokers/ | **No** | ~499 errors tolerated — `ci.yml:40-54` |
| Bandit + Safety | **No** | `|| true` — `ci.yml:57-62` |
| unit-and-contract | Yes | 80% overall, 85% brokers, 90% OMS, 80% application |
| quant-parity | Yes | `STRICT_EXECUTION_PARITY=1` |
| integration (sandbox) | **No** | `continue-on-error: true`, main push only — `ci.yml` |
| e2e-tests | Yes | **`pytest -m e2e` collects 0 tests** (143 deselected); relies on explicit file list |
| stress-tests | Yes | Benchmark compare warns only |
| flaky-test-detection | **No** | `continue-on-error: true` |

**Verified:** `pytest tests/e2e/ -m e2e --co -q` → **no tests collected (143 deselected)**

---

## Test Quality Issues

| Issue | Severity | Evidence |
|-------|----------|----------|
| Duplicate test suites at shim paths | Medium | `brokers/common/oms/tests/` mirrors `application/oms/tests/` |
| Chaos tests import legacy shim paths | Medium | `tests/chaos/test_failure_modes.py` → `brokers.common.lifecycle` |
| infrastructure/ has 1 test file for 18 modules | High | Only `infrastructure/event_bus/tests/test_processed_trade_crash_recovery.py` |
| pre_prod marker defined but not in CI | Medium | `pyproject.toml` — no workflow gate |
| Mock-heavy Upstox integration | High | `tests/integration/test_upstox_order_lifecycle.py` not in default CI |

---

## Chaos / Fault Injection

| Scenario | Covered? | Location |
|----------|----------|----------|
| Broker disconnect | Partial | `tests/chaos/test_failure_modes.py` |
| Network partition | Yes | `tests/chaos/test_network_partitions.py` |
| Data corruption | Yes | `tests/chaos/test_data_corruption.py` |
| Recovery certification | Yes | `tests/chaos/test_recovery_certification.py` |
| Failover | Yes | `tests/chaos/test_failover.py` |
| Rate limit exhaustion | Partial | Dhan unit tests only |
| WS disconnect during market open | **No** dedicated |
| DB drop during position update | **No** |

---

## Top Findings

| # | Finding | Severity | Location |
|---|---------|----------|----------|
| 1 | e2e marker step is no-op in CI | High | `tests/e2e/*.py` — no `@pytest.mark.e2e` |
| 2 | Integration CI non-blocking | High | `.github/workflows/ci.yml` |
| 3 | infrastructure/ severely undertested | High | 1 test / 18 modules |
| 4 | Dhan cumulative fill bug untested | Critical | Gap vs `brokers/dhan/websocket.py:991-1001` |
| 5 | Upstox OMS fill path untested | Critical | No integration test for portfolio_stream → OMS |
| 6 | multi_strategy_runtime untested | High | `application/trading/multi_strategy_runtime.py` |
| 7 | MyPy/security scans non-blocking | Medium | `ci.yml:40-62` |
| 8 | Duplicate shim test maintenance burden | Medium | `brokers/common/oms/tests/` |

**Testing Score (internal): 6/10** — Strong OMS/execution unit coverage; live broker and infrastructure gaps.
