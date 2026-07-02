# ADR-013: Master Remediation Plan — Platform Hardening

## Status

Accepted — 2026-07-02

## Context

The TradeXV2 platform underwent a comprehensive audit via the `quant-platform-orchestrator` agent, identifying critical issues across architecture, event-driven design, broker adapters, and operational readiness. This ADR documents the remediation decisions and their rationale.

## Decisions

### B1: MarketBridge O(N×M) → O(N+M) Optimization

**Problem:** The `MarketBridge._dispatch_loop` iterated over all connections × all subscriptions per event, causing O(N×M) complexity.

**Solution:** Introduced a reverse index (`_symbol_index: dict[str, set[str]]`) in `MarketConnectionManager` for O(1) symbol→connection routing. The bridge now formats each message once and uses the index to find target connections.

**Files:** `api/ws/market.py`, `api/ws/bridge.py`

### B2: Centralized Data Root Paths

**Problem:** Multiple modules hardcoded `"market_data"` as the default data root, causing CWD-dependent path issues.

**Solution:** All modules now import `DEFAULT_DATA_ROOT` from `datalake/core/paths.py` as the single source of truth.

**Files:** `analytics/views/base.py`, `analytics/precompute_features.py`, `analytics/replay/orchestrator.py`, `analytics/__init__.py`, `analytics/indicators/halftrend_backtest.py`

### B3: Typed Gateway Resolution

**Problem:** `feed_wiring.py` used string-based attribute probing (`_gateway`, `_upstox_gateway`) to find the active gateway.

**Solution:** Added `active_gateway` property to `BrokerService` returning the typed `MarketDataGateway | None`. Updated `_resolve_gateway` to check this property first.

**Files:** `cli/services/broker_service.py`, `api/ws/feed_wiring.py`

### B4: Dead MetricsCollector Code Removal

**Problem:** `render_prometheus_metrics()` accepted a `collector_snapshot` parameter that was never populated by any caller. Three `_render_collector_*` functions (~80 lines) were dead code.

**Solution:** Removed the parameter and dead functions.

**Files:** `infrastructure/observability/http_server.py`

### B5: HttpRequestMetrics Migration to Central Registry

**Problem:** `HttpRequestMetrics` in `api/middleware.py` maintained its own thread-safe counters, duplicating the central `MetricsRegistry` functionality.

**Solution:** Extended `MetricsRegistry` with `LabelledCounter`, `LabelledGauge`, and `LabelledHistogram` types supporting dynamic label combinations. Refactored `HttpRequestMetrics` to delegate to the central registry.

**Files:** `infrastructure/metrics/types.py`, `infrastructure/metrics/registry.py`, `api/middleware.py`

### B6: Broker Adapter Interface Normalization

**Problem:** Dhan's `OrdersAdapter` returned `Order` and raised `OrderError`, while Upstox's `UpstoxOrderCommandAdapter` returned `OrderResponse` and used `OrderResponse.fail()`. This divergence required the gateway layer to normalize errors.

**Solution:** Normalized Dhan's adapter to match Upstox's pattern:
- `place_order()` now returns `OrderResponse`
- `modify_order()` now returns `OrderResponse`
- `cancel_order()` now returns `OrderResponse.fail()` instead of raising `OrderError`
- `IdempotencyCache` now stores `OrderResponse` instead of `Order`

**Files:** `brokers/dhan/orders.py`, `brokers/dhan/gateway.py`, `brokers/dhan/tests/unit/test_orders.py`, `brokers/dhan/tests/unit/test_orders_idempotency.py`, `brokers/dhan/tests/unit/test_gateway.py`

### B7: Duplicate ORDER_PLACED Event Fix

**Problem:** When orders were submitted through the OMS, both the OMS and the broker adapter published `ORDER_PLACED` events, causing duplicate event processing.

**Solution:** Introduced `application/execution/context.py` with an `oms_managed()` context manager using `contextvars.ContextVar`. The `make_gateway_submit_fn` wraps the gateway call in this context, and both Dhan/Upstox adapters check `is_oms_managed_submit()` before publishing events.

**Files:** `application/execution/context.py`, `application/execution/gateway_submit.py`, `brokers/dhan/orders.py`, `brokers/upstox/orders/order_command_adapter.py`

### C1: Analytics Feature Test Coverage

**Problem:** 11 Feature classes in `analytics/indicators/` had no test coverage.

**Solution:** Added tests for `RelativeVolume`, `VolumeSMA`, `SwingHighLow`, `PriceDistance`, `Gap`, `Trend`, `AtrPercent`, `ZScore`, `Correlation`, `Beta`, `PercentRank`.

**Files:** `analytics/tests/test_indicators.py`

### C2: Containerization

**Problem:** No Docker support for deployment or local development.

**Solution:** Added multi-stage `Dockerfile`, `Dockerfile.dev` for hot-reload, `docker-compose.yml` with Prometheus and Grafana for monitoring, and `.dockerignore`.

**Files:** `Dockerfile`, `Dockerfile.dev`, `docker-compose.yml`, `.dockerignore`, `docker/prometheus/prometheus.yml`, `docker/grafana/provisioning/`

### C5: Analytics Coverage Gate

**Problem:** No mechanism to prevent future Feature classes from being added without tests.

**Solution:** Added `test_all_feature_classes_have_tests()` that dynamically discovers all `Feature` subclasses and asserts each has a corresponding test.

**Files:** `analytics/tests/test_indicators.py`

## Consequences

### Positive
- Consistent broker adapter interface reduces cognitive load and bug surface
- Central metrics registry enables unified observability
- O(N+M) WebSocket dispatch scales to hundreds of connections
- Containerization enables reproducible deployments
- Coverage gate prevents future test debt

### Negative
- B6 changes the Dhan adapter's public API (return type change from `Order` to `OrderResponse`)
- B5 adds complexity to `MetricsRegistry` with labelled metric types

### Neutral
- B7's context variable approach is thread-safe but adds implicit state propagation

## Deferred Items

- **B5 (partial):** `HttpRequestMetrics` label-series support in `MetricsRegistry` is complete, but full migration of all HTTP metrics rendering to the registry's Prometheus export is pending.
- **B6 (full):** The dual `MarketDataGateway` / `CommonBrokerGateway` interface divergence remains. This requires a larger architectural decision about which interface to keep.
- **C3:** Documentation sync for the above changes.
- **C4:** Full broker refactoring plan (merging the two gateway interfaces).
