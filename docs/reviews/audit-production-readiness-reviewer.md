# Production Readiness Assessment — Trade_XV2 (Capstone)

**Agent:** production-readiness-reviewer  
**Date:** 2026-06-23  
**Input:** Agents 1–7 consolidated findings

---

## VERDICT: NOT READY

**Weighted Score: 4.7/10**

This system has a sound architectural target, strong OMS unit test coverage, and well-designed reliability primitives (lifecycle, DLQ, circuit breakers, Decimal risk). It is **not ready for live capital** because broker fill paths contain silent state corruption bugs (Dhan cumulative qty, Upstox broken WS contract, paper double-apply), the processed trade ledger is not persisted on the default CLI path, and API bootstrap references a deleted module.

---

## Score Card

| Dimension | Weight | Score | Verdict | Top Risk |
|-----------|--------|-------|---------|----------|
| Architecture | 10% | 5/10 | Partial | Stale event_bus import; CLI composition SPOF |
| Design Quality | 10% | 5/10 | Partial | Broker→application inversion; event contract violations |
| Code Quality | 8% | 6/10 | Adequate | God classes (OrderManager 631L, TradingContext 516L) |
| Testing | 12% | 6/10 | Partial | Strong OMS unit; live broker paths untested |
| Reliability | 15% | 5/10 | Partial | Ledger not persisted; replay duplicates |
| Scalability | 8% | 5/10 | Partial | Single-writer SQLite; sync EventBus |
| Security | 12% | 5/10 | Partial | MyPy/Bandit non-blocking in CI |
| Performance | 10% | 6/10 | Adequate | Lock discipline in OMS; no soak test gates |
| Maintainability | 7% | 5/10 | Partial | Dual shim paths; 150+ brokers.common imports |
| Operational Readiness | 8% | 5/10 | Partial | Health/metrics present; runbooks not in code |
| **WEIGHTED TOTAL** | **100%** | **4.7/10** | **NOT READY** | — |

**Calculation:** (5×0.10)+(5×0.10)+(6×0.08)+(6×0.12)+(5×0.15)+(5×0.08)+(5×0.12)+(6×0.10)+(5×0.07)+(5×0.08) = 4.71

---

## Dimension Deep Dives

### 1. Architecture (5/10)
- **Pass:** domain/infrastructure independence enforced by import-linter
- **Pass:** application layer broker-free in prod code
- **Fail:** `runtime/trading_runtime_factory.py:77` — deleted `brokers.common.event_bus.factory`
- **Fail:** Runtime imports CLI `BrokerService` (`trading_runtime_factory.py:78,94`)
- **Fail:** 150+ files still on `brokers.common.*` shim paths

### 2. Design Quality (5/10)
- **Pass:** `ExecutionModeAdapter` ABC unifies live/paper/replay
- **Pass:** `TRADE_APPLIED` gating for position updates
- **Fail:** Upstox WS wrong event contract (`portfolio_stream.py:134-138`)
- **Fail:** Paper bypasses event contract (`paper_orders.py:189-191`)
- **Fail:** Upstox duplicate ORDER_PLACED (`order_command_adapter.py:247-254`)

### 3. Code Quality (6/10)
- **Pass:** Decimal in RiskManager; explicit orchestration contract
- **Pass:** EventBus never silently swallows handler failures
- **Fail:** OrderManager 631 lines — SRP violation
- **Fail:** Silent event publish swallow in Upstox adapter (`order_command_adapter.py:244-246`)

### 4. Testing (6/10)
- **Pass:** 177 OMS+execution tests pass; 56 architecture tests pass
- **Pass:** Quant parity CI gate with STRICT_EXECUTION_PARITY
- **Fail:** `pytest -m e2e` collects 0 tests
- **Fail:** infrastructure/ has 1 test for 18 modules
- **Fail:** Dhan cumulative fill bug has no failing test

### 5. Reliability (5/10)
- **Pass:** LifecycleManager ordered start/stop
- **Pass:** DLQ on handler failure
- **Fail:** ProcessedTradeRepository in-memory on CLI path
- **Fail:** EventLog replay + empty ledger = duplicate trades
- **Fail:** Upstox live fills never reach OMS

### 6. Scalability (5/10)
- **Pass:** Bounded DLQ FIFO
- **Fail:** Single-writer SQLite OMS store
- **Fail:** Synchronous EventBus — no horizontal scaling path

### 7. Security (5/10)
- **Pass:** import-linter boundary enforcement
- **Fail:** MyPy ~499 errors non-blocking (`ci.yml:40-54`)
- **Fail:** Bandit/Safety `|| true` (`ci.yml:57-62`)

### 8. Performance (6/10)
- **Pass:** OMS lock held only for state mutations, not network I/O
- **Pass:** Stress test job in CI
- **Fail:** Benchmark compare warns only, does not block

### 9. Maintainability (5/10)
- **Pass:** Architecture deepening tests
- **Fail:** Duplicate test suites at shim + canonical paths
- **Fail:** IntelligentGateway 578 lines unmigrated

### 10. Operational Readiness (5/10)
- **Pass:** `/healthz`, `/readyz`, `/metrics` endpoints
- **Pass:** RiskManager snapshot for dashboards
- **Fail:** No runbook for DLQ replay in codebase
- **Fail:** Integration CI non-blocking on main

---

## Top 20 Risks (Severity × Likelihood × Consequence)

| # | Risk | S | L | C | Location |
|---|------|---|---|---|----------|
| 1 | Dhan partial fill double-counts position | 10 | 8 | 10 | `brokers/dhan/websocket.py:991-1001` |
| 2 | Upstox live fills never update OMS/positions | 10 | 9 | 10 | `brokers/upstox/websocket/portfolio_stream.py:127-138` |
| 3 | Processed trade ledger not persisted on CLI | 10 | 7 | 9 | `cli/services/oms_setup.py:150-157` |
| 4 | Paper trading double-applies positions | 9 | 8 | 8 | `brokers/paper/paper_orders.py:189-191` |
| 5 | API bootstrap broken event_bus import | 9 | 6 | 9 | `runtime/trading_runtime_factory.py:77` |
| 6 | EventLog replay duplicates trades after restart | 9 | 6 | 9 | `application/oms/context.py:511-512` |
| 7 | authorize_risk_fail_open allows unguarded orders | 8 | 5 | 10 | `runtime/trading_runtime_factory.py:49` |
| 8 | Broker adapters import application layer | 8 | 9 | 7 | `brokers/paper/paper_gateway.py:25-26` |
| 9 | Upstox duplicate ORDER_PLACED events | 7 | 7 | 7 | `brokers/upstox/orders/order_command_adapter.py:247-254` |
| 10 | In-memory broker idempotency lost on restart | 7 | 6 | 8 | `brokers/dhan/orders.py:226-229` |
| 11 | Integration CI non-blocking | 7 | 8 | 6 | `.github/workflows/ci.yml` |
| 12 | e2e marker CI step is no-op | 6 | 9 | 5 | `tests/e2e/*.py` |
| 13 | infrastructure/ undertested | 6 | 7 | 6 | `infrastructure/` (1 test) |
| 14 | Single-writer invariant not enforced | 6 | 5 | 8 | `application/oms/context.py:54-58` |
| 15 | CLI as composition SPOF for API | 6 | 7 | 6 | `runtime/trading_runtime_factory.py:78` |
| 16 | MyPy/security scans non-blocking | 5 | 8 | 5 | `ci.yml:40-62` |
| 17 | multi_strategy_runtime untested | 6 | 6 | 6 | `application/trading/multi_strategy_runtime.py` |
| 18 | 24h trade ledger eviction | 5 | 4 | 7 | `domain/constants/__init__.py` |
| 19 | Upstox silent event publish swallow | 5 | 6 | 6 | `order_command_adapter.py:244-246` |
| 20 | Duplicate shim test maintenance drift | 4 | 8 | 4 | `brokers/common/oms/tests/` |

---

## Top 20 Improvements (Score Impact × Effort)

| # | Improvement | Impact | Effort |
|---|-------------|--------|--------|
| 1 | Fix Dhan incremental fill qty calculation | +1.5 Reliability, +1.0 Quant | 4h |
| 2 | Fix Upstox WS → canonical Order + TRADE events | +2.0 Reliability, +1.5 Quant | 1d |
| 3 | Persist ProcessedTradeRepository on CLI path | +1.5 Reliability | 4h |
| 4 | Remove paper double apply_trade | +1.0 Quant | 2h |
| 5 | Fix runtime event_bus import | +0.5 Architecture | 1h |
| 6 | Add failing test for Dhan cumulative fill | +0.5 Testing | 2h |
| 7 | Add @pytest.mark.e2e to e2e tests | +0.3 Testing | 1h |
| 8 | Make integration CI blocking | +0.5 Testing, +0.3 Ops | 2h |
| 9 | Extract neutral composition root from CLI | +1.0 Architecture | 2d |
| 10 | Remove broker→application imports | +1.0 Architecture, +0.5 Design | 3d |
| 11 | Complete shim migration | +0.8 Maintainability | 1d |
| 12 | Add infrastructure/ test suite | +0.5 Testing | 2d |
| 13 | Block MyPy errors incrementally | +0.5 Security | 1w |
| 14 | Decompose OrderManager | +0.5 Code Quality, +0.5 Maintainability | 1w |
| 15 | Add Upstox OMS integration test | +0.5 Testing | 1d |
| 16 | Enforce single-writer at startup | +0.3 Reliability | 4h |
| 17 | Wire trade ledger cleanup as shutdown hook | +0.2 Reliability | 2h |
| 18 | Test multi_strategy_runtime | +0.3 Testing | 2d |
| 19 | Consolidate duplicate test suites | +0.3 Maintainability | 1d |
| 20 | Add DLQ replay runbook | +0.3 Ops | 4h |

---

## Quick Wins (1–2 days each)

1. Fix `runtime/trading_runtime_factory.py:77` → `infrastructure.event_bus.factory` (1h)
2. Fix Dhan fill qty: compute incremental = filled - order.filled_quantity (4h)
3. Remove `position_manager.apply_trade()` from `paper_orders.py:191` (2h)
4. Wire `ProcessedTradeRepository` persistence in `oms_setup.py` (4h)
5. Add `@pytest.mark.e2e` to all `tests/e2e/*.py` files (1h)
6. Add regression test for Dhan cumulative fill (2h)
7. Stop `authorize_risk_fail_open` default or gate behind explicit env (2h)

---

## Medium-Term (1–4 weeks)

| Sprint | Items |
|--------|-------|
| Week 1 | Upstox WS canonical Order + TRADE; paper gateway decoupling; integration CI blocking |
| Week 2 | Neutral composition root; broker→application import removal |
| Week 3 | Shim migration completion; infrastructure test suite |
| Week 4 | OrderManager decomposition; multi_strategy_runtime tests |

---

## Long-Term Strategic (1–6 months)

| Milestone | Target |
|-----------|--------|
| M1 (Month 1) | All Phase A+B fixes complete; weighted score ≥ 6.5 |
| M2 (Month 2) | Live broker integration tests gate merges; MyPy errors < 100 |
| M3 (Month 3) | Horizontal scaling design for EventBus; async dispatch default |
| M4 (Month 4–6) | Production certification re-audit; target score ≥ 8.0 |

---

## Roadmap Summary

| Phase | Timeline | Goal | Key Items |
|-------|----------|------|-----------|
| A | 1–3 days | Protect capital | Dhan fill, paper double-apply, ledger persistence, runtime import |
| B | 1–2 weeks | Fix boundaries | Composition root, broker decoupling, Upstox WS |
| C | 2–4 weeks | Harden | Tests, CI gates, infrastructure coverage, decomposition |

---

## Plain-English Justification

The platform's bones are good: risk checks run before orders leave the system, money math uses Decimal, and the event bus has dead-letter queues and crash recovery hooks. But the live trading plumbing has holes — Dhan sends fill quantities the OMS misinterprets, Upstox fills never reach the order manager at all, and paper trading counts every fill twice. After a restart, the system can replay old trades and apply them again because the deduplication ledger isn't saved to disk. These aren't edge cases; they're the paths real orders take every trading day. Until they're fixed and tested under live broker conditions, deploying real capital would be gambling with silent position drift.
