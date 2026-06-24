# Quant Platform Review — Trade_XV2

**Agent:** quant-platform-reviewer  
**Date:** 2026-06-23  
**Context:** Architecture, EDA, static, broker findings

---

## Executive Summary

Risk management uses Decimal precision and enforces pre-trade checks in OrderManager before broker submission. Execution parity infrastructure exists (`ExecutionModeAdapter`, `parity_gate`, quant tests). However, **broker fill path bugs cause incorrect position/PnL on Dhan partial fills**, **Upstox live fills never reach OMS**, **paper trading double-counts positions**, and **processed trade ledger is not persisted** — making restart recovery unsafe for real capital.

---

## Expected Behavior Contract

| Contract | Enforced? | Evidence |
|----------|-----------|----------|
| Risk before order submission | **Yes** | `application/oms/order_manager.py:286-298` — risk check before `submit_fn` |
| Kill switch blocks orders | **Yes** | `application/oms/_internal/risk_manager.py` — `kill_switch` property |
| Decimal PnL in risk manager | **Yes** | `risk_manager.py:59-61,112,161` — all Decimal |
| Zero-parity live/paper/replay | **Partial** | `application/execution/execution_mode_adapter.py` — same OMS path; paper deviates |
| No look-ahead in backtest | **Partial** | `analytics/backtest/engine.py:75-79` wraps ReplayEngine; bar-by-bar loop |
| Circuit breaker for runaway loss | **Yes** | Daily loss limit + kill switch in RiskManager |
| Reconciliation broker vs internal | **Partial** | `application/oms/reconciliation_service.py`; auto_repair=False on CLI |

---

## PnL Calculation Precision

| Component | Type | Location |
|-----------|------|----------|
| RiskManager daily_pnl | Decimal | `application/oms/_internal/risk_manager.py:112` |
| Position notional | Decimal | `risk_manager.py:141-151` |
| BacktestEngine metrics | float/numpy | `analytics/backtest/engine.py:29-30` — acceptable for analytics, not OMS |

**Finding:** OMS path uses Decimal correctly. Analytics backtest uses numpy for performance metrics — acceptable if isolated from live OMS.

---

## Risk Limit Enforcement

| Gate | Bypassable? | Location |
|------|-------------|----------|
| Pre-trade risk in OrderManager | No (when RM configured) | `order_manager.py:286-298` |
| Placement gate (reconciliation) | Configurable | `order_manager.py:260-268` |
| Duplicate risk in broker (transport_only=False) | Yes if caller skips transport_only | `brokers/dhan/orders.py:262` |
| Kill switch | No | `risk_manager.py:233-236` |
| Daily PnL reset | Auto via scheduler | `application/oms/context.py:225-230` |

| Finding | Severity | Location |
|---------|----------|----------|
| authorize_risk_fail_open option in runtime | High | `runtime/trading_runtime_factory.py:49,57` — can fail-open risk |
| PHANTOM_CAPITAL_INR fallback | Medium | `application/oms/context.py:12` — used when no capital provider |

---

## Backtest-to-Live Leakage

| Check | Status | Evidence |
|-------|--------|----------|
| ReplayEngine bar-by-bar | Pass | `analytics/replay/engine.py` |
| BacktestEngine wraps ReplayEngine | Pass | `analytics/backtest/engine.py:75-79` — "same pipeline as live" |
| OMS integration in backtest optional | Pass | `BacktestEngine.__init__` accepts `trading_context`, `execution_adapter` |
| STRICT_EXECUTION_PARITY in CI | Pass | `.github/workflows/ci.yml:4,152` |
| Paper engine uses iloc[-1] for last bar | Review | `analytics/paper/engine.py:312,353` — point-in-time if df is sliced correctly |

---

## Order Lifecycle Correctness

| Scenario | Live (Dhan) | Live (Upstox) | Paper | Replay |
|----------|---------------|---------------|-------|--------|
| Partial fill qty | **Wrong** (cumulative) | **No WS path** | **Double apply** | Simulated via OMS |
| Slippage modeling | Broker truth | N/A | Simulated | Config in BacktestConfig |
| Idempotency on restart | **Broken** (in-memory ledger) | Same | Same | EventLog replay |

---

## Position Reconciliation

| Aspect | Status | Location |
|--------|--------|----------|
| ReconciliationService | Present | `application/oms/reconciliation_service.py` |
| Dhan reconciliation wired | Yes | `cli/services/oms_setup.py:143-165` |
| auto_repair=False on CLI | Yes | `oms_setup.py:162-165` — drift surfaced, not auto-fixed |
| Upstox reconciliation | Partial | `brokers/upstox/broker.py:237` — coupled to broker |

---

## Margin / Slippage / Commission

- Slippage configured in `BacktestConfig` (analytics layer)
- Live path uses broker-reported average_price on fills
- No explicit commission model in OMS — relies on broker truth

---

## Circuit Breaker for Runaway Strategies

| Mechanism | Location |
|-----------|----------|
| Kill switch in RiskManager | `application/oms/_internal/risk_manager.py` |
| Upstox broker kill switch | `brokers/upstox/kill_switch/adapter.py` |
| Orchestrator dry-run default | `runtime/trading_runtime_factory.py:63-65` — `ORCHESTRATOR_DRY_RUN=1` |
| Daily loss limit | `risk_manager.py:59,141+` |

---

## Top Findings (Capital Risk)

| # | Finding | Capital Impact | Location |
|---|---------|----------------|----------|
| 1 | Dhan partial fill double-count | Overstated position, wrong PnL | `brokers/dhan/websocket.py:991-1001` |
| 2 | Upstox fills never update OMS | Silent position drift | `brokers/upstox/websocket/portfolio_stream.py:127-138` |
| 3 | Paper double position apply | 2x position in paper (validates wrong strategy) | `brokers/paper/paper_orders.py:189-191` |
| 4 | Trade ledger not persisted | Duplicate fills after restart | `cli/services/oms_setup.py:150-157` |
| 5 | authorize_risk_fail_open | Orders pass without risk | `runtime/trading_runtime_factory.py:49` |
| 6 | Replay re-applies TRADE if ledger empty | Duplicate position on crash recovery | `application/oms/context.py:511-512` |

**Quant Score (internal): 4/10** — Risk gates exist but fill path bugs and persistence gaps make live capital unsafe.
