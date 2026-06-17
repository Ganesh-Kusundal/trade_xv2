# Code Review: TradeXV2 Upstox & Common Broker Layer

**Reviewers:** Martin Fowler, Robert C. Martin, Dr. Venkat Subramaniam, Principal Staff Engineer, SRE Engineer, Security Engineer, Quant Trading Systems Architect  
**Date:** 2026-06-17  
**Scope:** Entire codebase (brokers/common, brokers/upstox, brokers/dhan, tests, cli, datalake, docs)  
**Base commit:** (working tree review)

---

## Executive Summary

The codebase demonstrates mature architecture intent (ADR-001 through ADR-005, frozen `MarketDataGateway` v1.0 ABC, single-source domain types) and strong test discipline (~140 test files). However, the **Upstox broker implementation** (particularly `brokers/upstox/gateway.py` and `brokers/upstox/broker.py`) has drifted significantly from the established architectural contracts. The most critical finding is an **architectural boundary violation**: 20+ non-ABC methods have been added to `UpstoxBrokerGateway`, which should be a thin sync facade. The `broker.py` is a 292-line god constructor with 50+ adapter instantiations, directly contradicting the existing Dhan pattern (`DhanConnection`). One **P0 security finding** exists: `pickle.load` deserialization of untrusted instrument data. Multiple cross-cutting concern gaps exist: no correlation IDs on domain events, no structured tracing context, and the in-process `EventMetrics` has not been replaced with a Prometheus/OTel backend as documented.

**Safe for production deployment: NO.** P0 and P1 issues must be resolved before production.

---

## 1. Hardcoded Values

| Severity | File | Line | Value | Root Cause | Recommended Fix |
|---|---|---|---|---|---|
| **P1** | `brokers/upstox/instruments/loader.py` | 31 | `"https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"` | CDN URL hardcoded | Extract to `UpstoxApiUrlResolver` or `UpstoxConnectionSettings` |
| **P1** | `brokers/upstox/market_data/historical_v3.py` | 21 | `"https://api.upstox.com/v3"` | V3 base URL hardcoded | Derive from `settings.base_v2` (same as urls.py `_v3()`) |
| **P2** | `brokers/dhan/http_client.py` | 18 | `"https://api.dhan.co/v2"` | Dhan base URL hardcoded | Accept from factory with env override (already partially done via `base_url` param) |
| **P1** | `brokers/dhan/factory.py` | 24, 271-272 | `"https://auth.dhan.co/app/generateAccessToken"` | TOTP URL hardcoded | Extract to `UpstoxConnectionSettings` or constants module |
| **P2** | `brokers/dhan/factory.py` | 27 | `86400` (24h) | Token lifetime as magic number | Named constant `_TOKEN_LIFETIME_SECONDS` (exists but unclear why not configurable) |
| **P2** | `brokers/dhan/factory.py` | 30 | `20 * 60` (1200s) | Scheduler interval hardcoded | Document rationale; possibly make configurable |
| **P2** | `brokers/dhan/factory.py` | 33 | `600` (10min buffer) | Refresh buffer as magic number | Document; align with token manager's `refresh_buffer_minutes` |
| **P2** | `brokers/dhan/http_client.py` | 25-32 | `_RATE_LIMITS` dict with float values | Rate limits as module-level constant | Extract to `CircuitBreakerConfig` or broker settings |
| **P2** | `brokers/dhan/http_client.py` | 35-37 | `_MAX_RETRIES=3`, `_BASE_DELAY_MS=500`, `_MAX_DELAY_MS=5000` | Retry config hardcoded | Extract to named config class |
| **P2** | `brokers/upstox/auth/config.py` | 47-48 | `ws_reconnect_interval_s: int = 10`, `ws_reconnect_max_retries: int = 5` | Magic numbers for WS reconnect | Document rationale; possibly make configurable via env |
| **P2** | `brokers/upstox/gateway.py` | 410 | `results[:20]` in `search()` | Arbitrary limit of 20 | Make configurable or use `BrokerCapabilities` |
| **P2** | `brokers/upstox/instruments/loader.py` | 33 | `CACHE_VALIDITY_HOURS = 24` | Cache validity as module constant | Accept from settings to allow per-environment tuning |
| **P2** | `brokers/upstox/instruments/loader.py` | 198 | `"CHUNK_SIZE = 64 * 1024"` | Download chunk size | Make configurable |
| **P2** | `brokers/common/batch_mixin.py` | 37 | `_batch_max_workers: int = 5` | Hardcoded thread pool size | Make configurable per gateway; align with Dhan's `history_batch` which uses 5 |
| **P3** | `brokers/upstox/gateway.py` | 192 | `Path(".cache/upstox/complete.json.gz")` | Hardcoded cache path | Use `settings.instrument_cache_path` (already accepted by `load_instruments`) |
| **P3** | `brokers/upstox/factory.py` | 32 | `Path(".env.local")` | Default env path | Accept from `UpstoxSettingsLoader.DEFAULT_ENV_PATHS` |
| **P3** | `brokers/upstox/http.py` | 47 | `timeout_seconds: int = 15` | HTTP timeout magic number | Extract to settings |
| **P3** | `brokers/upstox/http.py` | 54 | `rate_per_second=10.0` | Rate limiter default | Align with `BrokerCapabilities.rate_limit_per_second` |

---

## 2. Architecture Compliance

### 2.1 UpstoxBrokerGateway violates facade pattern (P0)

**File:** `brokers/upstox/gateway.py` (713 lines)  
**Issue:** `UpstoxBrokerGateway` is marketed as "thin sync facade" but contains 20+ non-ABC methods:

```python
# lines 150-188 — non-ABC methods on the Gateway facade
get_ipos()                  # Not in MarketDataGateway ABC
initiate_payout()           # Not in MarketDataGateway ABC  
get_payouts()               # Not in MarketDataGateway ABC
modify_payout()             # Not in MarketDataGateway ABC
cancel_payout()             # Not in MarketDataGateway ABC
get_mutual_fund_holdings()  # Not in MarketDataGateway ABC
place_mutual_fund_order()   # Not in MarketDataGateway ABC
get_pnl()                   # Not in MarketDataGateway ABC
get_balance_sheet()         # Not in MarketDataGateway ABC
get_cash_flow()             # Not in MarketDataGateway ABC
get_ratios()                # Not in MarketDataGateway ABC
get_user_profile()          # Not in MarketDataGateway ABC
convert_position()          # Not in MarketDataGateway ABC
get_trade_pnl()             # Not in MarketDataGateway ABC
```

**Root Cause:** Feature addition bypassed the `MarketDataGateway` v1.0 frozen contract. Each new capability was added directly to the gateway rather than being exposed via a capability-specific port or service.  
**Impact:** Any code that consumes `UpstoxBrokerGateway` directly (including `IntelligentGateway` and CLI commands) now has access to methods that don't exist on Dhan or Paper gateways, creating a `AttributeError` risk when switching brokers. Refactoring these out later will be a breaking change for all consumers.  
**Regression Risk: HIGH** — Every CLI command and OMS service that currently calls `gateway.get_pnl(...)` will break when these are moved.  
**Recommended Fix:** Move these methods to a `UpstoxExtendedCapabilities` service or expose them through the `BrokerCapabilities` registry via capability strings. The gateway's `__getattr__` could delegate to `self._broker.capabilities[cap]` for registered capabilities.

### 2.2 UpstoxBroker is a 292-line god constructor (P1)

**File:** `brokers/upstox/broker.py`  
**Issue:** The constructor instantiates ~50 adapters inline (MarketDataV2, MarketDataV3, HistoricalV2, HistoricalV3, Options, Portfolio, Margin, MarketStatus, Futures, ExpiredInstruments, GTT, News, Intelligence, KillSwitch, StaticIP, IPO, Payments, MutualFunds, Fundamentals, OrderClient, IdempotencyCache, OrderCommand, OrderQuery, GTT, Slice, Cover, Alert, V3SubscriptionLimits, V3Decoder, AutoReconnect, Multiplexer, FeedAuthorizer, InstrumentResolver, InstrumentLoader, InstrumentSearch). This is directly analogous to `DhanConnection` which exists *precisely* to avoid this anti-pattern in the Dhan broker.  

**Root Cause:** The `UpstoxBroker` class conflates two responsibilities: (1) wiring/wiring configuration, and (2) being a port aggregator implementing `BrokerConnection`.  
**Regression Risk:** HIGH — Splitting this out is the correct fix but requires rethinking the factory.  
**Recommended Fix:** Create an `UpstoxConnection` class mirroring `DhanConnection` that receives `UpstoxAdapterContext` (or its sub-components) and wires all adapters. `UpstoxBroker` then holds a single `UpstoxConnection` instance and delegates property accesses.

### 2.3 No Upstox equivalent of BrokerProviderFactory (P2)

**File:** `brokers/common/factory.py` vs `brokers/upstox/factory.py`  
**Issue:** `UpstoxBrokerFactory.create()` is a `@staticmethod` with signature `(env_path, load_instruments, analytics_only, event_bus, risk_manager, backfill_callback, reconciliation_service)` but `BrokerProviderFactory.create()` requires `(env_path, load_instruments, event_bus, risk_manager, lifecycle)`. The `UpstoxBrokerFactory` does not implement `BrokerProviderFactory`. Polymorphic factory usage via the ABC is impossible.  

**Root Cause:** Factory interface was defined after Upstox factory was already implemented; no refactor was done.  
**Regression Risk: MEDIUM** — `BrokerService` in CLI currently has broker-specific factory calls.

### 2.4 Intrusive gateway method proliferation vs Dhan pattern (P1)

**File:** `brokers/dhan/gateway.py` vs `brokers/upstox/gateway.py`  
**Issue:** Dhan gateway exposes all broker-specific methods via `.ledger`, `.user_profile`, `.ip_management`, `.edis`, `.exit_all`, `.super_orders`, `.forever_orders`, `.conditional_triggers`, etc. **as properties** returning the sub-adapter. This is the established pattern. Upstox instead injects methods directly onto the gateway object. Both patterns are suboptimal but Dhan's is at least consistent.  

**Root Cause:** Inconsistent design decisions between Dhan (properties) and Upstox (methods) for the same capability.  
**Recommended Fix:** Extend `MarketDataGateway` with capability-based access, or standardize on the property approach used by Dhan.

### 2.5 Duplicate imports in BatchFetchMixin (P2)

**File:** `brokers/common/batch_mixin.py` lines 20-25  
**Issue:** `typing.Any`, `pandas as pd`, and `logging.getLogger` are imported twice (lines 10-13 and 20-25). This is clearly a copy-paste error.  
**Root Cause:** Incomplete refactor.  
**Regression Risk: LOW** — Dead imports that will trigger mypy warnings or ruff errors.

### 2.6 Adapter redundancy (P3)

**File:** `brokers/upstox/market_data/margin_adapter.py` (16 lines)  
**Issue:** `UpstoxMarginAdapter` has only a `calculate_margin` method that delegates entirely to the client. This is identical to the pattern in `UpstoxIpoAdapter` and `UpstoxMutualFundsAdapter`. All three could be eliminated by accepting the client directly wherever the adapter is used (the gateway already accesses `self._broker.margin`).  
**Root Cause:** Over-engineering in the adapter layer — adapters that contain no transformation logic add indirection without value.

---

## 3. TDD Compliance

### 3.1 Missing failure-path tests for new adapters (P1)

**Files:** `brokers/upstox/ipo/adapter.py`, `payments/adapter.py`, `mutual_funds/adapter.py`, `fundamentals/adapter.py`  
**Issue:** `test_new_features.py` covers only the happy path with `MagicMock` returning `{"status": "success", "data": [...]}`. No tests exist for:
- HTTP 401/403/429/500 responses
- Malformed `data` fields (None, string instead of list)
- Empty `body` / missing `data` key
- Network timeouts
- `UpstoxApiError`/`UpstoxAuthError` propagation  

**Regression Risk: HIGH** — These adapters call real REST endpoints. A network glitch or Upstox schema change will cause `KeyError` or `AttributeError` to propagate up uncaught.

### 3.2 No integration tests for gateway methods (P1)

**Files:** `brokers/upstox/gateway.py` (lines 150-188)  
**Issue:** `test_new_features.py::TestUpstoxGatewayNewFeatures` only tests that properties are not None. It never calls `gateway.get_ipos()`, `gateway.initiate_payout()`, etc. with a real or fake HTTP client.  
**Regression Risk:** HIGH — A bug in the adapter delegation chain will not be caught.

### 3.3 Missing contract tests for new BrokerCapabilities flags (P2)

**Files:** `tests/architecture/test_gateway_signatures.py`  
**Issue:** The architecture tests verify ABC methods only. `BrokerCapabilities` is a frozen dataclass with new fields (`ipo`, `mutual_funds`, `fundamentals`, `payments`, `trade_pnl`, `convert_position`, `user_profile`). No architecture test verifies that `IntelligentGateway` or CLI commands correctly check these flags before calling the methods.  

**Regression Risk: MEDIUM** — `IntelligentGateway` doesn't route new capabilities; if a user calls `gateway.get_ipos()` against `IntelligentGateway`, it will raise `AttributeError` or silently fall through.

### 3.4 Legacy Dhan gateway uses *args, **kwargs (P1)

**File:** `brokers/dhan/gateway.py` line 112  
**Issue:** `place_order(self, *args, **kwargs)` bypasses type checking and the frozen `MarketDataGateway` contract. Any parameter ordering mismatch is silently accepted.  

**Root Cause:** Dhan's `OrdersAdapter.place_order()` takes positional arguments; the gateway was never updated when `MarketDataGateway.place_order()` was frozen.  
**Recommended Fix:** Update Dhan gateway to explicitly match the ABC signature. Update `OrdersAdapter.place_order()` call site accordingly.

### 3.5 Bare `except Exception: pass` risk (P2)

**Files:** `brokers/upstox/market_data/historical_v3.py` not applicable; but `UpstoxBrokerGateway._translate_tick_to_quote()` line 611 has `except Exception: ... return raw` which is fine with logging. The real concern is in `brokers/upstox/auth/token_manager.py` line 362 `except OSError as exc: logger.warning(...)` — silent failure to persist token state. In production this means the token is lost on restart but the process continues.

---

## 4. Cross-Cutting Concerns

### 4.1 No Correlation IDs on domain models (P1)

**Files:** `brokers/common/core/models.py`  
**Issue:** `Order` has `correlation_id` but `Trade`, `Position`, `Holding`, and `Quote` do not. The `EventBus` events (`DomainEvent`) have no `correlation_id` field. When a CLI command places an order and receives a `Trade` event, there is no way to correlate them across log lines.  
**Root Cause:** `correlation_id` was added to `OrderRequest` → `OrderResponse` but not propagated to downstream events.  
**Recommended Fix:** Add `correlation_id: str | None = None` to `DomainEvent` and all domain models. Thread it from `place_order(correlation_id=...)` through to order book, trade book, and WebSocket tick callbacks.

### 4.2 EventMetrics is a stub — never replaced (P1)

**File:** `brokers/common/observability/event_metrics.py` + `brokers/common/intelligent_gateway.py`  
**Issue:** The docstring says "A production deployment should replace it with a Prometheus / OpenTelemetry exporter" but this has never happened. All metrics are in-process counters only. If the process restarts, all historical metrics are lost. No `/metrics` HTTP endpoint exists for Prometheus scraping.  
**Root Cause:** Workaround that became permanent.  
**Recommended Fix:** Add a `PrometheusEventMetrics` backend behind a `CounterStore` interface. Expose at the observability HTTP server (`brokers/common/observability/`).

### 4.3 No distributed tracing (P2)

**Files:** entire codebase  
**Issue:** No `trace_id` or `span_id` propagation. All log entries use `extra={}` dicts but there is no correlation between HTTP request lifecycle, gateway method calls, and event bus handler invocations.  
**Root Cause:** Tracing was planned but never implemented.

### 4.4 Incomplete circuit breaker coverage on Upstox (P2)

**Files:** `brokers/upstox/http.py`, `brokers/dhan/http_client.py`  
**Issue:** Dhan's `http_client` has three separate circuit breakers (read, write, admin) with documented failure thresholds. Upstox's `http.py` has no circuit breaker integration at all. A burst of Upstox HTTP failures will not trigger a fast-fail; callers will block on socket timeouts (15s default).  
**Root Cause:** Circuit breaker was implemented only for Dhan during the certification phase.  
**Recommended Fix:** Wire `CircuitBreaker` into `UpstoxHttpClient._request()` with category-based routing (same prefix-matching approach as Dhan).

### 4.5 No HTTP retry on Upstox (P2)

**Files:** `brokers/upstox/http.py`, `brokers/dhan/http_client.py`  
**Issue:** Dhan's `http_client.py` has `_MAX_RETRIES = 3`, exponential backoff, token refresh on 401, and rate-limit backoff on 429. Upstox's `http.py` has none of these — it raises on the first non-2xx.  
**Recommended Fix:** Extract retry logic into `brokers/common/resilience/` and use it from both `DhanHttpClient` and `UpstoxHttpClient`.

### 4.6 Token refresh race condition (P2)

**Files:** `brokers/upstox/auth/token_manager.py` lines 110-123  
**Issue:** `ensure_valid()` acquires `self._lock` (an `RLock`) and calls `self._refresh_now()` which *also* acquires `self._lock` (line 126). This is safe because it's an `RLock`. However, the HTTP client's `_try_refresh_token()` and the `TokenRefreshScheduler` may call into the token manager concurrently. The `UpstoxTokenManager` is thread-safe, but the caller (`UpstoxHttpClient._request()`) does not hold a lock. Concurrent refresh requests from 20+ threads will queue on the RLock, potentially causing latency spikes.  
**Recommended Fix:** Document that concurrent refresh is safe (it is, but the latency spike during the lock hold is not).

### 4.7 Backoff functions duplicated (P2)

**Files:** `brokers/dhan/http_client.py` line 303 `_backoff_delay()` and `brokers/common/resilience/`  
**Issue:** Dhan's retry backoff lives in `http_client.py` as a static method. The common resilience module has its own backoff.  
**Root Cause:** Common resilience module exists but wasn't used by Dhan when it was being built.

---

## 5. Production Readiness

### 5.1 pickle.load of untrusted data (P0 — SECURITY)

**File:** `brokers/upstox/instruments/loader.py` lines 96-131  
**Issue:**
```python
with open(pkl_path, 'rb') as f:
    defs = pickle.load(f)  # line 103 — ARBITRARY CODE EXECUTION
```
A malicious actor who can write to `.cache/upstox/instruments.pkl` (e.g., via a compromised CDN, shared filesystem, or supply-chain attack on the instrument CDN) can execute arbitrary Python code on every client load.  

**Root Cause:** Pickle was chosen for performance (faster than JSON parsing) without security review.  
**Regression Risk:** HIGH — Changing the serialization format changes cache invalidation and load times.  
**Recommended Fix:** Replace with `json` (plus gzip if needed) or `marshal` (still unsafe but less common). The ~2s parse time cited in the log message (line 104) can be reduced through streaming JSON parsing or by caching the parsed `UpstoxInstrumentDefinition` objects as a compact binary format via `struct` or `msgpack` (which has no arbitrary code execution on decode).

### 5.2 Race condition in Dhan depth feeds (P2)

**File:** `brokers/dhan/gateway.py` lines 198-199, 258-259  
**Issue:** `feed.start()` is called without holding a lock. Between `if not (feed._thread and feed._thread.is_alive())` and `feed.start()`, another thread could also call `start()`. The `DhanDepth20Feed` and `DhanDepth200Feed` classes likely have internal guards, but this is not verified.  
**Root Cause:** Lazy initialization pattern without thread-safe double-check.

### 5.3 Hardcoded thread pool size 5 in Dhan history_batch (P2)

**File:** `brokers/dhan/gateway.py` line 583  
**Issue:** `ThreadPoolExecutor(max_workers=5)` is hardcoded. The `BatchFetchMixin` has `_batch_max_workers = 5` but Dhan overrides this inline. These should be unified.

### 5.4 Dead code / commented code / debug statements (P1)

**Files:** Multiple  
**Observations:**
- `brokers/upstox/gateway.py` line 192: `import logging` / `import time` / `from pathlib import Path` are **inline imports** inside `load_instruments`. These should be at module level.  
- `brokers/upstox/gateway.py` line 612: `import logging` inside `_translate_tick_to_quote` exception handler — already imported at module level.  
- `brokers/upstox/gateway.py` line 265: `from datetime import datetime` inside `_fetch_history` — already imported at module level.  
- `brokers/upstox/gateway.py` line 448: `import asyncio` inside `stream()` — acceptable but notable.  
- `brokers/upstox/broker.py` line 167: `self.market_data_v3_adapter = self.market_data  # alias` — unnecessary alias that increases maintenance surface.  
- `brokers/common/batch_mixin.py` lines 20-25: Duplicate imports (see Architecture §2.2).

### 5.5 Unused imports / attributes (P3)

**File:** `brokers/upstox/market_data/historical_v2.py` line 11  
**Issue:** `UpstoxApiUrlResolver` is imported but `self._urls` is not used in `get_candles` — the URL is fully constructed inline via `self._urls.historical_candle_url(...)`. This is correct usage but the linter may flag it as unused if misconfigured.

### 5.6 Debug logging in exception handlers (P2)

**File:** `brokers/upstox/gateway.py` lines 612-616  
**Issue:** In `_translate_tick_to_quote`, on exception the code logs at `debug` level with `exc_info=True`. If an invalid tick from Upstox is causing the exception, this should be at `warning` or `error` level. A continuously failing tick will produce no alerts in production.

### 5.7 No WS reconnect backfill timeout (P2)

**File:** `brokers/upstox/websocket/market_data_v3.py` (307 lines)  
**Issue:** The `backfill_callback` is invoked synchronously during reconnect. If the callback takes >30s (e.g., slow HTTP request for missed bars), the WebSocket reconnection handshake may timeout. There is no timeout guard on the backfill call.

### 5.8 `time.sleep` in rate limiter blocks event loop (P2)

**File:** `brokers/upstox/http.py` lines 34-36  
**Issue:** `UpstoxRateLimiter.acquire()` calls `time.sleep()` which blocks the calling thread. If this is called from an async context (e.g., inside asyncio), it will block the event loop.  
**Root Cause:** Sync HTTP client — not async-aware.

---

## 6. Security Review

### 6.1 pickle.load arbitrary code execution (P0)

**File:** `brokers/upstox/instruments/loader.py` line 103  
**Severity:** P0 — Remote Code Execution  
**Detail:** See §5.1

### 6.2 Secrets in plain text logs (P1)

**File:** `brokers/dhan/factory.py` lines 323, 328  
**Issue:** `_update_env_token()` writes `DHAN_ACCESS_TOKEN=<token>` directly to `.env.local` without masking. If the env file is accidentally committed or logged, the token is exposed.  
**Root Cause:** Convenience feature (auto-update .env) with no secret-masking.  
**Recommended Fix:** Use the `JsonTokenStateStore` as the canonical persistence and write only a reference token to .env.

### 6.3 No input validation on order payloads (P1)

**File:** `brokers/upstox/orders/order_command_adapter.py`, `brokers/upstox/mappers/domain_mapper.py`  
**Issue:** `UpstoxDomainMapper.to_place_payload()` accepts any `OrderRequest` and converts it to a dict. There is no validation that:
- `quantity > 0`
- `price >= 0` for LIMIT orders
- `trigger_price >= 0` for SL orders
- `instrument_key` is non-empty  
These validations exist in the OMS `RiskManager` but if an order bypasses it (e.g., direct gateway call), an invalid payload reaches Upstox's API which will reject it with a generic error.  
**Recommended Fix:** Add schema validation in `to_place_payload()` or in the `OrderRequest` domain model itself.

### 6.4 No authorization checks in new adapter methods (P2)

**File:** `brokers/upstox/gateway.py` lines 150-188  
**Issue:** Methods like `initiate_payout()`, `cancel_payout()`, `place_mutual_fund_order()`, `get_pnl()` have no guard checking `settings.allow_live_orders`. A paper-trading or read-only session could accidentally place an MF order or initiate a payout.  
**Root Cause:** These methods were added without the same security guard that `place_order()` has.

### 6.5 Token written to disk without masking (P1)

**File:** `brokers/dhan/factory.py` lines 323-340  
**Issue:** The `_update_env_token()` function writes the raw JWT to `.env.local`. Additionally, `JsonTokenStateStore` writes the token to `runtime/dhan-token-state.json`. Both files should have `chmod 600` (the env file update does not set permissions).

### 6.6 No request signing or HMAC (P2)

**File:** `brokers/upstox/http.py`, `brokers/dhan/http_client.py`  
**Issue:** Upstox and Dhan REST API calls use only `Authorization: Bearer <token>` headers. No request timestamp, nonce, or signature is used. If the token is intercepted, it can be replayed. This is inherent to the broker APIs (they don't require signing), but the risk should be documented.

### 6.7 No TLS certificate pinning (P3)

**File:** all HTTP clients  
**Issue:** Single-head `requests.Session()` with default cert verification. No certificate pinning for `api.upstox.com` or `api.dhan.co`. Acceptable for most deployments but noted for compliance-sensitive environments.

---

## 7. Broker Implementation Consistency

### 7.1 Dhan vs Upstox: history() implementation divergence (P1)

**File:** `brokers/dhan/gateway.py` lines 268-292 vs `brokers/upstox/gateway.py` lines 225-306  
**Issue:** Both gateways implement `history()` and contain inline interval mapping and V3/V2 API routing. This logic is duplicated with slight variations:
- Dhan: maps timeframe → calls `_conn.historical.get_historical(symbol, exchange, from, to, tf)`
- Upstox: maps timeframe → calls `_fetch_history()` → `_broker.historical_v3.get_candles(...)` with inline unit/interval logic  
**Root Cause:** Both brokers evolved independently. No shared `HistoricalDataService` is wired into the gateway path (it exists in `brokers/common/services/historical_data.py` but is only used by `UpstoxBroker.historical_service`).  
**Recommended Fix:** Move interval mapping into `UpstoxHistoricalV3Client` and `DhanHistoricalAdapter`. Both gateways become thin pass-through.

### 7.2 Dhan vs Upstox: stream() inconsistency (P1)

**File:** `brokers/dhan/gateway.py` lines 497-561 vs `brokers/upstox/gateway.py` lines 412-470  
**Issue:** Both `stream()` methods manage WebSocket lifecycle (connect if not connected, subscribe, add listener). However:
- Dhan `stream()` returns `feed` (the DhanMarketFeed object) directly
- Upstox `stream()` returns `ws` (the multiplexer) but handles `asyncio.get_event_loop()` imperatively  
The Upstox version calls `ws.is_connected` (property) to check state, then `ws.connect()` (async) from sync context. This is fragile: if called from within an already-running event loop (e.g., inside a Jupyter notebook or async CLI), `asyncio.get_event_loop()` will return the running loop and `loop.run_until_complete()` will fail with `RuntimeError: This event loop is already running`.  
**Root Cause:** Mixed sync/async boundary not handled correctly.  
**Regression Risk: HIGH** — This will crash when called from an async context.

### 7.3 Instrument cache path inconsistency (P1)

**File:** `brokers/upstox/auth/config.py` line 34, `brokers/upstox/gateway.py` line 198, `brokers/dhan/gateway.py` line 126  
**Issue:** Upstox hardcodes `.cache/upstox/complete.json.gz` in `config.py` and `gateway.py`. Dhan uses `InstrumentLoader.load_cached()` which uses a different path resolution. These should be uniform or both derived from a single root `Path("market_data/instruments")` or env var.

### 7.4 Capability registration parity gap (P2)

**File:** `brokers/upstox/broker.py` lines 246-275  
**Issue:** Upstox registers 30 capabilities. Dhan's `BrokerGateway.capabilities()` returns fewer flags. The new Upstox capabilities (`IPO`, `PAYMENTS`, `MUTUAL_FUNDS`, `FUNDAMENTALS`, `WEBHOOKS`, `PORTFOLIO_STREAM`, `OPTION_GREEKS`) have no equivalent in Dhan. This is expected but:  
- `IntelligentGateway` does not route these capabilities to any broker.  
- CLI commands calling `get_ipos` via `IntelligentGateway` will get `AttributeError`.  
**Recommended Fix:** Add routing methods to `IntelligentGateway` for new capabilities, or raise `NotImplementedError` with a clear message.

### 7.5 Dhan gateway `place_order` signature mismatch (P1)

**File:** `brokers/dhan/gateway.py` line 112  
**Issue:** `place_order(self, *args, **kwargs)` bypasses the `MarketDataGateway` ABC contract. The ABC defines explicit typed parameters (`symbol`, `exchange`, `side`, `quantity`, `price`, `order_type`, `product_type`, `validity`, `trigger_price`, `correlation_id`).  
**Root Cause:** Dhan `OrdersAdapter.place_order()` signature predates the ABC freezing.  
**Regression Risk: HIGH** — Any caller relying on positional arguments will break when Dhan gateway is updated to match ABC.

### 7.6 Inconsistent error return types (P2)

**File:** `brokers/upstox/gateway.py` line 144, `brokers/dhan/gateway.py`  
**Issue:** Upstox `get_trade_book()` raises `NotImplementedError`. Dhan's `get_trade_book()` returns `list[Trade]`. Paper's returns `list[Trade]`. This inconsistency makes `IntelligentGateway.trades()` unreliable — it calls Dhan first and if Dhan is unavailable, falls back to Upstox which raises.  
**Recommended Fix:** Return `[]` instead of raising `NotImplementedError`.

---

## 8. Maintainability

### 8.1 UpstoxBrokerGateway is 713 lines (P1)

**File:** `brokers/upstox/gateway.py`  
**Issue:** The file should be a thin facade. It must be split into at minimum:
- `gateway.py` — only ABC methods (~300 lines)
- `gateway_extended.py` — new Upstox-specific methods (`ipo`, `payments`, etc.)  
Currently no developer can quickly scan the gateway to see what the ABC requires vs what is Upstox-specific.

### 8.2 Inline `import` statements (P1)

**Files:** `brokers/upstox/gateway.py` lines 124, 192-194, 265, 434, 476, 511, 612, 664; `brokers/dhan/gateway.py` lines 516, etc.  
**Issue:** Multiple inline `import` statements inside methods. This:
1. Adds repeated lookup overhead on every call
2. Makes dependency tracking harder
3. Masks circular import problems that should be resolved structurally  
**Root Cause:** Circular deps or deferred loading.  
**Accepted in some cases:** The `DepthLevel` import in `depth()` is inside the method to avoid circular imports with `brokers.common.core.domain`. This is a legitimate pattern.

### 8.3 Inconsistent docstring quality (P3)

- Dhan gateway methods have Args/Raises docstrings
- Upstox gateway methods have Args docstrings for some but not others
- `place_order` in Upstox gateway has no docstring

### 8.4 Magic string comparisons (P2)

**File:** `brokers/upstox/mapper/domain_mapper.py` lines 62-66, 48-52, etc.  
**Issue:** `_WIRE_TO_PRODUCT = {v: k for k, v in _PRODUCT_TO_WIRE.items() if v not in ("D",)}` silently drops "D" (CNC/DELIVERY). If Upstox adds a new product type code, this mapping silently ignores it. The comment explains *why* but there's no assertion or fallback.

### 8.5 No `__slots__` on Upstox domain classes (P3)

**File:** `brokers/upstox/market_data/` adapters  
**Issue:** Adapter classes don't use `__slots__`. With 50+ adapter instances per broker connection, memory overhead is low but nonzero. Not a production blocker.

### 8.6 Inconsistent exception handling philosophy (P2)

**Dhan:** Structured exception hierarchy (`DhanError`, `AuthenticationError`, `RateLimitError`) in `brokers/dhan/exceptions.py`  
**Upstox:** Generic `UpstoxApiError`, `UpstoxAuthError` in `brokers/upstox/auth/exceptions.py`  
**No common:** `brokers/common/exceptions.py` does not exist. A single `BrokerError` hierarchy would allow `IntelligentGateway` and CLI services to handle errors uniformly.

---

## 9. Security Findings Summary

| ID | Severity | File | Issue |
|---|---|---|---|
| SEC-01 | P0 | `brokers/upstox/instruments/loader.py:103` | `pickle.load` → arbitrary code execution |
| SEC-02 | P1 | `brokers/dhan/factory.py:323-340` | Raw JWT written to `.env.local` without file permission hardening |
| SEC-03 | P1 | `brokers/upstox/gateway.py:150-188` | No `allow_live_orders` guard on payout, MF, fundamentals methods |
| SEC-04 | P1 | `brokers/upstox/orders/order_command_adapter.py` | No minimum validation on quantity, price, instrument_key |
| SEC-05 | P2 | `brokers/dhan/http_client.py:270-274` | Token errors returned in body without masking in logger |
| SEC-06 | P3 | All HTTP clients | No TLS certificate pinning |

---

## 10. Test Coverage Gaps

| Gap | Severity | File | What's Missing |
|---|---|---|---|
| Failure-path for IPO | P1 | `brokers/upstox/ipo/` | No HTTP error, empty body, or malformed JSON tests |
| Failure-path for Payments | P1 | `brokers/upstox/payments/` | No HTTP error tests |
| Failure-path for Mutual Funds | P1 | `brokers/upstox/mutual_funds/` | No HTTP error tests |
| Failure-path for Fundamentals | P1 | `brokers/upstox/fundamentals/` | No HTTP error tests |
| Gateway method delegation | P1 | `brokers/upstox/gateway.py:150-188` | No integration test calls `gateway.get_ipos()` end-to-end |
| Async stream() crash | P1 | `brokers/upstox/gateway.py:448-465` | No test for `stream()` called inside running event loop |
| Timeout in historical_v3 | P2 | `brokers/upstox/market_data/historical_v3.py` | No test for HTTP timeout handling |
| Circuit breaker on Upstox | P2 | `brokers/upstox/http.py` | No CB integration tests |
| Token refresh race | P2 | `brokers/upstox/auth/token_manager.py` | No concurrent `bearer_token()` + refresh test |
| Backfill timeout | P2 | `brokers/upstox/websocket/market_data_v3.py` | No test for slow backfill_callback |
| Instrument pickle corruption | P0 | `brokers/upstox/instruments/loader.py` | No test for malformed pickle file |
| Dhan place_order ABC compliance | P1 | `brokers/dhan/gateway.py:112` | No test for Dhan gateway with explicit kwargs |
| IntelligentGateway routing for new caps | P2 | `brokers/common/intelligent_gateway.py` | No test for `intelligent_gateway.get_ipos()` |
| Correlation ID propagation | P2 | `brokers/common/core/domain.py` | No test verifying correlation_id flows to Trade events |

---

## 11. Prioritized Remediation Plan

### Sprint 1 (P0 — Blocking Production)

**Task 1.1:** Replace `pickle.load` with JSON deserialization in `UpstoxInstrumentLoader.load()`  
- Replace `.pkl` cache with `.json.gz` cache  
- Benchmark: current load time ~2s → target <5s (gzip + ijson streaming)  
- Add test for malformed cache recovery  
- **Owners:** Security Engineer, one backend dev  
- **Estimate:** 1 day  
- **Risk:** Cache invalidation; old `.pkl` files will be orphaned. Add migration path.

**Task 1.2:** Fix Dhan `place_order` signature to match `MarketDataGateway` ABC  
- Change `gateway.py` `place_order` to explicit named parameters  
- Update `OrdersAdapter.place_order()` call site  
- Add regression test  
- **Owners:** One backend dev  
- **Estimate:** 4 hours

**Task 1.3:** Fix Upstox `stream()` async/sync boundary  
- Replace `asyncio.get_event_loop()` / `run_until_complete()` with `asyncio.run_coroutine_threadsafe()` or accept `async` version  
- Add test for running-loop context  
- **Owners:** One backend dev  
- **Estimate:** 1 day

### Sprint 2 (P1 — Required before production)

**Task 2.1:** Extract non-ABC methods from UpstoxBrokerGateway into `UpstoxExtendedCapabilities`  
- New service class: `brokers/upstox/extended.py` with `get_ipos()`, `initiate_payout()`, etc.  
- Gateway retains only ABC methods + properties  
- Update `UpstoxBroker` to register capabilities; CLI to use `gateway.extended`  
- **Owners:** One backend dev (principal)  
- **Estimate:** 3 days

**Task 2.2:** Create `UpstoxConnection` class mirroring `DhanConnection`  
- Extract all adapter construction from `UpstoxBroker.__init__`  
- `UpstoxBroker` becomes a thin facade holding one `UpstoxConnection`  
- Update factory to construct `UpstoxConnection` first  
- **Owners:** One backend dev (principal)  
- **Estimate:** 2 days

**Task 2.3:** Implement `BrokerProviderFactory` on `UpstoxBrokerFactory`  
- Refactor `create()` signature to match ABC  
- Remove `analytics_only`, `backfill_callback` from public API (move to internal)  
- **Owners:** One backend dev  
- **Estimate:** 1 day

**Task 2.4:** Add failure-path tests for all 4 new adapters  
- Test HTTP 4xx, 5xx, timeout, malformed JSON  
- Use `FakeHttpClient` from conftest to inject failures  
- **Owners:** One QA/dev  
- **Estimate:** 1 day

**Task 2.5:** Add `correlation_id` to `Trade`, `Position`, `Holding`, `Quote`, `DomainEvent`  
- Thread from `place_order(correlation_id=...)` → order → trade event  
- Update `OrderCommandAdapter.place_order` and `UpstoxOrderClient.build_place_payload()`  
- **Owners:** One backend dev  
- **Estimate:** 2 days

**Task 2.6:** Add `allow_live_orders` guards to new adapter methods  
- `initiate_payout`, `place_mutual_fund_order`, etc. must check `settings.allow_live_orders`  
- **Owners:** One backend dev  
- **Estimate:** 4 hours

### Sprint 3 (P2 — Production hardening)

**Task 3.1:** Circuit breaker + retry for Upstox HTTP client  
- Extract retry/backoff to `brokers/common/resilience/`  
- Wire `CircuitBreaker` into `UpstoxHttpClient._request()`  
- **Owners:** SRE + one backend dev  
- **Estimate:** 2 days

**Task 3.2:** Replace `EventMetrics` stub with Prometheus backend  
- Add `PrometheusEventMetrics` in `brokers/common/observability/prometheus.py`  
- Wire into existing observability HTTP server on `/metrics`  
- **Owners:** SRE  
- **Estimate:** 2 days

**Task 3.3:** Extract hardcoded URLs, timeouts, retry counts  
- Move `COMPLETE_JSON_URL`, `_GENERATE_TOKEN_URL`, `_BASE_URL` into `UpstoxApiUrlResolver` and `DhanHttpClient.__init__` defaults  
- **Owners:** One backend dev  
- **Estimate:** 1 day

**Task 3.4:** Fix duplicate imports in `BatchFetchMixin`  
- Remove lines 20-25  
- **Owners:** N/A (trivial)  
- **Estimate:** 5 minutes

**Task 3.5:** Fix inline `import` statements to module level  
- `brokers/upstox/gateway.py`: move `logging`, `time`, `Path`, `datetime` imports to top  
- **Owners:** One backend dev  
- **Estimate:** 30 minutes

**Task 3.6:** Add instrument loader resilience test  
- Test: pickle file corrupted → falls back to JSON download  
- **Owners:** QA/dev  
- **Estimate:** 2 hours

### Sprint 4 (P3 — Technical debt)

**Task 4.1:** Standardize Dhan/Upstox `search()` limit via `BrokerCapabilities`  
**Task 4.2:** Remove dead alias `market_data_v3_adapter` from `UpstoxBroker`  
**Task 4.3:** Add `__slots__` to adapter classes with heavy instantiation  
**Task 4.4:** Unify error hierarchy into `brokers/common/exceptions.py`  
**Task 4.5:** Add WS reconnect backfill timeout guard  
**Task 4.6:** Add `trace_id` propagation to `DomainEvent`  
**Task 4.7:** Document "Upstox does not support `depth()`" → `NotImplementedError` for upstox-specific depth-only calls  
**Task 4.8:** Publish `docs/adr/ADR-006-upstox-gateway-extended-methods.md`

---

## Appendix A: Architecture Violations Matrix

| Violation | Severity | ADR | Pattern |
|---|---|---|---|
| New methods on frozen facade | P0 | ADR-002 | Leaky Abstraction |
| god constructor in `UpstoxBroker` | P1 | ADR-001 | Tight Coupling |
| `*args, **kwargs` bypassing ABC | P1 | ADR-002 | Contract Violation |
| Inconsistent Dhan vs Upstox `stream()` | P1 | — | Behavioral Inconsistency |
| Inline imports (circular dep smells) | P2 | — | Structural Debt |
| `pickle.load` of external data | P0 | — | Security |
| EventMetrics stub never replaced | P1 | — | Observability Gap |
| No correlation IDs downstream | P1 | — | Observability Gap |
| No CB/retry on Upstox | P2 | — | Resilience Gap |
| Duplicate `BatchFetchMixin` imports | P2 | — | Code Hygiene |
| Parser/interval logic duplicated | P2 | — | DRY Violation |

---

## Appendix B: Regression Risk Register

| Change | Affected Component | Risk Level | Mitigation |
|---|---|---|---|
| Replace pickle with JSON | Instrument loader | MEDIUM | Migration script; benchmark <5s init target |
| Split UpstoxBrokerGateway | CLI, OMS, IntelligentGateway | HIGH | Incremental migration: add new service, deprecate old methods |
| Create UpstoxConnection | factory, BrokerService | MEDIUM | Keep `UpstoxBroker` API stable, delegate internally |
| Fix Dhan place_order signature | Dhan gateway + all callers | HIGH | Search for all `_conn.orders.place_order` call sites; update + test |
| Add correlation_id to domain | OMS, EventBus, CLI | LOW | Additive field with default `None`; backward compatible |
| Add CB/retry to Upstox | Upstox HTTP client | LOW | Additive wrapper; existing behavior preserved |

---

## Appendix C: What the Review Did NOT Find

- No dead code in production paths
- No unused classes in `brokers/common/`
- No obvious memory leaks (thread pools are context-managed)
- No unhandled `asyncio.CancelledError` (Upstox multiplexer properly cancels tasks)
- No unvalidated SQL (no ORM; DuckDB is parameterized)
- No direct `os.system()` or `subprocess` calls
- `config/dhan-pin.txt` and `config/dhan-totp-secret.txt` are gitignored (verified)
