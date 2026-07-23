# Zero Parity Analysis: v2 vs src Broker Implementations

**Date:** 2026-07-23  
**Scope:** Complete functional and non-functional comparison of broker implementations  
**Brokers Analyzed:** Dhan, Upstox, Paper

---

## Executive Summary

The v2 broker implementation is a **ground-up rewrite** using modern Python patterns (dataclasses, Protocols, dependency injection) while src/brokers is the **production battle-tested system** with extensive features. v2 achieves ~60% functional parity but has critical gaps in production hardening, extended capabilities, and operational maturity.

**Key Findings:**
- ✅ Core order lifecycle (place/cancel/modify) — PARITY
- ✅ Basic market data (LTP/quote/depth/history) — PARITY  
- ✅ Token-based authentication — PARITY
- ✅ Rate limiting (token bucket) — PARITY
- ⚠️ Instrument management — PARTIAL (missing caching sophistication)
- ⚠️ Streaming/WebSocket — PARTIAL (missing subscription engine)
- ❌ Extended capabilities (super orders, forever orders) — MISSING
- ❌ Production hardening (metrics, observability) — MISSING
- ❌ Advanced risk management — MISSING

---

## 1. Architecture Comparison

### 1.1 Structural Pattern

**src/brokers (Production):**
```
BrokerFactory → BrokerAdapter (ABC) → Connection → Adapters
                                      ↓
                              HttpClient (requests)
                              TokenManager
                              RateLimiter
                              CircuitBreaker
                              SubscriptionEngine
```

**v2/plugins/brokers (Modern):**
```
Gateway → Connection → Adapters (Protocol-based)
           ↓
    HttpTransport (urllib)
    TokenManager
    RateLimiter
    CircuitBreaker
    WsReconnectManager
```

**Key Differences:**
- **src:** Uses `requests` library (connection pooling, session management)
- **v2:** Uses `urllib` (stdlib, no external deps)
- **src:** ABC-based inheritance (`BrokerAdapter` abstract class)
- **v2:** Protocol-based composition (structural typing)
- **src:** God-class `DhanWireAdapter` (1000+ lines)
- **v2:** Clean separation (Gateway → Connection → Adapters)

---

## 2. Instrument CSV Management

### 2.1 Download & Storage

| Aspect | src/brokers | v2/plugins/brokers | Parity |
|--------|-------------|-------------------|--------|
| **Download URL** | `Dhan.INSTRUMENT_CSV` (config-driven) | Hardcoded URL | ⚠️ |
| **Cache Location** | `data/lake/instruments/` (configurable via `DHAN_CACHE_DIR`) | `v2/runtime/` (hardcoded) | ⚠️ |
| **Cache Filename** | `instruments_YYYY-MM-DD.csv` | `dhan-instruments-YYYY-MM-DD.csv` | ✅ |
| **Cache TTL** | 6 hours | 6 hours | ✅ |
| **Cache Cleanup** | 7 days | 7 days | ✅ |
| **MCX Supplement** | ✅ Detailed API (`/v2/instrument/MCX_COMM`) | ✅ Same API | ✅ |
| **Fallback Strategy** | Stale cache on download failure | No fallback (raises exception) | ❌ |
| **Force Refresh** | `force_refresh=True` parameter | Cache age check only | ⚠️ |
| **Parsing** | `pandas.read_csv` (robust) | `csv.DictReader` (lightweight) | ⚠️ |
| **Memory Optimization** | Normalized rows → SymbolResolver | Direct Instrument objects | ⚠️ |

### 2.2 Instrument Resolution

**src/brokers:**
```python
DhanInstrumentService
  ├─ SymbolResolver (in-memory index)
  ├─ DhanIdentityProvider (symbol → security_id mapping)
  └─ BrokerWireRef (opaque wire references)
```

**v2/plugins/brokers:**
```python
DhanInstrumentAdapter
  ├─ _by_id: dict[str, Instrument] (flat lookup)
  └─ DhanWire (security_id registration)
```

**Gaps:**
- ❌ No canonical symbol resolution (src uses `SymbolResolver`)
- ❌ No identity provider pattern (src uses `DhanIdentityProvider`)
- ❌ No instrument search with fuzzy matching
- ❌ No instrument statistics/metrics
- ❌ No "is_loaded" check

### 2.3 Upstox Instruments

**src/brokers:**
- Downloads from Upstox CDN
- Caches with same 6h TTL / 7-day cleanup
- Uses `pandas` for parsing
- Integrates with `UpstoxInstrumentService`

**v2/plugins/brokers:**
- Downloads from same CDN URL
- **NO CACHING** (downloads every time)
- Uses `csv.DictReader`
- Flat in-memory dict

**Critical Gap:** v2 Upstox instruments re-download on every startup (no cache).

---

## 3. Rate Limiting

### 3.1 Configuration

**src/brokers:**
```python
DHAN_RATE_LIMITS = {
    "orders": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 130,
        "extra_windows": ((250, 60.0), (7000, 86400.0)),  # 250/min, 7000/day
    },
    "quotes": {...},
    "historical": {...},
    "options_historical": {...},  # Separate bucket for options
    "expired_historical": {...},  # Separate bucket for expired
    "admin": {...},
}
```

**v2/plugins/brokers:**
```python
DHAN_RATE_LIMITS = {
    "orders": {"sustained_rps": 10.0, "burst_rps": 20.0},
    "quotes": {"sustained_rps": 10.0, "burst_rps": 20.0},
    "historical": {"sustained_rps": 5.0, "burst_rps": 10.0},
    "admin": {"sustained_rps": 10.0, "burst_rps": 20.0},
}
```

**Gaps:**
- ❌ No `min_interval_ms` (minimum delay between requests)
- ❌ No `cooldown_on_429_s` (backoff after 429)
- ❌ No `extra_windows` (rolling window limits like 250/min, 7000/day)
- ❌ No separate buckets for `options_historical`, `expired_historical`
- ❌ No `PAPER_RATE_LIMITS` (paper broker uses same limits)

### 3.2 Implementation

**src/brokers:**
```python
MultiBucketRateLimiter (infrastructure.resilience.rate_limiter)
  ├─ Token bucket per category
  ├─ Rolling window enforcement
  ├─ Metrics (DhanRateLimiterMetrics)
  └─ Adaptive backoff on 429
```

**v2/plugins/brokers:**
```python
MultiBucketRateLimiter (plugins.brokers.common.rate_limit)
  ├─ Token bucket per category
  ├─ Rate reduction on 429 (RATE_REDUCTION_FACTOR)
  └─ No metrics
```

**Gaps:**
- ❌ No rolling window enforcement (only token bucket)
- ❌ No metrics/observability
- ❌ Rate reduction is simplistic (src uses adaptive backoff)

### 3.3 Rate Limit Flow

**src/brokers:**
```
Request → CircuitBreaker check → RateLimiter.acquire() → HTTP → 429? → Adaptive backoff → Retry
                                        ↓
                              ResilientHttpTransport
                              (unified rate-limit + retry hooks)
```

**v2/plugins/brokers:**
```
Request → RateLimiter.acquire() → HTTP → 429? → Rate reduction → Retry
                                        ↓
                              HttpTransport
                              (rate-limit + retry + circuit-breaker)
```

**Parity:** ✅ Core flow is same, but src has more sophisticated backoff.

---

## 4. Authentication & Token Management

### 4.1 Token Lifecycle

**src/brokers:**
```python
AuthManager
  ├─ TokenPersistence (JSON file store)
  ├─ TokenRefreshScheduler (background thread)
  ├─ TotpRefreshScheduler (daily TOTP refresh)
  ├─ TotpCooldownGuard (prevent TOTP hammering)
  └─ Token broadcast (notify receivers on refresh)
```

**v2/plugins/brokers:**
```python
DhanTokenManager
  ├─ DhanTokenStore (JSON file store)
  ├─ DhanTotpClient (TOTP generation)
  ├─ TotpCooldownGuard (prevent TOTP hammering)
  ├─ JwtExpiry (parse JWT expiry)
  └─ TokenBroadcast (notify receivers on refresh)
```

**Parity:** ✅ Core token management is equivalent.

### 4.2 Token Refresh Strategy

**src/brokers:**
- **Proactive refresh:** Background scheduler checks every N seconds
- **Reactive refresh:** On HTTP 401/DH-906
- **TOTP refresh:** Daily at configured hour (e.g., 8:55 AM)
- **Cooldown:** 120s between TOTP attempts
- **Backoff:** Exponential on rate limit (120s → 240s → 480s → max 600s)

**v2/plugins/brokers:**
- **Proactive refresh:** On `ensure_token()` call (checks JWT expiry buffer)
- **Reactive refresh:** On HTTP 401/403 (via `on_auth_failure` callback)
- **TOTP refresh:** On-demand (no scheduler)
- **Cooldown:** 120s between TOTP attempts
- **Backoff:** No exponential backoff

**Gaps:**
- ❌ No background token refresh scheduler
- ❌ No daily TOTP refresh scheduler
- ❌ No exponential backoff on TOTP rate limit

### 4.3 Token Storage

**src/brokers:**
```python
JsonTokenStateStore
  ├─ access_token
  ├─ expires_at
  ├─ expires_at_ms
  ├─ source (TOTP/env/store)
  └─ client_id
```

**v2/plugins/brokers:**
```python
DhanTokenStore
  ├─ access_token
  ├─ expires_at
  ├─ expires_at_ms
  └─ source (TOTP)
```

**Parity:** ✅ Equivalent.

### 4.4 Auth Flow

**src/brokers:**
```
authenticate() → AuthManager.acquire() → TOTP → TokenPersistence.save()
                                           ↓
                                    TokenRefreshScheduler.start()
                                    TotpRefreshScheduler.start()
```

**v2/plugins/brokers:**
```
authenticate() → DhanTokenManager.ensure_token() → TOTP → DhanTokenStore.save()
                                                        ↓
                                                 TokenBroadcast.broadcast()
```

**Parity:** ✅ Core flow is same.

---

## 5. Order Management

### 5.1 Order Placement

**src/brokers:**
```python
OrdersAdapter
  ├─ OrderValidator (pre-trade validation)
  ├─ OrderPlacer (placement, slicing, idempotency)
  ├─ IdempotencyCache (prevent duplicate orders)
  ├─ RiskManagerPort (pre-trade risk checks)
  └─ EventBus (order lifecycle events)
```

**v2/plugins/brokers:**
```python
DhanOrdersAdapter
  ├─ _cache: dict[str, Order] (in-memory cache)
  └─ Direct transport call
```

**Gaps:**
- ❌ No pre-trade validation
- ❌ No order slicing (large orders split into smaller chunks)
- ❌ No idempotency cache
- ❌ No risk manager integration
- ❌ No event bus integration
- ❌ No correlation ID tracking

### 5.2 Order Modification

**src/brokers:**
```python
modify_order(order_id, **changes)
  ├─ Fetch existing order
  ├─ Validate changes (OrderValidator)
  ├─ Apply changes
  └─ Transport.modify_order()
```

**v2/plugins/brokers:**
```python
modify_order(order_id, command)
  └─ Transport.post(/orders/{order_id}, json=body)
```

**Gaps:**
- ❌ No validation before modification
- ❌ No existing order fetch

### 5.3 Order Cancellation

**src/brokers:**
```python
OrdersAdapter
  ├─ cancel_order(order_id) → OrderCanceller
  ├─ cancel_all_orders() → Batch cancellation
  ├─ kill_switch(enable) → Emergency stop
  └─ status_kill_switch() → Check status
```

**v2/plugins/brokers:**
```python
DhanOrdersAdapter
  ├─ cancel_order(order_id) → Transport.post(/orders/{order_id}/cancel)
  └─ No cancel_all, no kill_switch
```

**Gaps:**
- ❌ No `cancel_all_orders()`
- ❌ No `kill_switch()` (emergency stop)
- ❌ No `status_kill_switch()`

### 5.4 Order Query

**src/brokers:**
```python
OrdersAdapter
  ├─ get_order(order_id)
  ├─ get_order_by_correlation_id(correlation_id)
  ├─ get_orderbook()
  ├─ get_trade_book()
  └─ Parse timestamps (ISO-8601 + DD/MM/YYYY)
```

**v2/plugins/brokers:**
```python
DhanOrdersAdapter
  ├─ get_order(order_id) → Cache-first lookup
  └─ get_orderbook()
```

**Gaps:**
- ❌ No `get_order_by_correlation_id()`
- ❌ No `get_trade_book()`
- ❌ No timestamp parsing

---

## 6. Market Data

### 6.1 LTP / Quote / Depth

**src/brokers:**
```python
MarketDataCapability
  ├─ ltp(symbol, exchange) → Decimal
  ├─ quote(symbol, exchange) → Quote
  ├─ depth(symbol, exchange) → MarketDepth
  ├─ depth_20(symbol, exchange) → MarketDepth (WebSocket)
  ├─ depth_200(symbol, exchange) → MarketDepth (WebSocket)
  ├─ ltp_batch(symbols, exchange) → dict (native batch API)
  ├─ quote_batch(symbols, exchange) → dict (native batch API)
  └─ ohlc(symbol, exchange) → OHLC
```

**v2/plugins/brokers:**
```python
DhanMarketDataAdapter
  ├─ get_ltp(instrument_id) → Price
  ├─ get_quote(instrument_id) → Quote
  ├─ get_depth(instrument_id) → MarketDepth
  └─ get_history(instrument_id, timeframe, start, end) → list[Bar]
```

**Gaps:**
- ❌ No `depth_20()` / `depth_200()` (WebSocket-based depth)
- ❌ No `ltp_batch()` / `quote_batch()` (native batch APIs)
- ❌ No `ohlc()` method
- ❌ Uses `InstrumentId` instead of `(symbol, exchange)` tuple

### 6.2 Historical Data

**src/brokers:**
```python
HistoricalDataCapability
  ├─ history(symbol, exchange, timeframe, lookback_days) → DataFrame
  ├─ history_batch(symbols, ...) → DataFrame (parallel fetch)
  ├─ options_history(symbol, exchange, ...) → DataFrame
  └─ expired_history(symbol, exchange, ...) → DataFrame
```

**v2/plugins/brokers:**
```python
DhanMarketDataAdapter
  └─ get_history(instrument_id, timeframe, start, end) → list[Bar]
```

**Gaps:**
- ❌ No `history_batch()` (parallel fetch)
- ❌ No `options_history()`
- ❌ No `expired_history()`
- ❌ Returns `list[Bar]` instead of `DataFrame`
- ❌ Uses `(start, end)` instead of `lookback_days`

---

## 7. Streaming / WebSocket

### 7.1 Market Streaming

**src/brokers:**
```python
SubscriptionEngine
  ├─ subscribe_market(symbol, exchange, mode, on_tick) → Feed
  ├─ unsubscribe_market(symbol, exchange, on_tick)
  ├─ subscribe_instruments(keys, modes, on_tick) → Batch
  ├─ unsubscribe_instruments(keys, on_tick)
  ├─ Instrument ref-counting
  ├─ Callback deduplication
  ├─ Mode switching (LTP/Quote/Depth)
  └─ Metrics
```

**v2/plugins/brokers:**
```python
DhanStreamingAdapter
  ├─ stream(instrument_id, on_quote)
  ├─ unstream(instrument_id)
  ├─ feed_raw(payload) → Test hook
  └─ WsReconnectManager (auto-reconnect)
```

**Gaps:**
- ❌ No subscription engine (ref-counting, deduplication)
- ❌ No batch subscribe
- ❌ No mode switching (LTP/Quote/Depth)
- ❌ No metrics
- ❌ Uses `InstrumentId` instead of `(symbol, exchange)`

### 7.2 Order Streaming

**src/brokers:**
```python
SubscriptionEngine
  ├─ subscribe_order(on_order) → Stream
  ├─ unsubscribe_order(on_order)
  ├─ Callback deduplication
  └─ Wrapper functions (raw dict → Order entity)
```

**v2/plugins/brokers:**
```python
DhanStreamingAdapter
  ├─ stream_order(on_order)
  └─ No unsubscribe
```

**Gaps:**
- ❌ No `unstream_order()`
- ❌ No callback deduplication

### 7.3 WebSocket Reconnect

**src/brokers:**
```python
ReconnectingService
  ├─ Auto-reconnect on disconnect
  ├─ Exponential backoff
  ├─ Subscription replay
  ├─ Token refresh on reconnect
  └─ Health monitoring
```

**v2/plugins/brokers:**
```python
WsReconnectManager
  ├─ Auto-reconnect on disconnect
  ├─ Exponential backoff
  └─ Subscription replay
```

**Parity:** ✅ Core reconnect logic is equivalent.

---

## 8. Extended Capabilities

### 8.1 Dhan Super Orders

**src/brokers:**
```python
DhanExtendedCapabilities
  ├─ SuperOrder
  │   ├─ place_super_order() (bracket/cover)
  │   ├─ cancel_super_order()
  │   └─ modify_super_order()
  ├─ ForeverOrder
  │   ├─ place_forever_order()
  │   ├─ cancel_forever_order()
  │   └─ modify_forever_order()
  ├─ ConditionalTriggers
  │   └─ place_conditional_order()
  ├─ PnlExit
  │   └─ exit_position_pnl()
  └─ ExitAll
      └─ exit_all_positions()
```

**v2/plugins/brokers:**
```python
BrokerExtensions
  └─ Empty (no extended capabilities)
```

**Gaps:**
- ❌ No super orders (bracket/cover)
- ❌ No forever orders
- ❌ No conditional triggers
- ❌ No PnL exit
- ❌ No exit-all

### 8.2 Dhan Specialized Features

**src/brokers:**
```python
DhanExtendedCapabilities
  ├─ EDIS (Electronic Delivery Instruction Slip)
  ├─ IP Management (whitelist IPs)
  ├─ UserProfile (fetch user details)
  ├─ OptionChain (fetch option chain)
  ├─ Futures (fetch futures data)
  └─ Margin (fetch margin requirements)
```

**v2/plugins/brokers:**
```python
BrokerExtensions
  └─ Empty
```

**Gaps:**
- ❌ No EDIS
- ❌ No IP management
- ❌ No user profile
- ❌ No option chain
- ❌ No futures data
- ❌ No margin calculator

### 8.3 Upstox Extended

**src/brokers:**
```python
UpstoxExtendedCapabilities
  ├─ IPO (apply for IPO)
  ├─ Fundamentals (PE ratio, market cap)
  ├─ News (company news feed)
  └─ KillSwitch (emergency stop)
```

**v2/plugins/brokers:**
```python
BrokerExtensions
  └─ Empty
```

**Gaps:**
- ❌ No IPO
- ❌ No fundamentals
- ❌ No news
- ❌ No kill switch

---

## 9. Production Hardening

### 9.1 Observability

**src/brokers:**
```python
Metrics
  ├─ dhan_request_total (Prometheus counter)
  ├─ dhan_request_duration_seconds (Prometheus histogram)
  ├─ dhan_errors_total (Prometheus counter)
  ├─ DhanRateLimiterMetrics (rate limiter stats)
  ├─ AuthMetrics (token refresh stats)
  └─ Health checks (register_broker_health_check)
```

**v2/plugins/brokers:**
```python
No metrics
```

**Gaps:**
- ❌ No Prometheus metrics
- ❌ No rate limiter metrics
- ❌ No auth metrics
- ❌ No health checks

### 9.2 Circuit Breaker

**src/brokers:**
```python
CircuitBreaker (per category)
  ├─ Read circuit breaker (market data)
  ├─ Write circuit breaker (orders)
  ├─ Admin circuit breaker (account)
  ├─ Isolated failures (read failure doesn't block orders)
  └─ Metrics (state, failure_count, last_failure_time)
```

**v2/plugins/brokers:**
```python
CircuitBreakerHttpClient (single)
  ├─ Single circuit breaker for all endpoints
  └─ No category isolation
```

**Gaps:**
- ❌ No category-specific circuit breakers
- ❌ Read failure can block order placement

### 9.3 Retry Logic

**src/brokers:**
```python
DhanHttpClient._request()
  ├─ Exponential backoff (500ms → 1s → 2s → 4s → max 5s)
  ├─ Retry on 429 (with Retry-After header)
  ├─ Retry on 5xx
  ├─ No retry on ambiguous writes (POST /orders)
  └─ Retry on 401 after token refresh
```

**v2/plugins/brokers:**
```python
RetryableHttpClient
  ├─ Exponential backoff (0.5s → 1s → 2s → max 10s)
  ├─ Jitter (randomized delay)
  ├─ Retry on 429, 500, 502, 503, 504
  └─ No write-safety check
```

**Gaps:**
- ❌ No Retry-After header parsing
- ❌ No write-safety check (may retry failed orders)
- ⚠️ Max delay is 10s (src is 5s)

### 9.4 Error Handling

**src/brokers:**
```python
Transport Errors
  ├─ AuthenticationError (401/DH-906)
  ├─ RateLimitError (429)
  ├─ DhanError (general API error)
  ├─ OrderResult (typed order result)
  └─ order_result_from_transport_error() (convert exceptions)
```

**v2/plugins/brokers:**
```python
Transport Errors
  ├─ AuthenticationError (401/403)
  ├─ RateLimitError (429)
  ├─ BrokerError (4xx)
  ├─ NetworkError (5xx)
  └─ No typed order result
```

**Gaps:**
- ❌ No `OrderResult` type
- ❌ No `order_result_from_transport_error()` helper

---

## 10. Non-Functional Comparison

### 10.1 Dependencies

| Aspect | src/brokers | v2/plugins/brokers |
|--------|-------------|-------------------|
| HTTP Client | `requests` (external) | `urllib` (stdlib) |
| CSV Parsing | `pandas` (external) | `csv` (stdlib) |
| WebSocket | `websockets` (external) | Injectable (test-friendly) |
| Total External Deps | 5+ | 1 (websockets) |

**v2 Advantage:** Minimal dependencies (easier to deploy, smaller footprint).

### 10.2 Testability

**src/brokers:**
- Hard to mock (tightly coupled to `requests`, `pandas`)
- Integration tests require real HTTP
- Some unit tests with mocks

**v2/plugins/brokers:**
- Highly testable (dependency injection)
- `BaseTransport` Protocol (easy to mock)
- `ws_factory` injectable (test WebSocket without real connection)
- Comprehensive unit tests

**v2 Advantage:** Better testability.

### 10.3 Code Organization

**src/brokers:**
- 307 files
- God-classes (DhanWireAdapter: 1000+ lines)
- Mixed concerns (auth + order + market data in one class)
- Extensive use of mixins

**v2/plugins/brokers:**
- 53 files
- Clean separation (Gateway → Connection → Adapters)
- Single responsibility (each adapter has one job)
- No mixins

**v2 Advantage:** Better code organization.

### 10.4 Performance

**src/brokers:**
- `requests.Session` (connection pooling)
- `pandas` (optimized CSV parsing)
- Batch APIs (native batch LTP/quote)
- Parallel historical fetch (`history_batch`)

**v2/plugins/brokers:**
- `urllib` (no connection pooling)
- `csv.DictReader` (slower than pandas)
- No batch APIs
- No parallel fetch

**src Advantage:** Better performance.

---

## 11. Summary of Gaps

### Critical Gaps (Production Blockers)

1. **❌ No extended capabilities** (super orders, forever orders, kill switch)
2. **❌ No production metrics** (Prometheus, health checks)
3. **❌ No category-specific circuit breakers** (read failure can block orders)
4. **❌ No Upstox instrument caching** (re-downloads on every startup)
5. **❌ No batch market data APIs** (ltp_batch, quote_batch)
6. **❌ No WebSocket depth** (depth_20, depth_200)

### Major Gaps (Feature Parity)

7. **❌ No order slicing** (large orders not split)
8. **❌ No idempotency cache** (duplicate order risk)
9. **❌ No pre-trade validation** (invalid orders sent to broker)
10. **❌ No risk manager integration** (no capital checks)
11. **❌ No event bus integration** (no order lifecycle events)
12. **❌ No correlation ID tracking** (can't trace order end-to-end)
13. **❌ No cancel_all_orders()** (can't batch cancel)
14. **❌ No kill_switch()** (no emergency stop)
15. **❌ No trade book** (can't fetch filled trades)

### Minor Gaps (Polish)

16. **⚠️ No background token refresh scheduler**
17. **⚠️ No daily TOTP refresh scheduler**
18. **⚠️ No exponential backoff on TOTP rate limit**
19. **⚠️ No Retry-After header parsing**
20. **⚠️ No write-safety check** (may retry failed orders)
21. **⚠️ No instrument search with fuzzy matching**
22. **⚠️ No instrument statistics**
23. **⚠️ No options_historical bucket** (separate rate limit)
24. **⚠️ No expired_historical bucket** (separate rate limit)
25. **⚠️ No rolling window rate limits** (250/min, 7000/day)

---

## 12. Recommendations

### Phase 1: Critical Fixes (Week 1-2)

1. **Add Upstox instrument caching** (same pattern as Dhan)
2. **Implement kill_switch()** (emergency stop)
3. **Add category-specific circuit breakers** (read/write/admin)
4. **Implement cancel_all_orders()** (batch cancel)
5. **Add Prometheus metrics** (request count, duration, errors)

### Phase 2: Feature Parity (Week 3-4)

6. **Implement super orders** (bracket/cover)
7. **Add batch market data APIs** (ltp_batch, quote_batch)
8. **Implement WebSocket depth** (depth_20, depth_200)
9. **Add order slicing** (split large orders)
10. **Implement idempotency cache** (prevent duplicates)

### Phase 3: Production Hardening (Week 5-6)

11. **Add pre-trade validation** (OrderValidator)
12. **Integrate risk manager** (capital checks)
13. **Add event bus integration** (order lifecycle events)
14. **Implement correlation ID tracking** (end-to-end trace)
15. **Add background token refresh scheduler**

### Phase 4: Extended Capabilities (Week 7-8)

16. **Implement forever orders** (Dhan)
17. **Add conditional triggers** (Dhan)
18. **Implement PnL exit** (Dhan)
19. **Add exit-all** (Dhan)
20. **Implement IPO** (Upstox)
21. **Add fundamentals** (Upstox)
22. **Implement news feed** (Upstox)

---

## 13. Conclusion

The v2 broker implementation is a **solid foundation** with clean architecture and excellent testability, but it lacks the **production hardening** and **extended capabilities** that make src/brokers battle-tested.

**v2 Strengths:**
- ✅ Clean architecture (Gateway → Connection → Adapters)
- ✅ Minimal dependencies (stdlib-only)
- ✅ Excellent testability (dependency injection)
- ✅ Protocol-based composition (structural typing)

**v2 Weaknesses:**
- ❌ No production metrics
- ❌ No extended capabilities
- ❌ No batch APIs
- ❌ No instrument caching (Upstox)
- ❌ No order slicing/idempotency

**Recommendation:** Use v2 for **new development** but backport critical production features from src before go-live. Prioritize Phase 1 (critical fixes) and Phase 2 (feature parity) before production deployment.

---

**Analysis Complete:** 2026-07-23  
**Analyst:** Zero Parity Analysis  
**Status:** ✅ Comprehensive
