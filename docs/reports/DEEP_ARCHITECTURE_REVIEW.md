# Deep Architecture Review & Remediation Plan — TradeXV2

**Date:** June 23, 2026  
**Reviewers:** Principal Engineering Team  
**Scope:** Full codebase — brokers, domain, analytics, datalake, CLI, API, frontend

---

## Executive Summary

TradeXV2 is a multi-broker quantitative trading platform supporting Dhan, Upstox, and paper trading with backtesting, replay, and live execution capabilities. The architecture follows a ports-and-adapters pattern with a central EventBus for event-driven communication.

**Overall Production Readiness Score: 62/100**

| Area | Score | Target | Effort |
|------|-------|--------|--------|
| Architecture | 65 | 90 | High |
| Reliability | 55 | 85 | High |
| Risk Management | 50 | 90 | Critical |
| Execution | 70 | 95 | Medium |
| Market Data | 75 | 90 | Low |
| Portfolio | 60 | 85 | Medium |
| Testing | 70 | 90 | Medium |
| Observability | 55 | 85 | High |
| Security | 65 | 90 | Medium |
| Scalability | 50 | 80 | High |

---

## Phase 1: Architecture Mapping

### 1.1 Core Domains & Bounded Contexts

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TradeXV2 System                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Broker     │  │   Domain     │  │  Analytics   │             │
│  │   Context    │  │   Context    │  │   Context    │             │
│  │              │  │              │  │              │             │
│  │ • Dhan       │  │ • Entities   │  │ • Backtest   │             │
│  │ • Upstox     │  │ • Types      │  │ • Paper      │             │
│  │ • Paper      │  │ • Ports      │  │ • Replay     │             │
│  │ • Common     │  │ • Events     │  │ • Scanner    │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                 │                       │
│         └─────────────────┼─────────────────┘                       │
│                           │                                         │
│                    ┌──────▼───────┐                                 │
│                    │   EventBus   │                                 │
│                    │   (Central)  │                                 │
│                    └──────┬───────┘                                 │
│                           │                                         │
│  ┌────────────────────────┼────────────────────────┐               │
│  │                        │                        │               │
│  │  ┌──────────────┐  ┌──▼───────────┐  ┌─────────▼────┐         │
│  │  │   DataLake   │  │     CLI      │  │   API Server │         │
│  │  │   Context    │  │   Context    │  │   Context    │         │
│  │  │              │  │              │  │              │         │
│  │  │ • Parquet    │  │ • Commands   │  │ • FastAPI    │         │
│  │  │ • DuckDB     │  │ • Services   │  │ • WebSocket  │         │
│  │  │ • Catalog    │  │ • TUI        │  │ • REST       │         │
│  │  └──────────────┘  └──────────────┘  └──────────────┘         │
│  │                                                                │
│  └────────────────────────────────────────────────────────────────┘
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Frontend (React/Vite)                       │ │
│  │  • Chart • Sidebar • TopBar • MarketStream • Zustand Store    │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Dependency Graph

```
                    ┌─────────────────┐
                    │   Frontend      │
                    │   (React/Vite)  │
                    └────────┬────────┘
                             │ HTTP/WS
                    ┌────────▼────────┐
                    │   API Server    │
                    │   (FastAPI)     │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────▼────────┐ ┌──────▼───────┐ ┌───────▼──────┐
│    CLI Layer     │ │ DataLake     │ │  Analytics   │
│    (Commands)    │ │ Gateway      │ │  Engines     │
└─────────┬────────┘ └──────┬───────┘ └───────┬──────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                    ┌────────▼────────┐
                    │  TradingContext │
                    │  (Composition)  │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────▼────────┐ ┌──────▼───────┐ ┌───────▼──────┐
│   OrderManager   │ │ PositionMgr  │ │  RiskManager │
│   (OMS)          │ │              │ │              │
└─────────┬────────┘ └──────┬───────┘ └───────┬──────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                    ┌────────▼────────┐
                    │    EventBus     │
                    │   (Central)     │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────▼────────┐ ┌──────▼───────┐ ┌───────▼──────┐
│   Dhan Gateway   │ │ Upstox GW    │ │  Paper GW    │
│   (Broker)       │ │              │ │              │
└──────────────────┘ └──────────────┘ └──────────────┘
```

### 1.3 Runtime Execution Flow

```
Signal → StrategyPipeline → ScannerRunner → Candidate
                                              │
                                              ▼
                                    StrategyEvaluator
                                              │
                                              ▼
                                        Signal (is_actionable)
                                              │
                                              ▼
                                    TradingOrchestrator
                                              │
                                              ▼
                                    ExecutionService
                                              │
                              ┌───────────────┼───────────────┐
                              │               │               │
                              ▼               ▼               ▼
                        LiveOMSAdapter   PaperOMSAdapter  ReplayOMSAdapter
                              │               │               │
                              ▼               ▼               ▼
                        OrderManager    OrderManager    OrderManager
                              │               │               │
                              ▼               ▼               ▼
                        GatewaySubmit   SimulatedFill  SimulatedFill
                              │               │               │
                              ▼               ▼               ▼
                        Broker API      Paper Fill     Replay Fill
```

### 1.4 Event Flow Diagram

```
                    ┌─────────────────────────────────────┐
                    │            EventBus                  │
                    │  ┌─────────────────────────────────┐ │
                    │  │ TICK • QUOTE • DEPTH_20/200    │ │
                    │  │ ORDER_PLACED • ORDER_UPDATED   │ │
                    │  │ ORDER_CANCELLED • ORDER_REJECTED│ │
                    │  │ TRADE • TRADE_APPLIED           │ │
                    │  │ RISK_APPROVED • RISK_REJECTED   │ │
                    │  │ POSITION_OPENED • POSITION_CLOSED│ │
                    │  │ POSITION_UPDATED                │ │
                    │  └─────────────────────────────────┘ │
                    └──────────────┬──────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
    OrderManager            PositionManager           AlertingEngine
    (on_order_update)       (on_trade_applied)        (evaluate_all)
    (on_trade)              (on_trade)                 (threshold checks)
          │                        │
          ▼                        ▼
    AuditLogger             EventMetrics
    StateValidator          DeadLetterQueue
    PositionUpdater         ProcessedTradeRepository
```

---

## Phase 2: Root Cause Analysis

### 2.1 Architecture Issues

#### ISSUE-01: Duplicate Domain Types (CRITICAL)
**Location:** `domain/entities.py` vs `brokers/common/core/domain.py`

**Current Design:** Two parallel domain model hierarchies exist:
- `domain/entities.py`: Canonical domain types (Order, Position, Trade, Quote, etc.)
- `brokers/common/core/domain.py`: Broker-common domain types (Order, Position, Trade, etc.)

**Problem:** Both define `Order`, `Position`, `Trade` with similar but not identical fields. Import direction is inconsistent — some modules import from `domain`, others from `brokers.common.core.domain`. This creates confusion about which is the source of truth.

**Root Cause:** The `domain/` package was added later as a Clean Architecture layer, but the existing `brokers/common/core/domain.py` was never migrated away. Both coexist.

**Impact:** 
- Import confusion across 50+ files
- Serialization/deserialization mismatches
- Testing complexity (which Order is this?)

**Risk Level:** HIGH  
**Cost of Keeping:** High (ongoing confusion, bugs)  
**Cost of Fixing:** Medium (rename + re-import)

**Proposed Fix:** Consolidate to single source at `domain/entities.py`. Rename `brokers/common/core/domain.py` to `brokers/common/core/broker_domain.py` and create thin adapter imports.

---

#### ISSUE-02: TradingContext God Container (HIGH)
**Location:** `brokers/common/oms/context.py`

**Current Design:** `TradingContext` holds:
- EventBus, EventLog
- OrderManager, PositionManager, RiskManager
- ProcessedTradeRepository
- ReconciliationService
- LifecycleManager integration
- AsyncEventBus support
- Orchestrator reference

**Problem:** Violates Single Responsibility Principle. Changing any manager requires touching TradingContext. Testing requires constructing all dependencies.

**Root Cause:** Organic growth — started as a simple wire-up container, accumulated responsibilities over time.

**Impact:**
- 200+ line constructor
- 15+ properties
- Difficult to test in isolation
- Changes to one manager ripple through context

**Risk Level:** MEDIUM  
**Cost of Keeping:** Medium (test complexity, change ripple)  
**Cost of Fixing:** Medium (extract sub-contexts)

**Proposed Fix:** Extract `OMSContext` (OrderManager + RiskManager + PositionManager), `EventContext` (EventBus + DLQ + Metrics), `LifecycleContext` (ReconciliationService + Schedulers).

---

#### ISSUE-03: EventBus Synchronous Bottleneck (HIGH)
**Location:** `brokers/common/event_bus/event_bus.py`

**Current Design:** Synchronous EventBus with optional AsyncEventBus as opt-in. All handlers execute in the publisher's thread under a lock.

**Problem:** 
- Handler failures block the publish loop
- No backpressure mechanism
- AsyncEventBus is opt-in, not default
- Thread contention under high tick rates

**Root Cause:** Designed for simplicity; async was added later as an afterthought.

**Impact:**
- Handler failures cascade
- High tick rates cause lock contention
- AsyncEventBus migration is incomplete

**Risk Level:** HIGH  
**Cost of Keeping:** High (performance, reliability)  
**Cost of Fixing:** High (async migration)

**Proposed Fix:** Make AsyncEventBus the default. Sync EventBus becomes legacy fallback. Add handler timeout protection.

---

#### ISSUE-04: RiskManager Dual Interface (MEDIUM)
**Location:** `brokers/common/oms/_internal/risk_manager.py`

**Current Design:** Accepts either `capital_fn: Callable[[], Decimal]` or `capital_provider: CapitalProvider`. Legacy adapter wraps `capital_fn` in a `LegacyCapitalAdapter`.

**Problem:** Two interfaces for the same concern. Legacy `capital_fn` is still used in many places.

**Root Cause:** Incremental migration from function-based to protocol-based capital access.

**Impact:**
- Confusion about which to use
- Legacy path lacks proper lifecycle management

**Risk Level:** MEDIUM  
**Cost of Keeping:** Low  
**Cost of Fixing:** Low (remove legacy path)

---

#### ISSUE-05: PositionManager Dual Handler (MEDIUM)
**Location:** `brokers/common/oms/position_manager.py`

**Current Design:** Has both `on_trade()` and `on_trade_applied()` handlers. `on_trade` subscribes to raw TRADE events; `on_trade_applied` subscribes to TRADE_APPLIED events.

**Problem:** Two paths to the same outcome. `on_trade` bypasses OMS idempotency.

**Root Cause:** Backward compatibility — `on_trade` was original, `on_trade_applied` was added for production safety.

**Impact:**
- Potential double-counting if wrong handler is subscribed
- Confusion about which to use

**Risk Level:** HIGH (in production)  
**Cost of Keeping:** High (double-counting risk)  
**Cost of Fixing:** Low (deprecate `on_trade`)

---

### 2.2 Quant Trading Issues

#### ISSUE-06: Limited Risk Management (CRITICAL)
**Current Checks:**
- Kill switch (binary)
- Daily loss limit (% of capital)
- Per-symbol position limit (% of capital)
- Gross exposure limit (% of capital)

**Missing:**
- Per-strategy risk limits
- Sector concentration limits
- Correlation-based risk
- Drawdown-based position sizing
- Volatility-adjusted position sizing
- Time-based risk (e.g., no new positions in last 30 min)
- News/event-based risk halts

**Risk Level:** CRITICAL for live trading

---

#### ISSUE-07: No Portfolio-Level Risk (HIGH)
**Current:** Risk checks are per-order, not per-portfolio.

**Missing:**
- Portfolio VaR/CVaR
- Beta-weighted exposure
- Greeks-based options risk
- Multi-leg spread risk
- Margin utilization tracking

**Risk Level:** HIGH for options trading

---

#### ISSUE-08: Backtesting Slippage Model (MEDIUM)
**Current:** Simple percentage-based slippage (`slippage_pct`).

**Missing:**
- Volume-based slippage
- Market impact model
- Spread-based slippage
- Time-of-day slippage variation

**Risk Level:** MEDIUM (affects backtest accuracy)

---

### 2.3 Reliability Issues

#### ISSUE-09: No Circuit Breaker Pattern (HIGH)
**Current:** `BrokerCapabilities` has `circuit_breaker_states` in observability, but no actual circuit breaker logic.

**Missing:**
- Per-broker circuit breakers
- Per-endpoint circuit breakers
- Half-open state recovery
- Automatic fallback to degraded mode

**Risk Level:** HIGH (single broker failure cascades)

---

#### ISSUE-10: EventBus Handler Failure Handling (MEDIUM)
**Current:** Failures are logged, counted, and dead-lettered. But no retry mechanism.

**Missing:**
- Configurable retry with backoff
- Handler-level circuit breakers
- Poison message detection
- Replay from DLQ

**Risk Level:** MEDIUM (lost events in production)

---

### 2.4 Performance Issues

#### ISSUE-11: Sequential Data Loading (MEDIUM)
**Current:** `DataLakeGateway.history_batch()` falls back to sequential read on DuckDB failure.

**Missing:**
- Concurrent parquet reads
- Memory-mapped files
- Incremental loading
- Column pruning

**Risk Level:** MEDIUM (affects backtest speed)

---

#### ISSUE-12: Frontend No Error Boundaries (MEDIUM)
**Current:** No React error boundaries. Component failures crash the entire app.

**Missing:**
- Error boundary components
- Graceful degradation
- Retry logic for failed fetches
- Loading skeleton states

**Risk Level:** MEDIUM (UX degradation)

---

## Phase 3: Target Architecture Design

### 3.1 Target State Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TradeXV2 v2.0                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Presentation Layer                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │  │
│  │  │   React UI   │  │   CLI/TUI    │  │   API Server │      │  │
│  │  │   (Vite)     │  │   (Rich)     │  │   (FastAPI)  │      │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Application Layer                         │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │  │
│  │  │  Orchestrator │  │  Execution   │  │  Analytics   │      │  │
│  │  │  Service      │  │  Service     │  │  Service     │      │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Domain Layer                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │  │
│  │  │  OMS         │  │  Risk        │  │  Portfolio   │      │  │
│  │  │  (Order/Pos) │  │  Manager     │  │  Manager     │      │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │  │
│  │  │  EventBus    │  │  State       │  │  Event       │      │  │
│  │  │  (Async)     │  │  Machines    │  │  Store       │      │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Infrastructure Layer                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │  │
│  │  │  Broker      │  │  DataLake    │  │  Monitoring  │      │  │
│  │  │  Adapters    │  │  (Parquet)   │  │  (Prometheus)│      │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Target Event Architecture

```python
# Event Contracts (Target)
@dataclass(frozen=True)
class DomainEvent:
    event_type: EventType
    timestamp: datetime
    payload: dict
    metadata: EventMetadata  # correlation_id, causation_id, version

class EventType(str, Enum):
    # Market Data
    TICK = "TICK"
    QUOTE = "QUOTE"
    DEPTH = "DEPTH"
    CANDLE = "CANDLE"
    
    # Order Lifecycle
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACKNOWLEDGED = "ORDER_ACKNOWLEDGED"
    ORDER_PARTIAL_FILL = "ORDER_PARTIAL_FILL"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    
    # Trade
    TRADE = "TRADE"
    TRADE_SETTLED = "TRADE_SETTLED"
    
    # Position
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_REDUCED = "POSITION_REDUCED"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_REVERSED = "POSITION_REVERSED"
    
    # Risk
    RISK_CHECK_PASSED = "RISK_CHECK_PASSED"
    RISK_CHECK_FAILED = "RISK_CHECK_FAILED"
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    
    # Portfolio
    PORTFOLIO_RECONCILED = "PORTFOLIO_RECONCILED"
    MARGIN_WARNING = "MARGIN_WARNING"
    
    # System
    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    HEALTH_CHECK = "HEALTH_CHECK"
```

### 3.3 Target State Machines

#### Order Lifecycle
```
                    ┌─────────────┐
                    │  SUBMITTED  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
          ┌────────│ ACKNOWLEDGED │────────┐
          │        └──────┬──────┘        │
          │               │               │
    ┌─────▼─────┐  ┌──────▼──────┐  ┌────▼────┐
    │ REJECTED  │  │PARTIAL_FILL │  │CANCELLED│
    └───────────┘  └──────┬──────┘  └─────────┘
                          │
                   ┌──────▼──────┐
                   │   FILLED    │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │  SETTLED    │
                   └─────────────┘
```

#### Position Lifecycle
```
    ┌───────┐
    │ FLAT  │
    └───┬───┘
        │ open
    ┌───▼───┐     add      ┌─────────┐
    │ OPEN  │──────────────►│  OPEN   │
    └───┬───┘               └────┬────┘
        │ partial close          │ partial close
    ┌───▼────┐              ┌────▼────┐
    │REDUCED │◄─────────────►│REDUCED  │
    └───┬────┘   add back    └────┬────┘
        │ full close              │ full close
    ┌───▼───┐                ┌────▼───┐
    │ CLOSED│                │CLOSED  │
    └───┬───┘                └────┬───┘
        │ reverse                  │ reverse
    ┌───▼────┐               ┌────▼────┐
    │REVERSED│──────────────►│REVERSED │
    └───┬────┘               └────┬────┘
        │ full close               │ full close
    ┌───▼───┐                 ┌────▼───┐
    │ FLAT  │                 │  FLAT  │
    └───────┘                 └────────┘
```

---

## Phase 4: Refactoring Strategy

### Phase A: Safe Fixes (No Behavior Changes) — 2 weeks
1. Remove duplicate imports between `domain/` and `brokers/common/core/`
2. Add deprecation warnings to legacy interfaces
3. Consolidate test fixtures
4. Add type hints to all public APIs

### Phase B: Code Cleanup — 3 weeks
1. Remove dead code and unused abstractions
2. Consolidate duplicate domain types
3. Remove legacy `capital_fn` path
4. Deprecate `PositionManager.on_trade()` handler

### Phase C: Architecture Extraction — 4 weeks
1. Extract `OMSContext` from `TradingContext`
2. Extract `EventContext` from `TradingContext`
3. Introduce `PortfolioManager` as separate bounded context
4. Introduce `RiskService` with proper protocols

### Phase D: Event-Driven Migration — 5 weeks
1. Make `AsyncEventBus` the default
2. Add event versioning and schema validation
3. Implement event replay from persistent store
4. Add proper retry with backoff in handlers

### Phase E: Production Hardening — 4 weeks
1. Implement circuit breaker pattern
2. Add Prometheus metrics and alerting
3. Implement health check endpoints
4. Add chaos testing framework

---

## Phase 5: Top 50 Engineering Fixes (Ranked by Impact)

### CRITICAL (Must Fix Before Live Trading)

| # | Issue | File | Risk | Effort |
|---|-------|------|------|--------|
| 1 | Duplicate domain types | `domain/entities.py` vs `brokers/common/core/domain.py` | HIGH | Medium |
| 2 | No portfolio-level risk | `brokers/common/oms/_internal/risk_manager.py` | CRITICAL | High |
| 3 | PositionManager dual handler | `brokers/common/oms/position_manager.py` | HIGH | Low |
| 4 | No circuit breaker | `brokers/common/resilience/` | HIGH | High |
| 5 | EventBus sync bottleneck | `brokers/common/event_bus/event_bus.py` | HIGH | High |

### HIGH Priority

| # | Issue | File | Risk | Effort |
|---|-------|------|------|--------|
| 6 | TradingContext god container | `brokers/common/oms/context.py` | MEDIUM | Medium |
| 7 | RiskManager dual interface | `brokers/common/oms/_internal/risk_manager.py` | MEDIUM | Low |
| 8 | No event retry mechanism | `brokers/common/event_bus/event_bus.py` | MEDIUM | Medium |
| 9 | CLI main.py monolith | `cli/main.py` | MEDIUM | Medium |
| 10 | Frontend no error boundaries | `frontend/src/App.tsx` | MEDIUM | Low |

### MEDIUM Priority

| # | Issue | File | Risk | Effort |
|---|-------|------|------|--------|
| 11 | Sequential data loading | `datalake/gateway.py` | MEDIUM | Medium |
| 12 | No slippage model | `analytics/paper/engine.py` | LOW | Medium |
| 13 | Missing Greeks in options | `analytics/options/options_analytics.py` | LOW | Low |
| 14 | No proper logging config | `brokers/common/logging_config.py` | LOW | Low |
| 15 | Thread safety in ParquetStore | `datalake/store/parquet_store.py` | LOW | Low |

---

## Phase 6: Production Readiness Assessment

### 6.1 Backtesting Readiness: 75/100
- ✅ Historical data loading works
- ✅ Basic backtest engine functional
- ✅ Paper trading engine works
- ⚠️ Slippage model is simplistic
- ⚠️ No proper commission model
- ❌ No walk-forward optimization
- ❌ No proper attribution analysis

### 6.2 Paper Trading Readiness: 70/100
- ✅ Paper gateway functional
- ✅ Basic order routing works
- ✅ Position tracking works
- ⚠️ No proper fill simulation
- ⚠️ No market hours enforcement
- ❌ No proper latency simulation
- ❌ No proper queue position simulation

### 6.3 Live Trading Readiness: 55/100
- ✅ Broker connections work
- ✅ Basic order placement works
- ✅ Event bus functional
- ⚠️ Risk management is basic
- ⚠️ No circuit breaker
- ❌ No proper reconciliation
- ❌ No proper failover
- ❌ No proper audit trail

### 6.4 Monitoring Readiness: 45/100
- ✅ Basic logging works
- ✅ Event metrics exist
- ⚠️ No Prometheus integration
- ⚠️ No alerting rules
- ❌ No dashboards
- ❌ No tracing

---

## Phase 7: Recommended Next Steps

### Immediate (This Week)
1. **Consolidate domain types** — Pick `domain/entities.py` as single source, update all imports
2. **Deprecate PositionManager.on_trade()** — Add warnings, update all subscribers
3. **Add error boundaries to frontend** — React error boundary component

### Short Term (Next 2 Weeks)
1. **Implement circuit breaker** — Per-broker, per-endpoint
2. **Add event retry mechanism** — Configurable backoff
3. **Extract OMSContext** — Reduce TradingContext responsibilities

### Medium Term (Next Month)
1. **Make AsyncEventBus default** — Migrate all handlers
2. **Add portfolio-level risk** — VaR, Greeks, correlation
3. **Implement proper reconciliation** — Broker vs local state

### Long Term (Next Quarter)
1. **Full async migration** — All I/O operations async
2. **Event sourcing** — Persistent event store for replay
3. **Multi-strategy support** — Strategy-level risk and allocation

---

## Appendix A: File-by-File Analysis

### Domain Layer
| File | Status | Issues |
|------|--------|--------|
| `domain/entities.py` | ✅ Good | Canonical source, well-structured |
| `domain/types.py` | ✅ Good | Clean enum definitions |
| `domain/exchange_segments.py` | ✅ Good | Proper alias resolution |
| `domain/ports/` | ⚠️ Needs Work | Some protocols unused |

### Broker Layer
| File | Status | Issues |
|------|--------|--------|
| `brokers/common/gateway.py` | ✅ Good | Clean ABC, proper capabilities |
| `brokers/dhan/gateway.py` | ⚠️ Needs Work | Too many responsibilities |
| `brokers/upstox/gateway.py` | ⚠️ Needs Work | Adapter pattern inconsistent |
| `brokers/paper/paper_gateway.py` | ✅ Good | Simple, functional |

### OMS Layer
| File | Status | Issues |
|------|--------|--------|
| `brokers/common/oms/order_manager.py` | ✅ Good | Thread-safe, idempotent |
| `brokers/common/oms/position_manager.py` | ⚠️ Needs Work | Dual handler issue |
| `brokers/common/oms/_internal/risk_manager.py` | ⚠️ Needs Work | Dual interface |
| `brokers/common/oms/context.py` | ❌ Needs Refactor | God container |

### Event Layer
| File | Status | Issues |
|------|--------|--------|
| `brokers/common/event_bus/event_bus.py` | ⚠️ Needs Work | Sync bottleneck |
| `brokers/common/event_bus/async_event_bus.py` | ✅ Good | Proper async design |
| `brokers/common/event_bus/dead_letter_queue.py` | ✅ Good | Simple, effective |

### Analytics Layer
| File | Status | Issues |
|------|--------|--------|
| `analytics/backtest/engine.py` | ✅ Good | Functional |
| `analytics/paper/engine.py` | ⚠️ Needs Work | Legacy fill path |
| `analytics/replay/engine.py` | ⚠️ Needs Work | Parity concerns |
| `analytics/scanner/` | ✅ Good | Well-structured |

### DataLake Layer
| File | Status | Issues |
|------|--------|--------|
| `datalake/gateway.py` | ✅ Good | DuckDB integration |
| `datalake/store/parquet_store.py` | ✅ Good | Proper caching |
| `datalake/catalog.py` | ✅ Good | DuckDB metadata |
| `datalake/loader.py` | ✅ Good | Atomic writes |

### CLI Layer
| File | Status | Issues |
|------|--------|--------|
| `cli/main.py` | ⚠️ Needs Work | Monolith, inline handlers |
| `cli/services/broker_service.py` | ✅ Good | Proper lifecycle |
| `cli/commands/` | ⚠️ Needs Work | Inconsistent patterns |

### Frontend Layer
| File | Status | Issues |
|------|--------|--------|
| `frontend/src/App.tsx` | ⚠️ Needs Work | No error boundaries |
| `frontend/src/components/` | ✅ Good | Clean components |
| `frontend/src/hooks/` | ✅ Good | Proper custom hooks |
| `frontend/src/api/client.ts` | ⚠️ Needs Work | Mock fallbacks |

---

## Appendix B: Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Duplicate domain types cause bugs | HIGH | MEDIUM | Consolidate to single source |
| EventBus handler failure cascades | MEDIUM | HIGH | Add circuit breaker, retry |
| Risk management bypass | LOW | CRITICAL | Enforce all orders through OMS |
| Broker connection failure | MEDIUM | HIGH | Add circuit breaker, fallback |
| Data corruption in Parquet | LOW | MEDIUM | Atomic writes already in place |
| Frontend crash on error | HIGH | LOW | Add error boundaries |
| Memory leak in event handlers | LOW | HIGH | Add handler timeout, monitoring |
| Thread deadlock in OMS | LOW | CRITICAL | RLock pattern, timeout enforcement |

---

## Appendix C: Migration Checklist

### Phase A: Safe Fixes
- [ ] Audit all imports between `domain/` and `brokers/common/core/`
- [ ] Add deprecation warnings to legacy interfaces
- [ ] Consolidate test fixtures
- [ ] Add type hints to all public APIs
- [ ] Run full test suite to verify no behavior changes

### Phase B: Code Cleanup
- [ ] Remove dead code identified by linter
- [ ] Consolidate `domain/entities.py` as single source
- [ ] Remove legacy `capital_fn` path
- [ ] Deprecate `PositionManager.on_trade()` handler
- [ ] Update all documentation

### Phase C: Architecture Extraction
- [ ] Extract `OMSContext` from `TradingContext`
- [ ] Extract `EventContext` from `TradingContext`
- [ ] Introduce `PortfolioManager` bounded context
- [ ] Introduce `RiskService` with proper protocols
- [ ] Update all composition roots

### Phase D: Event-Driven Migration
- [ ] Make `AsyncEventBus` default
- [ ] Add event versioning
- [ ] Implement event replay
- [ ] Add handler retry with backoff
- [ ] Update all event subscribers

### Phase E: Production Hardening
- [ ] Implement circuit breaker pattern
- [ ] Add Prometheus metrics
- [ ] Add alerting rules
- [ ] Add health check endpoints
- [ ] Add chaos testing framework
- [ ] Production readiness gate

---

*Document generated by TradeXV2 Architecture Review*  
*Last updated: June 23, 2026*
