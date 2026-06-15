# TradeXV2 — Concurrency Hardening Roadmap

**Author:** Dr. Venkat Subramaniam perspective  
**Goal:** Make TradeXV2 safe for parallel scanners, multi-strategy trading, replay, backtesting, and live trading.  
**Principles:** Correctness first, determinism, simplicity, immutability, single ownership.

---

## Guiding Design Decisions

1. **Immutable value objects** for `Order`, `Position`, `Trade`, `Quote`, `Signal`.
2. **Single owner** for every mutable state: `OrderManager` owns orders, `PositionManager` owns positions, `EventBus` owns event distribution.
3. **Copy-on-write** updates instead of in-place mutation.
4. **Lock-safe `EventBus`** as the only way broker events reach consumers.
5. **Atomic file writes** (temp + fsync + rename) for all Parquet/env updates.
6. **Stable deterministic ordering** for every top-N ranking.
7. **Fail fast** when credentials or state are inconsistent; do not silently fall back to mock brokers for real trading commands.

---

## Phase 1 — Stop the Bleeding (Week 1)

### 1.1 Immutable Domain Objects

**Why:** `Order`, `Position`, `Trade` are currently mutable dataclasses. Concurrent reads see partially updated fields.

**Design:**
- Convert `Order`, `Position`, `Trade`, `Quote`, `DepthLevel`, `Holding`, `Balance` in `brokers/common/core/domain.py` to `@dataclass(frozen=True)`.
- Provide `Order.with_status(...)`, `Position.with_fill(...)`, `Trade.new(...)` helpers that return new instances.
- Remove all in-place field mutations.

**Files:**
- `brokers/common/core/domain.py`
- All files that mutate these objects (`brokers/paper/paper_orders.py`, `brokers/dhan/portfolio.py`, etc.)

**Flow:**
```
old_position = positions[key]
new_position = old_position.with_fill(quantity=qty, price=price)
positions = {**positions, key: new_position}
```

**Tests:**
- `test_order_is_frozen`
- `test_position_with_fill_returns_new_instance`
- `test_position_avg_price_math_for_side_flip`

---

### 1.2 Lock Paper/Mock OMS

**Why:** `PaperOrders` and `MockBroker` use plain lists/dicts with no locks. Concurrent `place_order` + `get_positions` corrupts state.

**Design:**
- Add `threading.RLock` to `PaperOrders`.
- Guard `_orders`, `_trades`, `_positions`, `_order_seq`, `_trade_seq`.
- Make `_update_position` return a new `Position` instead of mutating.
- Generate order IDs atomically under the lock.
- Same treatment for `MockBroker`.

**Files:**
- `brokers/paper/paper_orders.py`
- `brokers/paper/paper_portfolio.py`
- `brokers/paper/paper_market_data.py` (move `_base_prices` to instance)
- `cli/services/broker_service.py` (`MockBroker`)

**Flow:**
```python
with self._lock:
    self._order_seq += 1
    order_id = f"PPR-{self._order_seq}"
    order = Order(...)
    self._orders.append(order)
    self._positions = self._update_position(self._positions, order)
```

**Tests:**
- `test_concurrent_place_order_no_duplicate_ids`
- `test_concurrent_place_and_get_positions_consistent`
- `test_paper_position_math_side_flip`
- `test_mock_broker_thread_safety`

---

### 1.3 Lock Dhan Idempotency Cache

**Why:** Two threads with same `correlation_id` can both miss cache, both POST, then both cache.

**Design:**
- Replace `brokers/dhan/orders.py:IdempotencyCache` with a lock-protected implementation.
- Hold the lock across the entire get-check-POST-put sequence in `OrdersAdapter.place_order()`.
- Use `threading.RLock`.

**Files:**
- `brokers/dhan/orders.py`
- `brokers/dhan/tests/unit/test_orders_idempotency.py`

**Flow:**
```python
with self._idempotency.lock(correlation_id):
    cached = self._idempotency.get(correlation_id)
    if cached:
        return cached
    response = self._http_post(...)
    self._idempotency.put(correlation_id, response)
    return response
```

**Status:** ✅ Done — `IdempotencyCache` uses `threading.RLock`; `lock(correlation_id)` context manager guards the full get-check-POST-put sequence; `correlation_id` is auto-generated when missing.

**Tests:**
- `test_concurrent_place_order_with_same_correlation_id_returns_one_order`
- `test_idempotency_cache_eviction_thread_safe`

---

### 1.4 Protect Callback / Listener Lists

**Why:** `DhanMarketFeed`, `DhanOrderStream`, and `UpstoxMarketDataV3Multiplexer` mutate callback lists while background threads iterate them.

**Design:**
- Add `threading.RLock` to Dhan feed/stream.
- Snapshot list before iterating: `for cb in list(self._quote_callbacks):`.
- For Upstox asyncio multiplexer, wrap listener mutations with `asyncio.get_event_loop().call_soon_threadsafe()` or snapshot.
- Add `is_connected` property to `UpstoxMarketDataV3Multiplexer`.

**Files:**
- `brokers/dhan/websocket.py`
- `brokers/upstox/websocket/market_data_v3.py`
- `brokers/upstox/websocket/portfolio_stream.py`
- `brokers/upstox/gateway.py` (fix `ws._connected` and callback signature)

**Status:** ✅ Dhan done — `DhanMarketFeed` and `DhanOrderStream` use `threading.RLock` for callback lists and connection state, snapshot lists before iterating, and use `threading.Event` to interrupt reconnect backoff in `disconnect()`.

**Tests:**
- `test_subscribe_while_ticks_flowing_no_crash`
- `test_upstox_stream_callback_signature`
- `test_disconnect_during_reconnect_eventually_stops`
- `brokers/dhan/tests/unit/test_websocket_thread_safety.py`

---

### 1.5 Atomic Parquet & Env Writes

**Why:** Readers see partial files during `pq.write_table` / `df.to_parquet` / `_update_env_token`.

**Design:**
- Create `datalake/io.py` with `atomic_write(path, writer_fn)` helper.
- Pattern: write to `target.tmp`, fsync, rename.
- Apply to all Parquet writers and `_update_env_token`.

**Files:**
- `datalake/io.py` (new)
- `datalake/loader.py`
- `datalake/updater.py`
- `datalake/converter.py`
- `brokers/dhan/factory.py` (`_update_env_token`)
- `brokers/common/services/historical_data.py`
- `brokers/common/services/download_engine.py`

**Flow:**
```python
from datalake.io import atomic_parquet_write
atomic_parquet_write(target_path, table)
```

**Tests:**
- `test_atomic_parquet_write_replaces_atomically`
- `test_reader_never_sees_partial_parquet`
- `test_update_env_token_preserves_other_keys`

---

### 1.6 Deterministic Scanner / Ranking / Views

**Why:** Unstable `sort_values` and `LIMIT N` without tie-breaker make top-N vary across runs.

**Design:**
- Add tie-breaker `symbol` to every top-N sort.
- Use `kind="mergesort"` for stability.
- Deduplicate `(symbol, timestamp)` before `groupby().last()` in scanners.
- Fix SQL `ORDER BY intraday_score DESC, symbol` in views.

**Files:**
- `analytics/scanner/scanners.py`
- `analytics/scanner/models.py`
- `analytics/ranking/ranking.py`
- `analytics/views/scanner.py`
- `analytics/views/strategy.py`
- `cli/commands/analytics_halftrend.py`

**Tests:**
- `test_momentum_scanner_deterministic_with_ties`
- `test_ranking_engine_stable_with_ties`
- `test_top3_candidates_stable_with_ties`

---

## Phase 2 — Centralize Trading State (Weeks 2-4)

### 2.1 Lock-Safe EventBus

**Why:** Three different threading models push events to ad-hoc callback lists. No ordering, dedup, or thread safety.

**Design:**
- New `brokers/common/event_bus.py`.
- Thread-safe `EventBus` using `threading.RLock` and immutable subscriber snapshot.
- Event types: `TICK`, `DEPTH`, `ORDER_UPDATE`, `TRADE`, `POSITION_UPDATE`.
- Feeds publish events; consumers subscribe.

**Files:**
- `brokers/common/event_bus.py` (new)
- `brokers/common/core/domain.py` (add `DomainEvent` frozen dataclass)
- `brokers/dhan/websocket.py` (publish instead of iterate callbacks)
- `brokers/upstox/websocket/market_data_v3.py` (publish instead of iterate listeners)

**Status:** ✅ Done — `brokers/common/event_bus.py` implemented with `threading.RLock`, immutable subscriber snapshots, handler-error isolation, and concurrency tests.

**Tests:**
- `test_event_bus_subscribe_publish`
- `test_event_bus_thread_safe_publish`
- `test_event_bus_snapshot_subscribers_no_crash_on_unsubscribe`

---

### 2.2 OrderManager

**Why:** No central OMS; order state fragmented across brokers.

**Design:**
- New `brokers/common/oms/order_manager.py`.
- Single `threading.RLock`.
- `orders: dict[str, Order]` by `order_id`.
- `orders_by_correlation: dict[str, Order]`.
- Methods: `place_order()`, `upsert_order()`, `get_order()`, `get_orders()`, `cancel_order()`.
- Generate `correlation_id` deterministically if not provided (`{strategy}:{symbol}:{side}:{nanoseconds}`).

**Files:**
- `brokers/common/oms/order_manager.py` (new)
- `brokers/common/oms/__init__.py`
- `cli/services/oms_service.py` (delegate to OrderManager)

**Status:** ✅ Done — `brokers/common/oms/order_manager.py` implemented with `threading.RLock`, idempotency by `correlation_id`, trade recording, cancellation, and optional `RiskManager` gate.

**Tests:**
- `test_place_order_atomic_idempotency`
- `test_concurrent_place_order_same_correlation_returns_same_order`
- `test_modify_order_after_fill_rejected`

---

### 2.3 PositionManager

**Why:** Position updates are scattered and unprotected.

**Design:**
- New `brokers/common/oms/position_manager.py`.
- Immutable `Position` values stored in a dict under lock.
- `apply_fill(trade) -> PositionUpdateResult` returns new position, realized PnL.
- Correct average price on side flip.
- Include realized PnL in available balance.

**Files:**
- `brokers/common/oms/position_manager.py` (new)
- `brokers/paper/paper_portfolio.py` (use PositionManager)
- `brokers/common/core/domain.py`

**Status:** ✅ Done — `brokers/common/oms/position_manager.py` implemented with immutable `Position` values, correct average price on side flip, and realized PnL tracking.

**Tests:**
- `test_apply_fill_long_to_short_flips_avg_price`
- `test_concurrent_fills_on_same_symbol_produce_correct_quantity`
- `test_realized_pnl_reflected_in_balance`

---

### 2.4 RiskManager

**Why:** No pre-trade risk checks; future check-then-act races likely.

**Design:**
- New `brokers/common/risk/risk_manager.py`.
- Runs **inside** OMS lock before any order is sent.
- Checks: available margin, gross exposure, per-symbol concentration, daily loss limit, kill-switch.
- Risk limits configured via `RiskConfig`.

**Status:** ✅ Done — `brokers/common/oms/risk_manager.py` implemented with `RiskConfig` for daily loss, per-symbol concentration, gross exposure, and kill-switch. Invoked by `OrderManager.place_order()` and by Paper/Dhan/Upstox order adapters.

**Files:**
- `brokers/common/oms/risk_manager.py` (new)
- `brokers/common/oms/order_manager.py` (invoke RiskManager)

**Tests:**
- `test_risk_manager_blocks_order_exceeding_margin`
- `test_concurrent_orders_collectively_exceed_limit_are_blocked`
- `test_kill_switch_blocks_all_orders`

---

### 2.5 Broker Adapters Feed the OMS

**Status:** ✅ Done — `TradingContext` wires `EventBus`, `OrderManager`, `PositionManager`, and `RiskManager`. Paper/Dhan/Upstox order adapters accept `event_bus`/`risk_manager` and publish `ORDER_PLACED`. Pre-trade risk checks run in Paper/Dhan/Upstox adapters. `DhanMarketFeed` publishes `TICK`/`DEPTH`, `DhanOrderStream` publishes `ORDER_UPDATED`/`TRADE`, and `UpstoxPortfolioStream` publishes `ORDER_UPDATED`/`POSITION_UPDATED`/`HOLDING_UPDATED`/`GTT_UPDATED` to the `EventBus`.

**Design:**
- Dhan `OrdersAdapter` no longer owns idempotency cache directly; it delegates to `OrderManager`.
- `DhanOrderStream` and `UpstoxPortfolioStream` publish `ORDER_UPDATE`/`TRADE` events to `EventBus`.
- `OrderManager` subscribes and updates orders/positions.

**Files:**
- `brokers/common/oms/context.py` (new)
- `brokers/dhan/orders.py`
- `brokers/dhan/connection.py`
- `brokers/dhan/factory.py`
- `brokers/upstox/orders/order_command_adapter.py`
- `brokers/upstox/broker.py`
- `brokers/upstox/factory.py`
- `brokers/paper/paper_orders.py`
- `brokers/paper/paper_gateway.py`
- `brokers/paper/mock_broker.py`
- `cli/services/oms_service.py`

---

## Phase 3 — Determinism & Durability (Weeks 4-6)

### 3.1 Per-Thread DB Connections

**Why:** `DataCatalog` and `TradeJournal` share one connection object, which is unsafe across threads.

**Design:**
- `DataCatalog`: use `threading.local()` connection or open read-only connections per query.
- `TradeJournal`: already SQLite WAL; ensure one connection per thread.
- `ViewManager`: keep as single object but document thread-affinity; add `read_only` mode for CLI reads.

**Status:** ✅ Done — `DataCatalog`, `TradeJournal`, and `ViewManager` now keep a per-thread connection map (`dict[thread_id, connection]` guarded by `threading.RLock`). Concurrent reads and writes no longer share connection objects, and `close()` cleans up all thread-local connections.

**Files:**
- `datalake/catalog.py`
- `datalake/journal.py`
- `analytics/views/manager.py`

**Tests:**
- `test_catalog_concurrent_register_symbol`
- `test_journal_concurrent_record_trade`

---

### 3.2 Versioned Materialized Snapshots

**Status:** ✅ Done — `ViewManager.materialize()` now writes to `market_data/materialized/versions/{table}/{timestamp}.parquet` and records the latest successful version in `latest.json`. `register_materialized()` creates a new table with a temporary name and atomically swaps it via `ALTER TABLE ... RENAME TO`, so readers never see a missing table. The last 3 versions are retained and older ones are cleaned up.

**Why:** `refresh()` drops all views before recreating; readers see broken state.

**Design:**
- Write materialized tables to timestamped directories: `market_data/materialized/versions/{table}/{timestamp}/`.
- Atomically swap via temporary table + `ALTER TABLE RENAME`.
- Keep last N versions for rollback.

**Files:**
- `analytics/views/manager.py`

**Tests:**
- `test_materialize_creates_versioned_snapshot`
- `test_refresh_is_atomic_readers_see_consistent_views`

---

### 3.3 Backtest Config Consistency

**Status:** ✅ Done — `slippage_pct` is now consistently interpreted as a percentage across `ReplayEngine`, `PaperEngine`, `FastBacktestEngine`, and `halftrend_backtest`. `ReplayConfig` validates non-negative slippage, positive `max_position_pct`, and non-negative `warmup_bars`. Default slippage values in `datalake/run_backtest.py` and `analytics/indicators/halftrend_backtest.py` updated from `0.001` (decimal) to `0.1` (0.1%).

**Why:** `FastBacktestEngine` and `ReplayEngine` interpreted `slippage_pct` differently; `analytics_replay.py` passed it unchecked.

**Design:**
- Unify units: `slippage_pct` is always a percentage (e.g., `0.01` = 0.01%).
- Add validation in `BacktestConfig`/`ReplayConfig`.

**Files:**
- `datalake/fast_backtest.py`
- `analytics/replay/models.py`
- `analytics/indicators/halftrend_backtest.py`
- `datalake/run_backtest.py`

**Tests:**
- `test_slippage_pct_must_be_non_negative`
- `test_max_position_pct_must_be_positive`
- `test_warmup_bars_must_be_non_negative`

---

## Phase 4 — Production Resilience (Weeks 6-8)

### 4.1 WebSocket Reconnect Backfill

**Status:** ✅ Done — `DhanMarketFeed` and `UpstoxMarketDataV3Multiplexer` track disconnect time and last tick time per symbol. On reconnect, if a `backfill_callback` is provided, it fetches missed bars from REST and publishes them as TICK events before resuming live feed. Supports both string and integer instrument formats.

**Why:** Dhan/Upstox reconnect without replaying missed ticks.

**Design:**
- On reconnect, record disconnect time.
- Backfill gap from REST historical API.
- Publish backfilled bars then resume live ticks.

**Files:**
- `brokers/dhan/websocket.py`
- `brokers/upstox/websocket/market_data_v3.py`
- `brokers/common/event_bus.py`

---

### 4.2 Persistent Event Log

**Status:** ✅ Done — New `brokers/common/event_log.py` writes append-only JSONL to `market_data/events/YYYY-MM-DD.jsonl`, fsyncs each line, and round-trips dataclass domain objects (including enums and `Decimal`). `EventBus` optionally persists every published event. `TradingContext` replays `ORDER_UPDATED`/`TRADE` events on startup to rebuild `OrderManager` and `PositionManager` state. Added guards so replay does not recursively re-log or read newly appended lines.

**Why:** Crash recovery requires durable order/trade/event history.

**Design:**
- Append-only JSONL event log: `market_data/events/YYYY-MM-DD.jsonl`.
- Log every `ORDER_UPDATE`, `TRADE`, `POSITION_UPDATE`.
- Replay log on startup to rebuild OMS state.

**Files:**
- `brokers/common/event_log.py` (new)
- `brokers/common/event_bus.py`
- `brokers/common/oms/context.py`
- `brokers/common/oms/order_manager.py`

**Tests:**
- `test_append_and_replay`
- `test_event_bus_persists_events`
- `test_trading_context_replays_event_log`

---

### 4.3 Active Reconciliation

**Status:** ✅ Done — `DhanReconciliationService` and `UpstoxReconciliationService` now accept an `oms` parameter and `auto_repair=True` to upsert missing orders and positions from broker state. `OrderManager.get_all_orders()` and `PositionManager.upsert_position()` provide reconciliation-compatible dict interfaces. `TradingContext` accepts a `reconciliation_service` and runs periodic reconciliation via a background timer thread.

**Why:** Reconciliation services detect drift but do not repair by default.

**Design:**
- Make reconciliation authoritative: broker state wins.
- Run on timer and on reconnect.
- Update local OMS state after reconciliation.

**Files:**
- `brokers/dhan/reconciliation.py`
- `brokers/upstox/reconciliation/service.py`
- `brokers/common/oms/order_manager.py`

---

## Multi-Agent Team Assignments

| Agent | Phase 1 Responsibility | Deliverables |
|-------|------------------------|--------------|
| **Agent A — OMS** | Immutable domain objects + lock Paper/Mock OMS | PR with domain.py frozen, paper_orders.py locked, tests |
| **Agent B — Dhan Safety** | Lock idempotency cache + protect Dhan callbacks | PR with orders.py + websocket.py fixes, tests |
| **Agent C — Upstox Safety** | Fix Upstox streaming + listener safety | PR with gateway.py + websocket fixes, tests |
| **Agent D — Determinism** | Scanner/ranking/view tie-breakers + HalfTrend scan | PR with stable sorts, SQL fixes, tests |
| **Agent E — Data Lake I/O** | Atomic Parquet/env writes + DuckDB read-only | PR with datalake/io.py, atomic writes, tests |
| **Agent F — Architecture** | Design EventBus + OrderManager + PositionManager + RiskManager | PR with new modules and integration tests |

---

## Testing Strategy

1. **Unit tests** for every new immutable helper and lock.
2. **Concurrency stress tests** using `threading.Thread` and `ThreadPoolExecutor`:
   - 10 threads place orders with same correlation id → exactly 1 order.
   - 10 threads read positions while 10 threads place orders → no crash, consistent final state.
3. **Determinism tests**:
   - Same scanner input run 10 times → identical output order.
   - Same backtest input run 10 times → identical trades/equity.
4. **Integration tests**:
   - WebSocket callback registration during tick flow.
   - Atomic Parquet write while reader loops.
   - View refresh while reader queries.
5. **Failure scenario tests**:
   - Broker disconnect/reconnect.
   - Kill-switch activation.
   - Process crash mid-order.

---

## Success Criteria

- [x] All 1128 existing tests pass.
- [x] New concurrency tests pass with 20+ threads.
- [x] No mutable shared state in Paper/Mock OMS.
- [x] No unprotected callback/listener lists.
- [x] Same scanner input produces identical output across runs.
- [x] Phase 4 production resilience (WebSocket backfill, persistent event log, active reconciliation).
- [ ] Same backtest input produces identical trades across 100 runs.
- [ ] Concurrent readers never see partial Parquet files.
- [ ] Duplicate order rate is zero under stress.
- [ ] Risk checks block orders that exceed limits, even under concurrency.
