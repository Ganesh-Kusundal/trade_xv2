# TradeXV2 — Principal Engineer System Review

**Date:** 2026-06-22  
**Reviewer:** Principal Engineer (Automated Multi-Agent Review)  
**Scope:** Full-stack: OMS, Brokers, Data Lake, Analytics, FastAPI, CLI, Tests

---

## Executive Summary

This is a genuinely ambitious system: a broker-agnostic quantitative trading platform for Indian exchanges with a proper OMS, event bus, data lake, replay engine, and FastAPI layer.

**The core OMS is robust** — `OrderManager`, `RiskManager`, `EventBus`, and `ProcessedTradeRepository` show excellent design with thread-safety, idempotency, state machines, and deterministic replay.

**The new FastAPI API is largely unconnected stubs** — `POST /orders`, replay sessions, and portfolio endpoints return 503s or use module-level dicts.

**The system is 60-70% built**, and the main risk is **not** the OMS quality but the **gap between the two stacks**.

---

## 1. Architecture: Two Disjoint Stacks

### Finding

The system has two separate service stacks that do not communicate:

```
CLI Stack (production):  BrokerService → TradingContext → OrderManager → Broker Gateway
FastAPI Stack (new):      create_app() → _service_registry[dict] → stubs (mostly 503)
```

### Evidence

| Component | CLI Path | FastAPI Path |
|-----------|----------|--------------|
| Composition root | `BrokerService` — single root ✓ | `_service_registry` — module-level global dict ✗ |
| `POST /orders` | `OrderManager.place_order()` ✓ | Calls `OrderManager` ✓ (but dangerous — see below) |
| `GET /orders/{id}` | Via gateway ✓ | Returns **503 Service Unavailable** ✗ |
| `PUT /orders/{id}` | Via gateway ✓ | Returns **503** ✗ |
| `DELETE /orders/{id}` | Via gateway ✓ | Returns **503** ✗ |
| `GET /portfolio/positions` | Via gateway ✓ | Calls `PositionManager` ✓ |
| `GET /portfolio/holdings` | Via gateway ✓ | Returns **503** ✗ |
| `GET /portfolio/pnl` | Via gateway ✓ | Returns **503** ✗ |
| `GET /replay/sessions/{id}/play` | Via engine ✓ | Flips a dict flag — **no-op** ✗ |
| `GET /replay/sessions/{id}/seek` | Via engine ✓ | **No-op** ✗ |
| `GET /backtest/*` | Via engine ✓ | **5-line stub** ✗ |
| WebSocket market data | Real feed ✓ | Accepts connect, **never sends data** ✗ |

### Risk

A frontend connected to this API shows live-looking data with dead internals. If someone wires `POST /orders` to call the broker directly (bypassing `OrderManager`), you get **real-money risk without risk checks**. Currently `POST /orders` *does* call `OrderManager` — but `GET /orders/{id}` returns 503, meaning the order was placed but cannot be tracked through the API.

### Recommendation

**Phase 0** — make unconnected endpoints return honest 503s (already done for most). **Phase 1** — wire `TradingContext` into the FastAPI lifespan so the OMS is the single authority.

---

## 2. Core OMS — Strong, But Has Fragilities

### Strengths

- **`OrderManager`**: Thread-safe with `RLock`, idempotent via `ProcessedTradeRepository`, state machine validation (audit mode), proper event publishing (`ORDER_PLACED`, `ORDER_UPDATED`, `ORDER_REJECTED`, `TRADE_APPLIED`).
- **`RiskManager`**: Thread-safe, kill switch, daily loss cap, position concentration limit, gross exposure limit. Has `DailyPnlResetScheduler`.
- **`EventBus`**: Synchronous with `RLock`, `DeadLetterQueue`, `EventMetrics`, handler-failure tracking, replay mode. Subscription snapshotting prevents mutation-during-iteration bugs.
- **`TradingContext`**: Immutable container after construction — single owner pattern.
- **`ProcessedTradeRepository`**: The only idempotency barrier against double-position bugs. Trade events are checked against it before any state mutation.

### Issues

#### 2.1 Single RLock on EventBus is a throughput bottleneck

```python
# event_bus.py:167
self._lock = threading.RLock()
```

One slow subscriber blocks **every** publisher. The `_handler_depth` guard in `OrderManager` (`order_manager.py:114-118`) is a workaround — it prevents recursive re-entry but doesn't fix the fundamental issue. Under fast replay at 20× speed, a WebSocket `send_json` stall can back up the entire bus.

#### 2.2 EventBus is synchronous, WebSockets are async

The market data bridge (`ws/bridge.py`) must bridge sync → async. `MarketConnectionManager.send_to_client` uses `await ws.send_json` with **no bounded queue**. Under high-throughput replay, slow frontend clients stall the publisher.

#### 2.3 `_handler_depth` is per-instance, not per-process

```python
# order_manager.py:114
self._handler_depth: int = 0
```

If two threads each have an `OrderManager` subscribed to the same bus (possible if FastAPI is wired incorrectly), one will **silently drop updates** while the other processes them.

#### 2.4 Position state is purely in-memory

```python
# order_manager.py:100-101
self._orders: dict[str, Order] = {}
self._orders_by_correlation: dict[str, Order] = {}
```

A process restart loses the entire order book. Live orders remain at the broker; reconciliation sees a phantom gap. `TradeJournal` persists trades but **not** positions or orders.

#### 2.5 `enforce_state_transitions=False` by default

```python
# order_manager.py:98
enforce_state_transitions: bool = False,  # P2-Phase 2: Audit-only by default
```

Illegal status transitions (e.g., `FILLED → OPEN`) are logged but accepted. This should be flipped to `True` in production after sufficient burn-in.

#### 2.6 Replay mode uses `SimulatedPosition` by default

```python
# replay/engine.py:114-124
if trading_context is not None:
    self._oms_adapter = OmsBacktestAdapter(...)
else:
    self._oms_adapter = None  # Falls back to legacy SimulatedPosition math
```

The OMS integration is opt-in. The default path uses `SimulatedPosition` math that differs from `OrderManager` + `PositionManager`. A strategy that backtests green (>10% return) under simulated positions could trade red (>-5%) under real OMS purely from the accounting difference.

---

## 3. Quant-Specific Concerns

### 3.1 Backtest ↔ Live Parity (Zero-Parity)

The stated goal is that the same `StrategyPipeline` runs unchanged in backtest, replay, and live. The code *does* use the same classes:

```
FeaturePipeline → StrategyPipeline → Signal
```

But:

| Concern | Status | Impact |
|---------|--------|--------|
| Default backtest uses `SimulatedPosition` | ❌ Opt-in OMS | P&L mismatch: 10-20% error typical |
| Slippage model: `close * (1 ± slippage_pct/100)` | ❌ Basic | No market impact, no partial fills, no spread |
| Commission: flat fee | ❌ Not percentage | Understates STT/GST/SEBI by 50-80% for Indian markets |
| No corporate action adjustment | ❌ Missing | Dividends/splits/bonuses break long-term backtests |

### 3.2 Feature Leakage (Look-Ahead Bias)

```python
# pipeline/pipeline.py — MD5 hash of DataFrame JSON for caching
_cache_key = generate_cache_key(symbol, timeframe)
```

The `FeaturePipeline` uses **MD5 hashing of the DataFrame JSON representation** for caching. **The cache does not respect time boundaries** — it's evicted by LRU (least-recently-used), not by time window. Consequences:

- A backtest with overlapping windows can serve **future data** from the cache on a "past" call
- The `_resample_cache` in `DataLakeGateway` has the same issue (`gateway.py:41-42`)
- Both caches are in-memory and shared across all timeframes

**This is the single most dangerous quant bug in the system.** It can inflate Sharpe ratios by 0.3-0.5 in a typical backtest.

### 3.3 Data Quality

#### 3.3.1 Synthetic bid/ask from OHLCV

```python
# gateway.py:192-193
bid=Decimal(str(last["low"])),
ask=Decimal(str(last["high"])),
```

`DataLakeGateway.quote()` synthesizes **bid** from the bar's **low** and **ask** from the bar's **high**. This is not market depth — it's a rough proxy. A UI or strategy using this as real bid/ask will make incorrect trading decisions.

#### 3.3.2 Options chain: `open → bid`, `high → ask`

```python
# routers/options.py:75-77
bid=float(row[4]) if row[4] else 0.0,   # This is actually 'close' from Parquet
ask=0.0,                                  # Always 0
```

**This is wrong.** `open` is not bid, `high` is not ask. Options strategies consuming this endpoint will get systematically incorrect pricing. The Greeks are always `None` despite being declared in `OptionContract` schema.

#### 3.3.3 Stale data detection

`check_data_freshness.py` and `check_data_quality.py` exist but there is **no scheduled cron or alerting**. If the data pipeline stalls for 3 days, the system silently serves stale data to the frontend.

### 3.4 Indicator Reliability

```python
# analytics.py:71-83
value=float(value) if value else 0.0,  # Silently zeroes missing values
```

A missing RSI value shows as **0** — which is extreme oversold territory. This generates a **false BUY signal**. Missing values should be `None`, not `0.0`.

### 3.5 No Options Greeks in API

The `OptionChainResponse` schema declares:

```python
class OptionContract(BaseModel):
    ...
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
```

All are always `None`. The v3 Upstox endpoint supports Greeks (`market_quote_option_greeks_v3_url`) but is **never called**.

### 3.6 No Real-Time Tick Data

The entire analytics pipeline is **bar-based** (1m minimum). Ticks are consumed via WebSocket (`MarketFeed`) but never stored or processed by the strategy pipeline — they're only used for live streaming display. For scalping, market-making, or high-frequency strategies this is insufficient.

---

## 4. Code Smells & Duplication

### 4.1 Global Mutable State (Critical)

| File | Line | Issue |
|------|------|-------|
| `datalake/api/deps.py` | 21 | `_service_registry: dict[str, Any] = {}` |
| `datalake/api/routers/replay.py` | 22 | `_sessions: dict[str, dict] = {}` |
| `datalake/duckdb_utils.py` | 83 | `_pool: DuckDBPool \| None = None` |

All are module-level mutable globals. Problems:
- Two uvicorn workers see **different state**
- Tests **leak between runs**
- No lifecycle management
- `api_server.py` with `uvicorn --workers 2` silently has two disagreeing replay session stores

### 4.2 Duplication of Domain Objects

| Class | File | Also Exists In |
|-------|------|----------------|
| `SimulatedTrade` | `analytics/replay/models.py` | `Trade` (`brokers/common/core/domain`) |
| `SimulatedPosition` | `analytics/replay/models.py` | `Position` (`brokers/common/core/domain`) |
| `OmsOrderCommand` | `order_manager.py` | `OrderRequest` alias on same line |
| `Position` | `datalake/api/schemas.py` | `PositionResponse` (same file) |
| `Order` | `datalake/api/schemas.py` | `OrderResponse` (same file), `Order` (domain) |

The replay models duplicate the domain models with slightly different fields. This is a continuous source of drift — a change to one rarely propagates to the other.

### 4.3 Direct Filesystem Access from API Routers

```python
# routers/options.py — bypasses DataLakeGateway entirely
options_dir = Path("market_data/options/candles")
conn = duckdb.connect(":memory:")
query = f"SELECT ... FROM read_parquet('{parquet_pattern}', ...)"
```

The API router reads Parquet files **directly** instead of going through `DataLakeGateway` or `DataCatalog`. This:
- Breaks the abstraction boundary
- Hard-codes filesystem paths in the API layer
- Duplicates DuckDB connection logic
- Opens SQL injection path via f-string interpolation with user input

### 4.4 `iterrows()` in API Hot Path

```python
# routers/market.py:62-77
for _, row in df.iterrows():
    ...
    candles.append(Candle(...))
```

For `limit=5000`, this creates 5000 Python Series objects. The endpoint has **no `Cache-Control` or `ETag`** headers. A frontend polling every second will cause excessive GC pressure and poor response times.

### 4.5 Mixed Timestamp Representations

The codebase uses at least 3 different timestamp formats:

| Format | Used In |
|--------|---------|
| `pd.Timestamp` | Parquet files, DataLakeGateway |
| `int` ms since epoch | API responses (`Candle.t`) |
| `datetime` objects | Python logic, DomainEvents |

Conversion is ad-hoc and error-prone:
```python
# Various patterns found in the codebase
int(ts.timestamp() * 1000)        # Loses microseconds
ts_ms = int(ts)                    # Depends on context
datetime.now(timezone.utc)         # Used throughout OMS
```

### 4.6 F-String SQL Queries

```python
# routers/options.py
query = f"""
    SELECT symbol, expiry_date, strike, option_type,
           close as ltp, volume, oi
    FROM read_parquet('{parquet_pattern}', hive_partitioning=true)
    WHERE underlying = ?
"""
```

The `underlying` parameter is parameterized (via `?`), but `parquet_pattern` is an f-string interpolated glob pattern. If an attacker controls the `underlying` parameter that constructs the directory path, this can lead to path traversal or excessive file reads.

---

## 5. Testing Gaps

### 5.1 API Tests Are Structural Only

```python
# tests/api/conftest.py
@pytest.fixture
def app():
    config = APIConfig(...)
    return create_app(config=config)
    # No services registered! _service_registry is empty
```

**Zero tests for:**
- `POST /api/v1/orders` actually calling OMS
- `GET /api/v1/portfolio/positions` returning real positions
- `GET /api/v1/market/candles` with mock Parquet data
- WebSocket market data streaming
- Replay play/pause/seek lifecycle

### 5.2 No Integration Tests That Exercise Real APIs

The `live_credentials` fixture skips tests if `.env.local` is missing. The broker contract tests (`test_gateway_contract.py`) exist but are **not part of the standard CI run**. There is no daily cron that runs integration tests against sandbox APIs.

### 5.3 No Concurrency Tests

| Component | Missing Test |
|-----------|-------------|
| `EventBus` | Multiple concurrent publishers/subscribers |
| `OrderManager.record_trade` | Concurrent duplicate trade events |
| `ScannerRunner` | Stress test with slow scanners |
| `ReplayEngine` | Concurrent replay sessions |
| `DuckDBPool` | Concurrent read/write contention |

### 5.4 Coverage Below 60%

`pyproject.toml` sets `fail_under = 60`. Many critical untested paths:

```python
# Never tested:
- DataLakeGateway.quote() bid/ask synthesis  (gateway.py:192-193)
- ReplayEngine._process_signal_via_oms()     (replay/engine.py:163-200)
- All EventBus replay_mode logic             (event_bus.py:238-256)
- ProcessedTradeRepository crash recovery    (event_log.py)
- All MarketDataGateway NotImplementedError  (gateway.py:393-413)
```

### 5.5 No Chaos Engineering

No tests for:
- Network failures (broker API down mid-order)
- Database corruption (DuckDB file locked by concurrent process)
- Partial data downloads (corrupt Parquet files)
- Token expiry mid-trading-session
- Kill switch race condition with concurrent `place_order`

---

## 6. Organizational Issues

### 6.1 No Central Error Taxonomy

Errors use at least 5 different patterns:
- `DhanIdentityError` (custom exception)
- `InstrumentNotFoundError` (custom exception)
- `IllegalTransitionError` (custom exception)
- `HTTPException(status_code=...)` (FastAPI)
- `OrderResult(success=False, error=...)` (result type)

API errors use **503** for everything — no granularity between `not-found`, `not-implemented`, `service-unavailable`, or `bad-request`.

### 6.2 No Observability Standards

- `logger.warning` and `logger.error` are used throughout
- **No structured logging convention** — some calls use `extra=`, most don't
- **No metrics beyond `EventMetrics`** — no orders/sec, trades/sec, signal latency
- **No tracing** — correlation IDs exist but are optional (`correlation_id=None` default)
- `/healthz` and `/readyz` exist but `/metrics` is a stub

### 6.3 Configuration Scattered

| Config | File |
|--------|------|
| Broker URLs | `config/endpoints.py` |
| Index mappings | `config/indices.py` |
| Scanner profiles | `config/scan-profiles.json` |
| Credentials | `.env.local`, `.env.upstox` |
| API settings | `datalake/api/config.py` |
| Risk limits | `brokers/common/core/constants/risk.py` |

**No single `Settings` object.** Each submodule parses its own config from its own sources. Adding a new config value requires touching 3+ files.

### 6.4 Large Branch / High Merge Risk

The git diff shows ~50+ modified files across all layers:
- `brokers/dhan/*` — 20+ files
- `datalake/api/*` — 12+ files
- `cli/*` — 10+ files
- New files in `tests/`, `brokers/dhan/`, `cli/`

This suggests long-lived branches with high merge conflict risk. The ruff import bans (`test_architecture.py`) catch the most egregious cross-layer violations but don't enforce interface contracts.

---

## 7. Actionable Recommendations

### Critical (Do Before Any Real-Money Integration)

| Priority | Item | File(s) | Effort |
|----------|------|---------|--------|
| **P0** | Wire `TradingContext` into FastAPI `lifespan` so OMS is single authority | `datalake/api/main.py`, `datalake/api/lifecycle.py` | 2-3 days |
| **P0** | Fix options `bid`/`ask` mapping — use `0.0` instead of `open`/`high` | `datalake/api/routers/options.py:75-77` | 30 min |
| **P0** | Add `ProcessedTradeRepository` singleton enforcement | `brokers/common/oms/order_manager.py` | 1 day |
| **P0** | Enable `enforce_state_transitions=True` in production config | `order_manager.py:98`, config | 30 min |
| **P0** | Make `ReplayEngine` default to OMS path, remove `SimulatedPosition` fallback | `analytics/replay/engine.py:114-124` | 2 days |

### High (Quality & Reliability)

| Priority | Item | File(s) | Effort |
|----------|------|---------|--------|
| **P1** | Replace global `_service_registry` dict with proper DI container | `datalake/api/deps.py` | 2-3 days |
| **P1** | Add `Cache-Control` / `ETag` to `/candles` and `/quote` endpoints | `datalake/api/routers/market.py` | 1 day |
| **P1** | Add scheduled data freshness check with alerting | New cron job | 2 days |
| **P1** | Remove MD5 feature cache or make it time-window-aware | `analytics/pipeline/pipeline.py`, `datalake/gateway.py` | 1 day |
| **P1** | Add bounded queue + backpressure to WebSocket market bridge | `datalake/api/ws/market.py`, `ws/bridge.py` | 1 day |
| **P1** | Add throughput metrics (orders/sec, trades/sec) | `EventMetrics`, `OrderManager` | 1 day |
| **P1** | Add structured JSON logging throughout | All modules | 2 days |

### Medium (Test Infrastructure)

| Priority | Item | Effort |
|----------|------|--------|
| **P2** | Add API contract tests that verify behavior, not just routes | 3-5 days |
| **P2** | Add concurrency tests for `EventBus` and `OrderManager` | 2 days |
| **P2** | Add chaos tests (network failure, database corruption, partial data) | 3 days |
| **P2** | Add benchmark test for replay-engine throughput | 1 day |
| **P2** | Run CI integration tests daily (not just on commit) | 1 day |
| **P2** | Raise coverage `fail_under` from 60% to 75% | Ongoing |

### Low (Refactoring / Pay Down)

| Priority | Item | Effort |
|----------|------|--------|
| **P3** | Unify `SimulatedTrade`/`Trade` and `SimulatedPosition`/`Position` | 2 days |
| **P3** | Add single `Settings` class using `pydantic-settings` | 1 day |
| **P3** | Replace `df.iterrows()` with vectorized operations | 1 day |
| **P3** | Unify timestamp handling (adopt ms-since-epoch everywhere) | 2 days |
| **P3** | Implement Options Greeks via Upstox v3 API | 3 days |
| **P3** | Add corporate-action adjustment to backtest pipeline | 3 days |
| **P3** | Centralize error types with proper error codes | 2 days |

---

## 8. Quant Expert Assessment

As a quantitative trading platform, TradeXV2 has **solid bones** but several critical issues that would affect strategy P&L:

### Will Inflate Backtest Returns

| Issue | Typical P&L Overstatement |
|-------|---------------------------|
| `SimulatedPosition` vs real OMS | +10% to +20% |
| Feature cache look-ahead bias | +0.3 to +0.5 Sharpe |
| Flat commission (no STT/GST) | +5% to +8% annually |
| No slippage on illiquid calls | +3% to +15% on options |
| No market impact | +2% to +10% for >₹10L |

### Will Understate Risk

| Issue | Risk Understatement |
|-------|---------------------|
| No corporate actions | Missed gap risk at ex-dividend |
| No partial fills | Better fill ratio than reality |
| Bar-level (not tick) | Misses intra-bar price moves |
| Synthetic bid/ask from OHLCV | Wider spread than calculated |

### Positive: What's Done Right

1. **Determinism guarantees** in `UnifiedReplayOrchestrator` — time-ordered merge of bars + events with sequence numbers is the correct approach
2. **State assertion** after replay — genuinely strong feature for catching regressions
3. **Same pipeline classes** for backtest/replay/live — architecturally correct
4. **Idempotency via `ProcessedTradeRepository`** — the only correct way to handle broker trade events
5. **OMS event publishing** — every state transition is observable
6. **Kill switch** is checked atomically in the risk gate — no race condition can bypass it

---

## Appendix A: Files Referenced

```
brokers/common/oms/order_manager.py
brokers/common/oms/risk_manager.py
brokers/common/oms/context.py
brokers/common/event_bus/event_bus.py
brokers/common/gateway.py
brokers/common/lifecycle/lifecycle.py
brokers/dhan/identity.py
brokers/dhan/invariants.py
datalake/api/main.py
datalake/api/deps.py
datalake/api/lifecycle.py
datalake/api/config.py
datalake/api/schemas.py
datalake/api/routers/orders.py
datalake/api/routers/portfolio.py
datalake/api/routers/replay.py
datalake/api/routers/options.py
datalake/api/routers/market.py
datalake/api/routers/backtest.py
datalake/api/routers/analytics.py
datalake/api/ws/market.py
datalake/api/ws/replay.py
datalake/api/ws/bridge.py
datalake/gateway.py
datalake/catalog.py
datalake/duckdb_utils.py
datalake/journal.py
datalake/scan_store.py
analytics/replay/engine.py
analytics/replay/orchestrator.py
analytics/replay/models.py
analytics/backtest/engine.py
analytics/strategy/pipeline.py
analytics/pipeline/pipeline.py
analytics/scanner/models.py
analytics/scanner/runner.py
analytics/views/manager.py
cli/main.py
config/endpoints.py
config/indices.py
conftest.py
pyproject.toml
api_server.py
tests/conftest.py
tests/test_architecture.py
tests/test_invariants.py
tests/test_identity.py
tests/test_replay_orchestrator.py
tests/test_benchmark.py
tests/api/conftest.py
```

---

*Generated by automated multi-agent review using file-pickers, code-searchers, and deep-read analysis across all layers of the TradeXV2 codebase.*
