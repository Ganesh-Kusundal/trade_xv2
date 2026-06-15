# Pre-Production Architectural Review & Deployment Certification

**Project:** TradeXV2  
**Review date:** 2026-06-15  
**Codebase:** 313 Python source files (~42,000 LOC), 137 test files (~18,500 LOC), plus a React/TypeScript frontend  
**Verdict:** **NO-GO** (conditional — see §12)

---

## 1. System Intent

TradeXV2 is a **Python-based, broker-agnostic algorithmic trading framework for Indian exchanges (NSE/BSE/MCX)**. It provides a live DhanHQ adapter, a partial Upstox adapter, a paper-trading adapter, a frozen `MarketDataGateway` contract, an in-process order management system (OMS) with idempotency and event-bus position tracking, a Rich/Textual CLI diagnostic terminal, a local Parquet datalake, and a large analytics/research engine (backtest, scanner, options Greeks, replay, sector rotation, etc.). The system is intended to place and monitor orders, stream market data, and run quantitative strategies.

---

## 2. Architecture Reconstruction

### 2.1 Module inventory

| Package / module | Files (src/test) | Status | Responsibility |
|---|---|---|---|
| `brokers/common/core/domain.py` | 1 / 0 | **ACTIVE, CANONICAL** | Single source of truth for `Order`, `Position`, `Holding`, `Trade`, `Side`, `OrderStatus`, etc. |
| `brokers/common/oms/` | 7 / 4 | **ACTIVE IN CODE, DISCONNECTED IN PRODUCTION** | `OrderManager`, `PositionManager`, `RiskManager`, `TradingContext`, `ReconciliationService`. |
| `brokers/common/event_bus/` | 4 / 2 | **ACTIVE IN CODE, NOT SHARED WITH LIVE GATEWAY** | Pub/sub, `ProcessedTradeRepository`, DLQ, `EventMetrics`. |
| `brokers/common/lifecycle/` | 1 / 1 | **ACTIVE, NOT WIRED** | `LifecycleManager` / `ManagedService` protocol. |
| `brokers/common/resilience/` | 6 / 4 | **ACTIVE** | Rate limiter, circuit breaker, retry, backoff — tested. |
| `brokers/common/api/ports.py` | 1 / 0 | **PARTIAL** | SPI ports; many Upstox-side ports unimplemented. |
| `brokers/common/core/{models,enums,broker,facade,connection,schemas}.py` | 6 / 4 | **DEPRECATED / DEAD** | Duplicates of `domain.py` or unused ABCs. |
| `brokers/common/data_contracts.py` | 1 / 0 | **OBSOLETE** | Re-exports `domain.py` plus column lists; only consumer is `intelligent_gateway.py`. |
| `brokers/common/observability/{metrics,logging}.py` | 2 / 1 | **DEAD** | `MetricsCollector` (buggy), `StructuredLogger` — no production callers. |
| `brokers/common/event_log.py` | 1 / 1 | **ACTIVE ONLY IN TESTS** | Used by `TradingContext` but `event_log` is never passed in production. |
| `brokers/common/intelligent_gateway.py` | 1 / 0 | **ACTIVE, DANGEROUS** | Dual-broker router; 17 silent `except Exception: pass` fallbacks. |
| `brokers/dhan/` | ~20 / 28 | **ACTIVE (PORTIONS)** | Live broker adapter; order placement is hardened, market/options/futures modules untested. |
| `brokers/dhan/{adapters,auth,instruments,mapper,market_data,orders,websocket,runtime-dev}/` | 8 dirs | **EMPTY PLACEHOLDERS** | 0 non-`__init__.py` files. |
| `brokers/upstox/` | ~75 / 22 | **PARTIAL** | Many adapters; no contract tests; `get_trade_book()` returns `[]`; uses deprecated `BrokerConnection`. |
| `brokers/paper/` | 5 / 2 | **ACTIVE** | In-memory simulator. |
| `cli/` | ~49 / 5 | **ACTIVE, FRAGILE** | Entry point, commands, services; `main.py` has 0 tests. |
| `datalake/` | 15 / 11 | **ACTIVE** | `TradeJournal` and Parquet gateway; gateway has 0 tests. |
| `analytics/` | ~47 / 29 | **ACTIVE** | Research/backtest code; test tree fragmented across `analytics/tests/` and `tests/analytics/`. |
| `frontend/` | 23 tsx / 0 | **ACTIVE, UNTESTED** | Vite/React widget workspace; 0 tests, no backend exists. |
| `tests/e2e/`, `tests/regression/` | 2 / 0 | **EMPTY** | Only `__init__.py`. |

### 2.2 Ownership map (verified by `grep` of definitions and callers)

| Concept | Canonical owner | Other copies | Production state |
|---|---|---|---|
| `Order` | `brokers.common.core.domain.Order` | `models.py`, `dhan/domain.py` re-export | `domain.py` is used by Dhan and OMS; `models.py` still used by Upstox. |
| `Position` / `Holding` / `Trade` | `domain.py` | `models.py` | Same as above. |
| `OrderStatus` | `domain.py::OrderStatus.normalize()` | `enums.py` duplicate | Dhan adapter now uses `normalize()` — previous DH-906 root cause is fixed. |
| `Side` / `OrderSide` | `domain.py::Side` | `dhan/domain.py` alias, `TransactionType` in `enums.py` | Aliases tolerated; `TransactionType` duplicate remains. |
| `OrderType` / `ProductType` / `Validity` | `domain.py` | `enums.py` duplicate | Upstox still imports `enums.py`. |
| `Exchange` | `dhan/domain.py::Exchange` (5/7 values) | `core/enums.py::ExchangeSegment` (5 values), `dhan/segments.py` string map | 3 representations. |
| `Instrument` | `dhan/domain.py::Instrument` | `core/instruments.py::Instrument` | Two incompatible instrument types. |
| `Quote` / `MarketDepth` | `dhan/domain.py` + `domain.py` (`DepthLevel` only) | `models.py` Pydantic copies | No single canonical `Quote`/`MarketDepth`. |
| `KillSwitch` | `RiskConfig.kill_switch` (in-process) | `KillSwitchPort`, `Connection.Capability.KILL_SWITCH`, `UpstoxKillSwitchAdapter`, Dhan `/killswitch` API | 4 different meanings, no unified owner. |
| `ReconciliationService` | `brokers.common.oms.reconciliation_service.ReconciliationService` | `brokers.dhan.reconciliation.DhanReconciliationService` | Two classes with overlapping names. |
| `RiskManager` | `brokers.common.oms.risk_manager.RiskManager` | Dhan `OrdersAdapter._risk_manager` | Central manager is never fed live PnL; `set_kill_switch` dead. |
| `Metrics` | `EventMetrics` (used by bus/OMS) | `MetricsCollector` (dead) | Two parallel systems. |
| `Token refresh` | `TokenRefreshScheduler` + `DhanHttpClient` 401 handler + `AuthManager` | — | 3 timing strategies, one shared lock. |

### 2.3 Dependency / execution graph

```text
cli/main.py  (430 LOC, 22 elif blocks, 0 tests)
    │ loads .env.local via python-dotenv (override=True)
    │
    ▼
cli/services/broker_service.py  (loads .env.local via python-dotenv again)
    │  BrokerFactory.create(env_path=.env.local, load_instruments=True)
    │  create_trading_context(reconciliation_service=...)
    │  ▲ but does NOT call attach_lifecycle()
    ▼
brokers/dhan/factory.py  (loads .env.local via CUSTOM parser)
    │  AuthManager + TokenStateStore
    │  ONE CircuitBreaker("dhan-api") for ALL endpoints
    │  DhanHttpClient
    │  DhanConnection ──► OrdersAdapter (with its own IdempotencyCache)
    │  TokenRefreshScheduler ──► auto-start() when lifecycle=None
    ▼
BrokerGateway  (delegates to connection adapters)
    │  market_data / orders / portfolio / options / futures / historical
    ▼
Live Dhan REST + WebSocket
```

**Architectural defect:** The CLI constructs a `TradingContext` (central OMS) **and** a `BrokerGateway`, but they are not integrated. The gateway's `event_bus` is `None`, so WebSocket fill events never reach the context's OMS. `OmsService.place_order()` calls the gateway directly, bypassing `OrderManager`. Reconciliation is constructed but never started because `attach_lifecycle()` is never called.

---

## 3. Active Execution Paths

| # | Path | Verified | Thread-safe | Tested |
|---|---|---|---|---|
| 1 | CLI help / no-gateway commands (`journal`, `views`) | ✅ | N/A | ❌ |
| 2 | `broker`, `account`, `holdings`, `positions`, `orders`, `trades`, `oms` summary via CLI | ✅ | ✅ (per-call) | ⚠️ command-level only |
| 3 | `quote`, `depth`, `option-chain`, `futures`, `historical` via CLI | ✅ | ✅ (rate limiter) | ⚠️ command-level only |
| 4 | `stream` / `websocket` via CLI | ✅ | ✅ (RLock) | ⚠️ no e2e reconnect test |
| 5 | Dhan TOTP token acquisition at startup | ✅ | ✅ | ✅ `test_factory_auth.py` |
| 6 | Background token refresh (`TokenRefreshScheduler` auto-started) | ✅ | ✅ (per-instance lock) | ✅ |
| 7 | `OrdersAdapter.place_order` (validation → idempotency → risk → HTTP → event) | ✅ | ✅ (RLock) | ✅ 17+ unit tests |
| 8 | `OrderManager.place_order` / `on_trade` (in-process OMS path) | ✅ | ✅ (RLock) | ✅ 25+ tests |
| 9 | `EventBus.publish` → handler dispatch + DLQ | ✅ | ✅ | ✅ |
| 10 | `PositionManager.on_trade_applied` | ✅ | ✅ | ✅ |
| 11 | `TradingContext` construction (BrokerService) | ✅ | N/A | ⚠️ not a test target |
| 12 | `ReconciliationService` timer loop | ✅ | ✅ | ✅ |
| 13 | `DataLakeGateway.history` (Parquet read + silent resample fallback) | ⚠️ | ✅ | ❌ no `test_gateway.py` |
| 14 | `IntelligentGateway` dual-broker routing | ⚠️ verified by reading | ❌ silent fallbacks | ❌ 0 tests |

---

## 4. Dead / Legacy / Duplicate Components

### 4.1 DELETE

| Component | File | Why |
|---|---|---|
| `Broker` ABC (deprecated) | `brokers/common/core/broker.py` | Marked deprecated; zero subclasses. |
| `BrokerFacade` | `brokers/common/core/facade.py` | Marked deprecated; zero callers. |
| Pydantic `models.py` | `brokers/common/core/models.py` | DEPRECATED; duplicates `domain.py`; still used only by Upstox adapter + SPI tests. |
| `enums.py` duplicate enums | `brokers/common/core/enums.py` | DEPRECATED; all enums duplicated in `domain.py`. |
| `connection.py` | `brokers/common/core/connection.py` | `BrokerConnection` ABC deprecated; Upstox still uses it. |
| `schemas.py` | `brokers/common/core/schemas.py` | Own docstring says no module imports it. |
| `data_contracts.py` | `brokers/common/data_contracts.py` | Re-exports `domain.py`; only consumer is `intelligent_gateway.py`. |
| `StructuredLogger` | `brokers/common/observability/logging.py` | Zero production callers. |
| `MetricsCollector` / `OperationMetrics` | `brokers/common/observability/metrics.py` | Dead; `p95` is wrong; test freezes the bug. |
| `TradexTuiApp` dead path | `cli/main.py` import | Constructed only in `test_tui.py`; not in production CLI. |
| 8 empty Dhan dirs | `brokers/dhan/{adapters,auth,instruments,mapper,market_data,orders,websocket,runtime-dev}` | 0 non-`__init__.py` files. |
| Root `ind_nifty*.csv` files | `ind_nifty100list.csv`, etc. | Zero Python consumers; duplicates `data/universes/nifty*.csv`. |
| Singular `broker/` alias | (README only) | Directory does not exist; README is stale. |
| `tests/e2e/`, `tests/regression/` | empty dirs | Only `__init__.py`. |

### 4.2 MERGE

| Concept | Owners | Target |
|---|---|---|
| `Order` / `Position` / `Holding` / `Trade` | `domain.py` + `models.py` | Single `domain.py`. |
| `OrderStatus` / `OrderType` / `ProductType` / `Validity` / `Side` | `domain.py` + `enums.py` + Dhan aliases | Single `domain.py`. |
| `Exchange` / `ExchangeSegment` | Dhan `Exchange`, `enums.ExchangeSegment`, `dhan/segments.py` | Single enum + class methods. |
| `Instrument` | `core/instruments.py` + `dhan/domain.py` | Extend canonical with `security_id`. |
| `ReconciliationService` | `oms/reconciliation_service.py` + `dhan/reconciliation.py` | One class name. |
| `KillSwitch` | 4 representations | One in-process `RiskConfig.kill_switch` + one broker `KillSwitchPort`. |
| `.env.local` loaders | `factory.py` custom + `main.py` dotenv + `broker_service.py` dotenv | One loader. |
| Analytics test tree | `analytics/tests/` + `tests/analytics/` | Consolidate. |
| Upstox factories | `__init__.py` `__new__` + `factory.py` | One factory. |

### 4.3 REWRITE

| Component | Why |
|---|---|
| `cli/main.py` | 430 LOC, 22 `elif` blocks; 0 tests; violates single responsibility. Replace with command registry. |
| `brokers/common/intelligent_gateway.py` | 17 silent `except Exception: pass` fallbacks hide systemic Upstox failures. |
| `brokers/common/oms/risk_manager.py` | No lock, `_daily_pnl` never reset, `set_kill_switch`/`update_daily_pnl` dead. |
| `brokers/dhan/factory.py` | Single `CircuitBreaker` for all endpoints; 3 loaders. |
| `brokers/dhan/websocket.py` | 3 daemon threads not `ManagedService`; 2/3 `disconnect()` do not `join()`. |
| `datalake/gateway.py` | Unknown timeframes silently return unresampled 1m data; 0 tests. |
| `cli/commands/oms.py` | Uses Dhan-specific statuses (`COMPLETE`, `PARTIAL`) and fields (`order_timestamp`, `average_price`) not present on canonical `Order`. |
| `brokers/upstox/reconciliation/service.py` | 6 bare `except Exception:` blocks swallow every error. |

### 4.4 KEEP

- `brokers/common/core/domain.py` (canonical dataclasses, `OrderStatus.normalize()`).
- `brokers/common/oms/order_manager.py` and `position_manager.py`.
- `brokers/common/event_bus/event_bus.py`, `dead_letter_queue.py`, `processed_trade_repository.py`.
- `brokers/common/lifecycle/lifecycle.py`.
- `brokers/common/resilience/*`.
- `brokers/dhan/orders.py::OrdersAdapter.place_order` and `IdempotencyCache`.
- `brokers/dhan/token_scheduler.py`.
- `brokers/dhan/factory.py::_update_env_token` (atomic write).
- `datalake/journal.py::TradeJournal` and `datalake/io.py::atomic_parquet_write`.
- Analytics research modules (indicators, options, scanner, replay, backtest) — all tested.

---

## 5. Domain Consistency Findings

- **Duplicate `Order` models:** canonical dataclass, Pydantic `models.py`, and Dhan re-export. Upstox still imports the Pydantic `OrderRequest` from `models.py`.
- **Duplicate enums:** `domain.py` and `enums.py` both define `OrderStatus`, `OrderType`, `ProductType`, `Validity`, `Side`, `ExchangeSegment`, `InstrumentType`, `TransactionType`.
- **Source-of-truth violation for order status:** was a production failure (DH-906). **Fixed** in `dhan/orders.py:345` via `OrderStatus.normalize(status_str)`.
- **`RiskManager._daily_pnl` is the only source for daily PnL, but it is never reset.** An IST 00:00 rollover is invisible to the process.
- **Two parallel token stores:** `os.environ["DHAN_ACCESS_TOKEN"]` and `runtime/dhan-token-state.json`. Kept in sync only by `_update_env_token`.
- **`Quote`/`MarketDepth` have no single canonical owner.** Dhan defines its own; canonical `domain.py` only defines `DepthLevel`/`MarketDepthLevel`.
- **`KillSwitch` has four meanings** and no single owner.

---

## 6. Shotgun Surgery Findings

### 6.1 "Place an order" — two parallel systems

- **Dhan path:** `OrdersAdapter.place_order` performs validation, idempotency, risk check (via injected `RiskManager`), HTTP submit, event publish, and position update (none).
- **Central OMS path:** `OrderManager.place_order` performs validation, idempotency (`ProcessedTradeRepository`), risk check (same `RiskManager`), event publish, and `PositionManager` update.
- **Defect:** The CLI uses the Dhan path only. The OMS path is tested but not live. Adding a new order type requires changes in both adapters.

### 6.2 "Daily loss limit" — defined but unwired

- `RiskConfig.max_daily_loss_pct` and `RiskManager.update_daily_pnl` exist, but `update_daily_pnl` is **never called** from production code. The daily loss limit is decorative.

### 6.3 "Token must remain valid" — three uncoordinated implementations

1. `TokenRefreshScheduler` (proactive, 20-min interval, 10-min buffer).
2. `DhanHttpClient._try_refresh_token` (reactive 401, 60s cooldown).
3. `AuthManager.refresh_recommended` (TOTP-time-aware).

The shared `refresh_lock` only protects factory-built paths; direct `AuthManager` construction bypasses it.

### 6.4 "Reconcile OMS with broker" — two classes, never started

- `DhanReconciliationService` (algorithm) + `ReconciliationService` (ManagedService wrapper). BrokerService constructs it but never calls `attach_lifecycle()`, so the timer thread is created but **never started**.

### 6.5 "Event-driven OMS" — isolated from live broker events

- The gateway's `event_bus` is `None` in the CLI path. WebSocket `ORDER_UPDATED`/`TRADE` events are not published to the `TradingContext`'s bus. The OMS is a disconnected read-only mirror.

---

## 7. Concurrency & Reactive Risks

### 7.1 Race conditions

| Risk | Location | Failure mode |
|---|---|---|
| `RiskManager` config rebind | `risk_manager.py:82` | `set_kill_switch` replaces `_config` without a lock; concurrent `check_order` may see torn config. |
| `RiskManager._daily_pnl` update | `risk_manager.py:78` | `update_daily_pnl` and `check_order` read/write `_daily_pnl` without synchronization. |
| Token refresh contention | `factory.py:190` | `refresh_lock` is per-factory instance; direct `AuthManager` usage bypasses it. |
| Single shared circuit breaker | `factory.py:115` | Read-side failures open the breaker for order placement. |
| WebSocket reconnect backoff | `websocket.py:246` | Backoff doubles on every silent drop but only resets on successful `connect()`. Dhan's "no close frame" drops mean 30s backoff is reached quickly. |

### 7.2 Timing / ordering dependencies

- Reconciliation interval 5 min; drift can go undetected for up to 5 min.
- Daily PnL reset: **missing**.
- `.env.local` loaders run in startup order; `factory.py` custom parser may mis-parse quoted values.
- `TradingContext` must be attached to a `LifecycleManager` before services start; this is never done.

### 7.3 Resource leaks

| Leak | Location | Severity |
|---|---|---|
| WebSocket market-feed thread not joined | `websocket.py:248-258` | HIGH |
| WebSocket order-stream thread not joined | `websocket.py:527-531` | HIGH |
| Token scheduler auto-started without lifecycle | `factory.py:174` | MEDIUM |
| Reconciliation thread created but not started | `context.py:126` | LOW (leak only if started) |
| `EventBus` no backpressure | `event_bus.py` | MEDIUM |
| `MetricsCollector._metrics` unbounded | `metrics.py` | LOW |

### 7.4 Distributed failure scenarios

| Scenario | Detection | Mitigation | Status |
|---|---|---|---|
| Dhan 401 mid-session | Reactive HTTP handler | Lock-protected refresh | OK |
| Dhan 429 | HTTP handler | Exponential retry | OK |
| Dhan 5xx | HTTP handler | Circuit breaker | PARTIAL — single breaker |
| WebSocket silent drop | Debug log only | Reconnect + backfill | FRAGILE — backoff never resets |
| Upstox outage via `IntelligentGateway` | **Silent** | Falls back to Dhan | **DANGEROUS** |
| Day rollover PnL | None | None | **MISSING** |
| Process restart loses OMS state | `EventLog` exists | Not used in CLI path | **DEAD** |

---

## 8. Integration Certification Report

| Integration | Preconditions | Guarantees | Failure Detection | Recovery | Production Ready |
|---|---|---|---|---|---|
| Dhan REST API | TOTP/PIN/client_id; valid JWT; network | Idempotent order placement; rate-limited | 401 refresh, 429 backoff, 5xx retry/CB | Token auto-refresh | **NO** — single shared CB; 3 loaders |
| Dhan WebSocket market feed | Valid token; network | Tick stream; reconnect; gap backfill | Debug/error logs; no alert | Reconnect backoff | **NO** — not lifecycle-owned; no join |
| Dhan WebSocket order updates | Valid token; subscribed | Order status events | Lock-protected; no reconnect loop | Manual disconnect only | **NO** |
| Upstox REST API | API key/secret/token | Read endpoints | 6 silent `except` in reconciliation | Silent fallback | **NO** |
| Upstox WebSocket V3 | Token + URL | Multiplexed stream | `UpstoxAutoReconnect` | Auto-reconnect | **PARTIAL** |
| SQLite `TradeJournal` | None | WAL writes; thread-local | Exception | Reopen | **YES** |
| Parquet `DataLakeGateway` | Files on disk | Read + silent resample | Silent wrong-timeframe fallback | None | **NO** |
| `.env.local` | Read/write at startup | Atomic token write | Permission fallback | State store | **PARTIAL** — 3 loaders |
| Token state JSON | None | Persisted `TokenState` | None | Regenerate | **YES** |
| Frontend backend | **Does not exist** | — | — | — | **N/A** |
| HTTP health/metrics endpoint | **Does not exist** | — | — | — | **NO** |

---

## 9. Observability Gaps

### 9.1 Missing metrics / telemetry

- No Prometheus / OpenTelemetry exporter. `EventMetrics.snapshot()` exists but is never scraped.
- No broker API latency histograms. `MetricsCollector` keeps raw samples; `p95` is computed as the 100th percentile and the test asserts the bug.
- No market-data staleness metric.
- No daily PnL metric (because PnL is never updated).
- No circuit-breaker-state metric exposed to operators.

### 9.2 Missing alerts

There is no alert engine. The following should page an operator but do not:

- Order rejected by broker.
- Position mismatch (reconciliation drift).
- Duplicate fill.
- No ticks for 30s.
- Token refresh failure.
- Kill switch activation.
- Circuit breaker OPEN.
- Rate-limit sustained.

### 9.3 Silent failure risks

- **17 silent `except Exception: pass` fallbacks** in `IntelligentGateway`.
- **6 silent `except Exception:` swallows** in `upstox/reconciliation/service.py`.
- **47 bare `except Exception: ... pass` blocks** in production code overall.
- `DataLakeGateway` returns unresampled 1m data for unknown timeframes.
- `RiskManager` kill switch is never triggered; daily PnL never reset.
- Upstox `get_trade_book()` returns `[]` unconditionally.

### 9.4 Production diagnostics

Logs are stdlib only. Structured `extra=` fields exist but the default formatter drops them, so logs are not machine-parseable without a custom formatter. Metrics have no exporter. Traces do not exist. Root-cause identification is **not possible** with the current stack.

---

## 10. Mandatory Test Matrix Before Deployment

| Category | Status | Notes |
|---|---|---|
| Unit tests | ⚠️ Partial | Strong for OMS, event_bus, lifecycle, resilience, Dhan orders; weak for gateway/CLI. |
| Integration tests | ⚠️ Partial | Dhan-only; `verify_event_replay.py` not wired to CI. |
| Contract tests | ❌ Partial | Dhan has `BrokerContractSuite`; Upstox has none. |
| End-to-end tests | ❌ Empty | `tests/e2e/` contains only `__init__.py`. |
| Concurrency tests | ✅ Good | Idempotency, thread-safety, re-entrancy covered where tested. |
| Load tests | ⚠️ Light | `tests/performance/test_performance.py` exists but no baseline. |
| Failover tests | ❌ Missing | No token-expiry-mid-flight, broker disconnect, network partition tests. |
| Chaos tests | ❌ Missing | No `toxiproxy`/simulated failure injection. |
| Recovery tests | ❌ Missing | EventLog replay not exercised in production path. |
| Frontend tests | ❌ Zero | No test runner, no `*.test.*` files. |
| CLI entry-point tests | ❌ Zero | `main.py` has no dedicated tests. |
| DataLakeGateway tests | ❌ Zero | No `test_gateway.py`. |
| IntelligentGateway tests | ❌ Zero | No tests at all. |

---

## 11. Production Failure Scenarios

### What can break?

1. Single shared circuit breaker opens on read failures and blocks order placement.
2. WebSocket silent drop with backoff that never resets → up to 30s stale data.
3. Token scheduler auto-started without lifecycle → leaked on shutdown.
4. Day rollover leaves yesterday's loss in `RiskManager._daily_pnl`.
5. `.env.local` drift between three loaders causes stale token on restart.
6. Reconciliation service never starts → position drift accumulates.
7. `IntelligentGateway` silently hides every Upstox failure.
8. `DataLakeGateway` returns wrong-timeframe data without warning.
9. WebSocket disconnect does not join threads → thread leaks.
10. `oms.py` CLI assumes Dhan-specific fields/statuses not present on canonical `Order`.

### What fails silently?

- All Upstox calls through `IntelligentGateway`.
- All Upstox reconciliation errors.
- Unknown timeframe resampling in `DataLakeGateway`.
- Daily PnL reset.
- Kill switch activation (never called).
- Duplicate fill protection on the live Dhan path (OMS not fed).

### Worst-case chain reaction

1. Dhan WebSocket drops silently.
2. Backoff climbs to 30s.
3. A read-heavy command triggers rate limit / circuit breaker.
4. The single breaker opens, blocking `place_order`.
5. Operator sees every command fail with `Circuit breaker open`.
6. No alert fires; logs are unstructured; root cause is buried in debug logs.

---

## 12. Deployment Decision

### **NO-GO**

**Risk level:** **HIGH**

The system has already failed once in production (DH-906 circuit-breaker bug). The same failure class — hidden assumptions, untested paths, and silent failure modes — is present in at least 47 locations today. The central OMS is constructed but disconnected from live broker events. The kill switch and daily PnL limits are decorative. WebSocket threads are not owned by the lifecycle manager. Upstox failures are swallowed silently.

### Blocking issues (must fix before re-deployment)

| # | Issue | File |
|---|---|---|
| B1 | Single shared `CircuitBreaker` for all Dhan endpoints | `brokers/dhan/factory.py:115` |
| B2 | `RiskManager._daily_pnl` never reset | `brokers/common/oms/risk_manager.py` |
| B3 | `RiskManager` has no internal lock | `brokers/common/oms/risk_manager.py` |
| B4 | `LifecycleManager` not wired; reconciliation never started | `cli/services/broker_service.py` |
| B5 | WebSocket threads not `ManagedService`; disconnect doesn't join | `brokers/dhan/websocket.py` |
| B6 | 17 silent `except Exception: pass` fallbacks in `IntelligentGateway` | `brokers/common/intelligent_gateway.py` |
| B7 | Central OMS not integrated with live gateway | `cli/services/oms_service.py`, `broker_service.py` |
| B8 | No `/healthz`, `/readyz`, `/metrics` endpoint | missing |
| B9 | No Prometheus/OpenTelemetry exporter | `brokers/common/observability` |
| B10 | No chaos/failover tests | `tests/e2e/`, `tests/regression/` |

### Required remediation (4-week plan)

**Week 1 — Stop the bleeding**
- Split Dhan circuit breaker into `read`, `write`, `admin` breakers.
- Add lock + daily PnL reset scheduler to `RiskManager`.
- Implement `ManagedService` for all three WebSocket classes.
- Replace all silent `except: pass` in `IntelligentGateway` with log + metric.
- Wire `LifecycleManager` in `BrokerService`; call `attach_lifecycle()`.

**Week 2 — Integrate or delete the OMS**
- Decision: route live orders through `OrderManager` (shared event bus) or delete the central OMS.
- If kept, pass the context's `EventBus` into `BrokerFactory.create()` and feed WebSocket events into it.
- Fix `cli/commands/oms.py` to use canonical `Order` fields/statuses.

**Week 3 — Observability + testing**
- Add aiohttp `/healthz`, `/readyz`, `/metrics`.
- Add Prometheus exporter scraping `EventMetrics` + `LifecycleManager.health_snapshot()`.
- Add `test_gateway.py`, `test_intelligent_gateway.py`, `test_cli_main.py`.
- Add Upstox `BrokerContractSuite`.
- Add chaos tests for token expiry, WebSocket drop, network partition.

**Week 4 — Cleanup + certification**
- Delete deprecated modules (`models.py`, `enums.py`, `broker.py`, `facade.py`, `connection.py`, `schemas.py`, `data_contracts.py`, `observability/metrics.py`, `observability/logging.py`).
- Delete 8 empty Dhan placeholder dirs and root `ind_nifty*.csv`.
- Consolidate analytics test tree.
- 7-day staging soak, 1,000-thread concurrency test, 24-hour WebSocket reconnect test.
- SRE / Release Manager / Trading Lead sign-off.

---

**Bottom line:** TradeXV2 contains production-grade components, but they are not wired together into a survivable system. The previous production failure is a warning, not an anomaly. **Deployment is not approved until all 10 blocking issues and the 4-week remediation plan are complete.**
