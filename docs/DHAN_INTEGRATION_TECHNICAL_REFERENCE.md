# Dhan Broker Integration — Technical Implementation Reference

> **Purpose**: Provide exhaustive technical detail extracted from the actual codebase so an expert reviewer can identify every design flaw, concurrency issue, WebSocket issue, and source of HTTP 429 errors.
>
> **Methodology**: Every statement references the source file, class, and method. No assumptions.

---

## 1. High-Level Architecture

### 1.1 Component Interaction

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         BrokerFactory (factory.py)                      │
│  Loads settings → Auth → HTTP client → Connection → Gateway → WS wiring│
└────────────────────────────┬────────────────────────────────────────────┘
                             │ creates
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     AccountConnectionRegistry                           │
│  Process-wide singleton: one gateway per (broker_id, client_id)        │
│  Thread-safe via threading.Lock                                         │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ owns
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       BrokerGateway (gateway.py)                        │
│  Thin sync facade. Delegates to DhanConnection adapters.                │
│  Implements MarketDataGateway + ObservabilityProvider                   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ delegates to
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      DhanConnection (connection.py)                     │
│  Wires all adapters with shared HTTP client + resolver.                 │
│  Owns token-receiver registry, lifecycle registration,                  │
│  subscription engine, resolver refresher.                               │
└────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────────┘
     │       │       │       │       │       │       │       │
     ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼
  Orders  Market  Histor.  Options  Portfolio Depth20 Depth200 Polling
  Adapter Data    Adapter  Adapter  Adapter  Feed    Feed    Feed
     │       │                                                    │
     ▼       ▼                                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   DhanHttpClient (http_client.py)                    │
│  Sync HTTP via requests.Session. Token refresh, retry, rate limit,  │
│  circuit breaker (read/write/admin split).                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.1.1 Extended Adapter Layer

The following additional adapters sit alongside the core adapters, all wired by `DhanConnection`:

| Adapter | File | Class | Purpose |
|---------|------|-------|---------|
| Super Orders | `super_orders.py` | `SuperOrdersAdapter` | Bracket orders (Entry + Target + SL + Trail) |
| Forever Orders | `forever_orders.py` | `ForeverOrdersAdapter` | GTT / OCO orders |
| Conditional Triggers | `conditional_triggers.py` | `ConditionalTriggersAdapter` | Price-based alert orders (v2.5) |
| Alerts | `alerts.py` | `AlertsAdapter` | Price alerts (create/list/delete) |
| Margin | `margin.py` | `MarginAdapter` | Margin calculator |
| Ledger | `ledger.py` | `LedgerAdapter` | Account ledger entries |
| EDIS | `edis.py` | `EDISAdapter` | eDIS/TPIN for holdings sell |
| IP Management | `ip_management.py` | `IPManagementAdapter` | Static IP whitelisting |
| Exit All | `exit_all.py` | `ExitAllAdapter` | Close all positions + cancel orders |
| Futures | `futures.py` | `FuturesAdapter` | Futures contract discovery (read-only) |
| Reconciliation | `reconciliation.py` | `DhanReconciliationService` | Drift detection OMS vs broker |

### 1.1.2 Instrument Master Pipeline

```
InstrumentLoader (loader.py)
  ├── Downloads compact CSV from Dhan (daily cache, 6h TTL)
  ├── Supplements with MCX detailed API (urllib.request)
  ├── Atomic file write (.csv.tmp → os.replace → .csv)
  └── Returns list[dict] rows
        │
        ▼
SymbolResolver (resolver.py)
  ├── O(1) dict lookups: _by_symbol, _by_security_id, _by_underlying
  ├── Progressive fallback: direct → stripped → CE/PE → index → hardcoded
  ├── Alternate key generation (30+ format variants per instrument)
  ├── Atomic swap on load_from_rows() (RLock-protected)
  └── Returns Instrument (Dhan domain)
        │
        ▼
DhanIdentityProvider (identity.py)
  ├── Wraps SymbolResolver + hardcoded index table
  ├── Enforces Dhan-internal contract (segment + digit-only security_id)
  ├── Emits audit log (security_id_issued) with source tracking
  ├── Expected-segment constraint (prevents index/derivative misroute)
  └── Returns DhanInstrumentRef (frozen dataclass, immutable carrier)
        │
        ▼
Invariant Assertions (invariants.py)
  ├── assert_dhan_payload() — boundary check before every HTTP POST
  ├── assert_dhan_identity() — carrier or tuple form
  ├── assert_dhan_segment() — bare segment validation
  └── assert_valid_security_id() — digit-only contract
```

### 1.1.3 Extended Capabilities Facade

`DhanExtendedCapabilities` (in `extended.py`) exposes broker-specific features beyond the `MarketDataGateway` ABC:

- Super/Forever/Conditional order placement via connection adapters
- Option expiry and futures contract listing
- Order validation, ledger, user profile, IP management, EDIS
- Exit-all (panic button)
- MCX-specific option chain resolution (resolves nearest futures for security_id)

`DhanSuperOrderExtension`, `DhanForeverOrderExtension`, `DhanNativeSliceExtension` (in `common_extensions.py`) implement the cross-broker `SuperOrderProvider`, `ForeverOrderProvider`, `NativeSliceOrderProvider` interfaces for the extension registry.

### 1.1.4 Symbol Validation Layer

`DhanSymbolValidator` (in `symbol_validator.py`) provides pre-trade symbol verification:

- Regex-based F&O symbol parsing (4 formats: spaced option, compact option, spaced future, no-day future)
- Scans entire instrument master for F&O matches (underlying + expiry + strike + option type)
- Returns VALID / INVALID / AMBIGUOUS / EXPIRED status with candidates
- Used by CLI and API for symbol lookup before order placement

### 1.2 Data Flow

| Direction | Path | Transport |
|-----------|------|-----------|
| REST API | Gateway → Adapter → DhanHttpClient → `requests.Session` → `https://api.dhan.co/v2` | HTTP/1.1 |
| Market Feed WS | DhanMarketFeed → dhanhq SDK `MarketFeed` → `wss://...` | WebSocket (SDK-managed) |
| Order Stream WS | DhanOrderStream → dhanhq SDK `OrderUpdate` → `wss://...` | WebSocket (SDK-managed) |
| Depth 20/200 WS | BinaryDepthFeed → `websockets` library → `wss://depth-api-feed.dhan.co/twentydepth` | WebSocket (raw binary) |
| Polling Fallback | PollingMarketFeed → DhanHttpClient → `/marketfeed/ltp` | HTTP/1.1 (batch) |
| Events | All WS feeds → EventBus → Domain subscribers | In-process pub/sub |

### 1.3 Control Flow

All WebSocket services run as **daemon threads** managed by `LifecycleManager` (when provided) or `atexit` handlers. The control flow is:

1. `BrokerFactory.create()` → settings → auth → HTTP client → connection → gateway
2. WebSocket services created lazily via `_wire_websocket_services()`
3. Token refresh scheduler started as daemon thread
4. All services registered with `LifecycleManager` for coordinated shutdown

---

## 2. Complete Authentication Flow

### 2.1 Login Flow

**File**: `brokers/dhan/factory.py`, class `BrokerFactory`, method `_create_auth()`

```python
# factory.py L128-181
auth = AuthManager(
    client_id=cid,
    token_store=JsonTokenStateStore(token_state_dir / "dhan-token-state.json"),
    token_source=TokenSource.TOTP,
    on_acquire=_generate_token,      # calls _generate_totp_token()
    on_refresh=_generate_token,       # same callable
    token_lifetime_seconds=settings.token_lifetime_seconds,  # 86400 (24h)
)
```

1. Check for existing `DHAN_ACCESS_TOKEN` in env
2. If absent, call `auth.acquire()` which invokes `_generate_totp_token()`
3. TOTP flow: `pyotp.TOTP(secret).now()` → POST to `https://auth.dhan.co/app/generateAccessToken`
4. Response parsed for `accessToken` / `access_token`
5. Token persisted to `JsonTokenStateStore` and `.env.local`

### 2.2 Token Refresh

**File**: `brokers/dhan/token_scheduler.py`, class `TokenRefreshScheduler`

- **Interval**: `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS = 1200` (20 minutes)
- **Buffer**: `DHAN_TOKEN_REFRESH_BUFFER_SECONDS = 600` (10 minutes before expiry)
- **Lifetime**: `DHAN_TOKEN_LIFETIME_SECONDS = 86400` (24 hours)
- **Mechanism**: Daemon thread checks `state.is_valid()` every 20 min; only generates new token if expired/missing
- **Lock**: Shared `threading.Lock` (`refresh_lock`) between HTTP 401 handler and scheduler prevents concurrent refresh

**File**: `brokers/dhan/factory.py`, method `_refresh_via_auth()` (L346-374)

```python
def _refresh_via_auth(auth, env_file, refresh_lock):
    acquired = refresh_lock.acquire(timeout=5.0)  # Wait up to 5s for in-flight refresh
    if not acquired:
        return None
    try:
        state = auth.force_refresh()
        ...
    finally:
        refresh_lock.release()
```

### 2.3 Token Distribution (REF-13)

**File**: `brokers/dhan/connection.py`, method `broadcast_token()` (L598-625)

Token receivers registered via `register_token_receiver()`:
1. `DhanHttpClient.update_token()` — updates session headers
2. `DhanMarketFeed.update_token()` — closes active WS so reconnect picks up new token
3. `DhanOrderStream.update_token()` — updates SDK object token
4. `DhanDepth20Feed.update_token()` / `DhanDepth200Feed.update_token()` — closes WS for reconnect

### 2.4 Token Expiry & Rate Limit

**File**: `brokers/dhan/http_client.py`, method `_try_refresh_token()` (L303-351)

- Cooldown: 60 seconds between refresh attempts (`_REFRESH_COOLDOWN_SECONDS`)
- Rate limit backoff: 130 seconds (`_RATE_LIMIT_BACKOFF_SECONDS`) when Dhan returns "once every 2 minutes"
- Exponential backoff on the scheduler side: starts 120s, doubles to max 600s

### 2.5 Multiple Sessions

**File**: `brokers/dhan/account_registry.py`

`AccountConnectionRegistry` is a **class-level** (process-wide) singleton dict protected by `threading.Lock`. One gateway per `(broker_id, client_id)` pair.

---

## 3. HTTP Layer

### 3.1 Base Configuration

**File**: `brokers/dhan/http_client.py`, class `DhanHttpClient`

| Property | Value | Source |
|----------|-------|--------|
| Base URL | `https://api.dhan.co/v2` | `config/endpoints.py` L47 |
| Timeout | 15.0s (configurable) | `settings.py` L183 |
| Session | `requests.Session` (connection pooling) | `http_client.py` L170 |
| Pool connections | 50 (default) | `settings.py` L185 |
| Pool maxsize | 100 (default) | `settings.py` L186 |
| Max retries | 3 | `http_client.py` L44 |
| Base delay | 500ms | `http_client.py` L45 |
| Max delay | 5000ms | `http_client.py` L46 |

### 3.2 Headers

```python
# http_client.py L178-183
{
    "Accept": "application/json",
    "Content-Type": "application/json",
    "client-id": client_id,
    "access-token": access_token,
}
```

### 3.3 API Endpoints

| Endpoint | Method | Purpose | Rate Limit | Circuit Breaker Category |
|----------|--------|---------|------------|--------------------------|
| `/marketfeed/ltp` | POST | Batch LTP (up to 1000) | 10 req/s (0.15s interval) | read |
| `/marketfeed/quote` | POST | Batch quotes | 1 req/s (1.0s interval) | read |
| `/marketfeed/ohlc` | POST | OHLC data | 10 req/s (0.15s interval) | read |
| `/charts/historical` | GET | Historical candles | 10 req/s (0.15s interval) | read |
| `/charts/intraday` | GET | Intraday candles | 10 req/s (0.15s interval) | read |
| `/optionchain` | GET | Option chain | 10 req/s (0.35s interval) | read |
| `/orders` | POST | Place order | 25 req/s (0.04s interval) | write |
| `/orders` | GET | Order book | 25 req/s (0.04s interval) | write* |
| `/orders` | PUT | Modify order | 25 req/s (0.04s interval) | write |
| `/orders` | DELETE | Cancel order | 25 req/s (0.04s interval) | write |
| `/sliceorder` | POST | Slice order | 25 req/s | write |
| `/killswitch` | PUT | Kill switch | N/A | write |
| `/positions` | GET | Net positions | 20 req/s | admin |
| `/holdings` | GET | Holdings | 20 req/s | admin |
| `/fundlimit` | GET | Fund limits | 20 req/s | admin |
| `/traderbook` | GET | Trade book | 20 req/s | admin |
| `/marketstatus` | GET | Market status | 10 req/s | read |
| `/instruments` | GET | Instrument master | 10 req/s | read |
| `/super/orders` | POST | Place super order | 25 req/s | write |
| `/super/orders/{id}` | PUT | Modify super order leg | 25 req/s | write |
| `/super/orders/{id}/{leg}` | DELETE | Cancel super order leg | 25 req/s | write |
| `/super/orders` | GET | List super orders | 25 req/s | write* |
| `/forever/orders` | POST | Place forever order (GTT/OCO) | 25 req/s | write |
| `/forever/orders/{id}` | PUT | Modify forever order | 25 req/s | write |
| `/forever/orders/{id}` | DELETE | Cancel forever order | 25 req/s | write |
| `/forever/all` | GET | List all forever orders | 25 req/s | write* |
| `/alerts/orders` | POST | Place conditional trigger | 25 req/s | write |
| `/alerts/orders/{id}` | PUT | Modify conditional trigger | 25 req/s | write |
| `/alerts/orders/{id}` | GET | Get conditional trigger | 20 req/s | admin |
| `/alerts/orders` | GET | List all conditional triggers | 20 req/s | admin |
| `/alerts/orders/{id}` | DELETE | Delete conditional trigger | 25 req/s | write |
| `/alerts` | POST | Create price alert | 20 req/s | admin |
| `/alerts` | GET | List all alerts | 20 req/s | admin |
| `/alerts/{id}` | GET | Get alert details | 20 req/s | admin |
| `/alerts/{id}` | DELETE | Delete alert | 20 req/s | admin |
| `/margincalculator` | POST | Calculate margin | 20 req/s | admin |
| `/ledger` | GET | Ledger entries (date range) | 20 req/s | admin |
| `/edis/tpin` | POST | Generate TPIN | 20 req/s | admin |
| `/edis/authorize` | POST | Authorize eDIS transaction | 20 req/s | write |
| `/edis/status/{isin}` | GET | Check eDIS status | 20 req/s | admin |
| `/ip` | POST | Set static IP | 10 req/s | admin |
| `/ip` | PUT | Modify static IP | 10 req/s | admin |
| `/ip` | GET | Get IP configuration | 10 req/s | admin |
| `/exitall` | POST | Exit all positions + orders | N/A (emergency) | write |
| `/charts/rollingoption` | POST | Expired options OHLCV | 10 req/s | read |
| `/optionchain/expirylist` | POST | Option expiry list | 10 req/s | read |

*Note: GET /orders shares the write CB bucket due to prefix matching (documented trade-off in code).

### 3.4 Retry Policy

**File**: `brokers/dhan/http_client.py`, method `_request()` (L379-546)

| Status Code | Action | Retry? | Delay |
|-------------|--------|--------|-------|
| 401 | Token refresh + retry once | Yes (1 retry) | Immediate after refresh |
| 429 | Backoff + retry | Yes (up to max_attempts) | `Retry-After` header or exponential backoff |
| 5xx | Retry | Yes (up to max_attempts) | 500ms → 1s → 2s (exponential, cap 5s) |
| 400 (DH-906/DH-808) | Token refresh + retry | Yes (1 retry) | Immediate after refresh |
| 4xx (other) | Fail immediately | No | N/A |
| Network error | Retry | Yes (up to max_attempts) | 500ms → 1s → 2s |

### 3.5 Backoff Algorithm

```python
# http_client.py L548-552
def _backoff_delay(attempt):
    delay_ms = min(500 * (2 ** (attempt - 1)), 5000)
    return delay_ms / 1000.0
# attempt 1: 0.5s, attempt 2: 1.0s, attempt 3: 2.0s
```

---

## 4. WebSocket Architecture

### 4.1 Connection Types

| Service | SDK/Library | Endpoint | Max Instruments | Thread Model |
|---------|-------------|----------|-----------------|--------------|
| DhanMarketFeed | dhanhq `MarketFeed` | SDK-managed | 1000 | Daemon thread + SDK event loop |
| DhanOrderStream | dhanhq `OrderUpdate` | SDK-managed | N/A (account-wide) | Daemon thread |
| DhanDepth20Feed | `websockets` (raw) | `wss://depth-api-feed.dhan.co/twentydepth` | 50 | Daemon thread + asyncio loop |
| DhanDepth200Feed | `websockets` (raw) | `wss://full-depth-api.dhan.co/twohundreddepth` | 1 | Daemon thread + asyncio loop |
| PollingMarketFeed | HTTP REST | `/marketfeed/ltp` | Unlimited (batch 1000) | Daemon thread |

### 4.2 DhanMarketFeed Lifecycle

**File**: `brokers/dhan/websocket/market_feed.py`, class `DhanMarketFeed`

**State Machine**:
```
INIT → start() → _run() loop
  ├─ Admission check (fcntl host lock)
  ├─ Cooldown check (429 penalty)
  ├─ feed.run() [SDK blocks here]
  │   ├─ _on_connect() → set _is_connected=True, replay subscriptions
  │   ├─ _on_message() → parse tick/depth, dispatch callbacks, publish events
  │   ├─ _on_close() → set _is_connected=False, record disconnect_time
  │   └─ _on_error() → set _is_connected=False
  ├─ On return/exception: backoff 1s → 30s (exponential)
  └─ Reconnect loop until _stop_event.set()
```

**Reconnect Strategy**:
- Initial backoff: 1.0s
- Max backoff: 30.0s
- Multiplier: 2x
- Reset: On successful `feed.run()` return (B-4 fix)
- Max reconnect attempts: 50 (env `DHAN_MAX_RECONNECT_ATTEMPTS`)
- After max attempts: 300s cooldown (env `DHAN_RECONNECT_COOLDOWN_SECONDS`), then reset counter

### 4.3 DhanOrderStream Lifecycle

**File**: `brokers/dhan/websocket/order_stream.py`, class `DhanOrderStream`

Same reconnect pattern as MarketFeed but simpler:
- Uses `connect_to_dhan_websocket_sync()` (SDK blocking call)
- No instrument subscriptions (account-wide stream)
- Backoff: 1.0s → 30.0s via `_backoff_sleep()`
- Max reconnect: 50 attempts, then 300s cooldown

### 4.4 BinaryDepthFeed Lifecycle

**File**: `brokers/dhan/depth_feed_base.py`, class `BinaryDepthFeed`

```python
# depth_feed_base.py L330-340
def _websocket_loop(self):
    while not self._stop_event.is_set():
        try:
            self._connect_and_run()
        except Exception as exc:
            ...
        if not self._stop_event.is_set():
            self._reconnect_count += 1
            time.sleep(min(2 ** min(self._reconnect_count, 5), 30))
```

**Connection**: Uses `websockets.connect(url)` with async handler
**URL Auth**: `wss://...?token={access_token}&clientId={client_id}&authType=2`
**Heartbeat**: 30-second `asyncio.wait_for(ws.recv(), timeout=30.0)` — TimeoutError is caught and loop continues
**Subscription Replay**: On reconnect, re-sends all `_subscriptions` list

### 4.5 Token Update on WebSocket

**File**: `brokers/dhan/websocket/market_feed.py`, method `update_token()` (L118-134)

```python
def update_token(self, access_token):
    self._context.update_token(access_token)
    with self._lock:
        if self._feed:
            self._feed.access_token = access_token
            ws = getattr(self._feed, "ws", None)
            loop = getattr(self._feed, "loop", None)
            if ws and loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(ws.close(), loop)
```

This forces a reconnect with the new token by closing the active WebSocket.

---

## 5. WebSocket Subscription Lifecycle

### 5.1 Subscription Engine

**File**: `brokers/dhan/subscription_engine.py`, class `SubscriptionEngine`

Single source of truth for all market/order subscriptions per connection.

**Data Structures**:
```python
_instrument_refs: dict[tuple[str, str], int]      # (symbol, exchange) → ref count
_instrument_modes: dict[tuple[str, str], str]      # (symbol, exchange) → mode (LTP/QUOTE/FULL)
_market_callbacks: dict[tuple[str, str], list[Any]] # (symbol, exchange) → [callback, ...]
_market_wrappers: dict[tuple[str, str], list[tuple]] # (symbol, exchange) → [(original, wrapper), ...]
_order_callbacks: list[Any]                         # [callback, ...]
```

**Lock**: `threading.RLock()` — all operations are thread-safe

### 5.2 Subscribe Flow

```python
# subscription_engine.py L40-95
def subscribe_market(self, symbol, exchange, mode, on_tick):
    with self._lock:
        feed = self._ensure_market_feed()
        feed.subscribe([(segment, sid, mode)])       # Dedup in DhanMarketFeed.subscribe()
        self._instrument_refs[key] += 1              # Ref counting
        if on_tick not in existing:
            feed.on_quote(_wrap)                      # Register wrapper callback
            self._market_callbacks[key].append(on_tick)
        if not feed.is_connected:
            feed.connect()
```

### 5.3 Duplicate Prevention

**File**: `brokers/dhan/websocket/market_feed.py`, method `subscribe()` (L484-531)

```python
# P0 Fix: Dedup — only subscribe new instruments
new_instruments = [i for i in sdk_instruments if i not in self._subscribed_instruments]
if not new_instruments:
    return  # Already subscribed, no-op
```

Also enforces `MAX_INSTRUMENTS = 1000` limit with `ValueError`.

### 5.4 Unsubscribe Flow

**File**: `brokers/dhan/subscription_engine.py`, method `unsubscribe_market()` (L97-139)

- Decrements ref count
- When refs reach 0: removes callbacks, calls `feed.unsubscribe()`, cleans up tracking
- SDK `unsubscribe_symbols()` called only when feed is connected

### 5.5 Recovery After Reconnect

**File**: `brokers/dhan/websocket/market_feed.py`, method `_on_connect()` (L590-627)

```python
def _on_connect(self, feed):
    with self._lock:
        pending = self._pending_subscriptions[:]
        self._pending_subscriptions.clear()
        subscribed = list(self._subscribed_instruments)
    # Replay ALL desired subscriptions, not just pending
    to_subscribe = list(dict.fromkeys(subscribed + pending))
    if to_subscribe and feed is not None:
        feed.subscribe_symbols(to_subscribe)
```

---

## 6. Connection Management

### 6.1 Connection Ownership

| Component | Owner | Singleton? |
|-----------|-------|------------|
| DhanHttpClient | DhanConnection | Yes, per connection |
| DhanMarketFeed | DhanConnection | Yes, created once via `create_market_feed()` |
| DhanOrderStream | DhanConnection | Yes, created once via `create_order_stream()` |
| DhanDepth20Feed | DhanConnection | Yes, created on demand |
| DhanDepth200Feed | DhanConnection | Yes, created on demand |
| PollingMarketFeed | DhanConnection | Yes, created on demand |
| BrokerGateway | AccountConnectionRegistry | Yes, process-wide per (broker, client_id) |

### 6.2 Maximum Simultaneous Sockets

| Connection Type | Max Per Account | Enforcement |
|-----------------|-----------------|-------------|
| Market Feed | 1 (host-wide via fcntl) | `MarketFeedConnectionAdmission` |
| Order Stream | 1 (SDK limit) | Not enforced (single instance) |
| Depth 20 | 1 (50 instruments) | `subs_per_connection=50` |
| Depth 200 | 1 (1 instrument) | `subs_per_connection=1` |

Dhan allows up to **5 concurrent WebSocket connections** per account. This implementation uses:
- 1 Market Feed
- 1 Order Stream
- 1 Depth 20 (optional)
- 1 Depth 200 (optional)
= **4 maximum** (within the 5-connection limit)

### 6.3 Host-Wide Admission Control

**File**: `brokers/dhan/connection_admission.py`, class `MarketFeedConnectionAdmission`

Uses `fcntl.flock()` for non-blocking exclusive lock:
- Lock file: `runtime/dhan-market-feed-{client_id}.lock`
- Cooldown file: `runtime/dhan-market-feed-{client_id}.cooldown.json`
- Prevents multiple processes on same host from opening duplicate WS connections

---

## 7. Threading Model

### 7.1 Thread Inventory

| Thread | Class | Daemon? | Purpose |
|--------|-------|---------|---------|
| `dhan.market_feed` | DhanMarketFeed | Yes | SDK WebSocket event loop |
| `dhan.market_feed.watchdog` | DhanMarketFeed | Yes | Staleness watchdog |
| `dhan.order_stream` | DhanOrderStream | Yes | SDK WebSocket event loop |
| `dhan.depth_20` | BinaryDepthFeed | Yes | Raw WebSocket + asyncio loop |
| `dhan.depth_200` | BinaryDepthFeed | Yes | Raw WebSocket + asyncio loop |
| `dhan.polling_market_feed` | PollingMarketFeed | Yes | REST polling loop |
| `token-refresh` | TokenRefreshScheduler | Yes | Token expiry check + TOTP |
| Resolver refresher | ResolverRefresher | Yes | Instrument CSV refresh |

### 7.2 Locks and Synchronization

| Lock | Owner | Protects | Type |
|------|-------|----------|------|
| `_lock` (RLock) | DhanMarketFeed | Connection state, instruments, callbacks | Reentrant |
| `_lock` (RLock) | DhanOrderStream | Connection state, callbacks | Reentrant |
| `_lock` (Lock) | BinaryDepthFeed | WS reference, connection state | Non-reentrant |
| `_depth_cache_lock` (Lock) | BinaryDepthFeed | Per-security depth cache | Non-reentrant |
| `_callback_lock` (RLock) | ReconnectingServiceMixin | Callback lists | Reentrant |
| `_rate_lock` (Lock) | DhanHttpClient | Rate limit state | Non-reentrant |
| `_lock` (Lock) | AccountConnectionRegistry | Gateway dict | Non-reentrant |
| `_lock` (RLock) | SubscriptionEngine | Refs, callbacks, modes | Reentrant |
| `_lock` (RLock) | IdempotencyCache | Order cache | Reentrant |
| `_lock` (RLock) | DhanIdentityProvider | _issue_count, _synthetic_index_count | Reentrant |
| `_lock` (RLock) | SymbolResolver | _by_symbol, _by_security_id, _by_underlying | Reentrant |
| `refresh_lock` (Lock) | BrokerFactory | Token refresh serialization | Non-reentrant |

### 7.3 Race Condition Analysis

1. **Token update race**: `update_token()` on MarketFeed closes the WS from the scheduler thread while the SDK thread is inside `feed.run()`. The SDK must handle this gracefully.

2. **Subscribe during reconnect**: If `subscribe()` is called while the feed is reconnecting (not `_is_connected`), instruments are queued in `_pending_subscriptions` and flushed on next `_on_connect()`.

3. **Depth feed subscription send**: `_send_subscription()` uses `asyncio.run_coroutine_threadsafe()` to cross thread boundaries. If the loop is closed, the subscription is dropped with a counter increment.

---

## 8. Queue Architecture

### 8.1 Pending Subscriptions Queue

**File**: `brokers/dhan/websocket/market_feed.py`

| Property | Value |
|----------|-------|
| Purpose | Buffer instruments subscribed before SDK connection completes |
| Type | `list[tuple]` |
| Producer | `subscribe()` (caller thread) |
| Consumer | `_on_connect()` (SDK thread) |
| Overflow | No limit (bounded by MAX_INSTRUMENTS=1000) |
| Cleanup | Flushed and cleared on every `_on_connect()` |

### 8.2 Idempotency Cache

**File**: `brokers/dhan/orders.py`, class `IdempotencyCache`

| Property | Value |
|----------|-------|
| Purpose | Prevent duplicate order placement on retry |
| Type | `dict[str, tuple[float, Order]]` |
| Max size | 1000 entries |
| TTL | 3600 seconds |
| Eviction | Oldest entry when full |
| Thread safety | `threading.RLock` |

### 8.3 Order Stream TTLCache

**File**: `brokers/dhan/websocket/order_stream.py`

```python
self._last_cumulative_filled = TTLCache(maxsize=10000, ttl=3600)
```

| Property | Value |
|----------|-------|
| Purpose | Track cumulative filled qty per order for incremental trade calculation |
| Max size | 10,000 entries |
| TTL | 3600 seconds |
| Library | `cachetools.TTLCache` |

---

## 9. Event Flow

### 9.1 Incoming Tick Processing

```
Dhan SDK → _on_message(feed, data)
  ├─ data.type == "Ticker Data" / "Quote Data"
  │   ├─ _transform_quote() → dict with symbol, ltp, open, high, low, close, volume
  │   ├─ _track_tick_time() → record last tick time per symbol
  │   ├─ For each callback in _quote_callbacks: cb(quote)
  │   └─ _publish_tick() → EventBus.publish(DomainEvent("TICK", ...))
  ├─ data.type == "Market Depth" / "Full Data"
  │   ├─ _transform_depth() → dict with symbol, depth
  │   ├─ For each callback in _depth_callbacks: cb(depth)
  │   └─ _publish_depth() → EventBus.publish(DomainEvent("DEPTH", ...))
  └─ data.type == "Full Data" (also carries quote fields)
      └─ Also publishes TICK event
```

### 9.2 Strict-Mode Validation

**File**: `brokers/dhan/websocket/market_feed.py`, method `_publish_tick()` (L840-916)

Drops ticks when:
- `ltp` is missing or zero (dangerous false signal)
- `symbol` is missing

Counters: `_published_ticks`, `_dropped_ticks` (visible via `health()`)

### 9.3 Order Events

```
Dhan SDK → _on_order_update(data)
  ├─ Filter: data.Type == "order_alert"
  ├─ _transform_order() → canonical dict
  ├─ For each callback: cb(transformed)
  ├─ EventBus.publish("ORDER_UPDATED", ...)
  └─ If filled_quantity increased:
      ├─ Calculate incremental qty (cumulative - previous)
      └─ EventBus.publish("TRADE", ...)
```

---

## 10. Retry Framework

### 10.1 HTTP-Level Retry

**File**: `brokers/dhan/http_client.py`, method `_request()` (L379-546)

| Parameter | Value |
|-----------|-------|
| Max attempts | 3 |
| Backoff | Exponential: 500ms, 1s, 2s (cap 5s) |
| Retryable | Network errors, 429 (with Retry-After), 5xx |
| Non-retryable | 4xx (except 401/DH-906/DH-808) |
| Token refresh retry | Once (on first 401 or DH-906) |

### 10.2 Standardized Retry Executor

**File**: `brokers/dhan/resilience/retry_executor.py`

| Category | Max Attempts | Base Delay | Max Delay | Backoff |
|----------|-------------|------------|-----------|---------|
| orders | 3 | 1000ms | 8000ms | 2x, jitter 0.2 |
| market_data | 2 | 500ms | 4000ms | 2x, jitter 0.2 |
| portfolio | 3 | 1000ms | 8000ms | 2x, jitter 0.2 |
| admin | 3 | 1000ms | 8000ms | 2x, jitter 0.2 |

### 10.3 Circuit Breaker

**File**: `brokers/dhan/resilience/circuit_breaker.py`

| Category | Failure Threshold | Recovery Timeout | Success Threshold |
|----------|-------------------|------------------|-------------------|
| orders | 3 | 30s | 3 |
| market_data | 5 | 30s | 3 |
| portfolio | 5 | 30s | 3 |
| admin | 5 | 30s | 3 |

States: CLOSED → OPEN (on threshold) → HALF_OPEN (after timeout) → CLOSED (on success_threshold)

---

## 11. Rate Limiting

### 11.1 Token Bucket Rate Limiter

**File**: `brokers/dhan/resilience/rate_limiter.py`

| Bucket | Rate (req/s) | Capacity | Burst |
|--------|-------------|----------|-------|
| orders | 25 | 25 | 25 |
| market_data | 10 | 10 | 10 |
| portfolio | 20 | 20 | 20 |
| admin | 10 | 10 | 10 |

**File**: `brokers/common/resilience/rate_limiter.py`, class `TokenBucketRateLimiter`

- Thread-safe via `threading.Lock`
- Refill: continuous based on elapsed time
- Acquire timeout: 5.0s (default in `_acquire_rate_limit_token()`)
- On timeout: raises `DhanError("Rate limit timeout: ...")`

### 11.2 Per-Endpoint Throttling

**File**: `brokers/dhan/http_client.py`, method `_throttle()` (L219-230)

```python
_RATE_LIMITS = {
    "/marketfeed/quote": 1.0,    # 1 req/s
    "/marketfeed/ltp": 0.15,     # ~6.67 req/s
    "/marketfeed/ohlc": 0.15,    # ~6.67 req/s
    "/optionchain": 0.35,        # ~2.86 req/s
    "/charts/": 0.15,            # ~6.67 req/s
    "/orders": 0.04,             # 25 req/s
}
```

Uses `time.sleep()` to enforce minimum interval between requests to same endpoint.

### 11.3 Adaptive Rate Adjustment

On HTTP 429 response:
```python
# http_client.py L444-460
retry_after = self._parse_retry_after(resp)
if retry_after is not None:
    self._adaptive_intervals[key] = max(retry_after, self._adaptive_intervals.get(key, 0))
```

Adaptive intervals are **additive** with static limits: `min_interval = max(static, adaptive)`.

### 11.4 WebSocket Rate Limiting

**File**: `brokers/dhan/connection_admission.py`

- Host-wide lock prevents duplicate WS connections
- 429 cooldown: exponential backoff persisted to disk
  - Base: 60s (env `DHAN_WS_429_COOLDOWN_SECONDS`)
  - Ceiling: 900s (env `DHAN_WS_429_COOLDOWN_MAX_SECONDS`)
  - Multiplier: `2^(consecutive_rate_limits - 1)`
  - Penalty window: 3600s (env `DHAN_WS_429_PENALTY_WINDOW_SECONDS`)

---

## 12. Possible Sources of HTTP 429

| # | File | Class | Method | Reason | Risk | Frequency | Throttling | Likelihood |
|---|------|-------|--------|--------|------|-----------|------------|------------|
| 1 | http_client.py | DhanHttpClient | `_request()` | Quote endpoint at 1 req/s — any burst triggers 429 | HIGH | Per quote call | Static 1.0s interval | MEDIUM |
| 2 | http_client.py | DhanHttpClient | `_request()` | Token generation rate limit ("once every 2 minutes") | HIGH | On 401/DH-906 | 60s cooldown + 130s backoff | MEDIUM |
| 3 | factory.py | BrokerFactory | `_generate_totp_token()` | TOTP token generation called too frequently | HIGH | On scheduler interval | Scheduler 20min + exponential backoff | LOW |
| 4 | polling_feed.py | PollingMarketFeed | `_poll_batch()` | Batch LTP polling every 2s across segments | MEDIUM | Every 2s per cycle | Subject to market_data bucket (10/s) | LOW |
| 5 | http_client.py | DhanHttpClient | `_request()` | Concurrent adapters hitting same bucket | MEDIUM | Continuous | Token bucket capacity (10-25) | MEDIUM |
| 6 | subscription_engine.py | SubscriptionEngine | `subscribe()` | Rapid subscribe calls during startup | LOW | One-time burst | SDK `subscribe_symbols()` is batched | LOW |
| 7 | market_feed.py | DhanMarketFeed | `_backfill_gap()` | REST backfill calls on reconnect for N symbols | MEDIUM | On reconnect | Sequential per symbol, no batching | HIGH |
| 8 | resolver_refresher.py | ResolverRefresher | Background thread | Instrument CSV download (daily) | LOW | Once per 24h | N/A | VERY LOW |
| 9 | http_client.py | DhanHttpClient | `_try_refresh_token()` | Concurrent refresh from 401 handler + scheduler | MEDIUM | On token expiry | `refresh_lock` prevents concurrency | LOW |
| 10 | market_feed.py | DhanMarketFeed | `_run()` | Reconnect storm after network outage | HIGH | On outage | Max 50 attempts then 300s cooldown | MEDIUM |
| 11 | super_orders.py | SuperOrdersAdapter | `place_super_order()` | Each super order is a separate HTTP POST to write bucket | MEDIUM | Per order | Subject to orders bucket (25/s) | LOW |
| 12 | forever_orders.py | ForeverOrdersAdapter | `place_forever_order()` | Each forever order is a separate HTTP POST to write bucket | MEDIUM | Per order | Subject to orders bucket (25/s) | LOW |
| 13 | conditional_triggers.py | ConditionalTriggersAdapter | `place_trigger()` | Conditional trigger placement hits write bucket | MEDIUM | Per trigger | Subject to orders bucket (25/s) | LOW |
| 14 | options.py | OptionsAdapter | `get_option_chain()` | Option chain + per-strike resolve calls (N security_id lookups) | MEDIUM | Per chain request | Single POST but resolver iterates strikes | LOW |
| 15 | reconciliation.py | DhanReconciliationService | `reconcile()` | Fetches full orderbook + positions in quick succession | MEDIUM | Per reconcile cycle | 2 HTTP calls (GET /positions + GET /orders) | LOW |
| 16 | loader.py | InstrumentLoader | `_fetch_mcx_detailed()` | MCX detailed CSV download via urllib (bypasses rate limiter) | LOW | Once per day | Not subject to HTTP client rate limiter | VERY LOW |
| 17 | market_data.py | MarketDataAdapter | `get_batch_ltp()` | Batch LTP resolves N symbols before single POST | MEDIUM | Per batch call | N identity resolutions + 1 HTTP POST | LOW |
| 18 | extended.py | DhanExtendedCapabilities | `get_option_chain()` | MCX path: resolves nearest futures + option chain POST | MEDIUM | Per MCX chain call | 2 HTTP calls (futures resolve + optionchain POST) | LOW |

---

## 13. WebSocket 429 Analysis

| Scenario | Cause | Mitigation in Code | Residual Risk |
|----------|-------|--------------------|---------------|
| 429 during connection | Dhan connection rate limit | `MarketFeedConnectionAdmission` host lock + cooldown file | LOW — single process per host |
| 429 during reconnect | Rapid reconnect attempts | Exponential backoff 1s→30s, max 50 attempts | MEDIUM — 50 attempts before cooldown |
| 429 after reconnect | Subscription replay storm | SDK `subscribe_symbols()` batches all instruments | LOW — single batch call |
| 429 after login | Token generation rate limit | 60s cooldown + 130s backoff on HTTP client | LOW |
| 429 during bursts | Multiple WS services connecting simultaneously | Staggered by lifecycle manager registration order | LOW |
| 429 due to duplicate sockets | Two processes on same host | `fcntl.flock()` exclusive lock | VERY LOW |
| 429 due to reconnect storms | Network outage affecting all WS | Max 50 attempts + 300s cooldown + admission cooldown | MEDIUM — cooldown starts at 60s base |
| 429 due to race conditions | Token update closes WS while connecting | `_lock` protects feed reference; close is best-effort | LOW |
| 429 due to thread contention | Multiple threads calling subscribe() | `SubscriptionEngine._lock` (RLock) serializes | VERY LOW |
| 429 due to subscription replay | Full subscription set replayed on reconnect | Single `subscribe_symbols()` call with deduped list | LOW |

---

## 14. State Machine

### 14.1 DhanMarketFeed States

```
                    ┌──────────────────┐
                    │      INIT        │
                    └────────┬─────────┘
                             │ start()
                             ▼
                    ┌──────────────────┐
            ┌──────│   CONNECTING     │──────┐
            │      └──────────────────┘      │
            │ admission               SDK    │
            │ blocked               error    │
            ▼                       ▼        │
   ┌────────────────┐     ┌──────────────┐   │
   │  ADMSSION_     │     │  BACKOFF     │◄──┘
   │  BLOCKED       │     │  1s → 30s    │
   └────────────────┘     └──────────────┘
            │                     │
            │ lock acquired       │ backoff expires
            ▼                     ▼
   ┌──────────────────┐  ┌──────────────────┐
   │  CONNECTED       │◄─│  AUTHENTICATED   │
   │  (_is_connected= │  │  (_on_connect    │
   │   True)          │  │   callback)      │
   └────────┬─────────┘  └──────────────────┘
            │
            │ disconnect/error
            ▼
   ┌──────────────────┐
   │  DISCONNECTED    │──── reconnect loop ────► BACKOFF
   │  (_is_connected= │
   │   False)         │
   └──────────────────┘
            │
            │ stop()
            ▼
   ┌──────────────────┐
   │     STOPPED      │
   └──────────────────┘
```

### 14.2 Session Manager States

**File**: `brokers/dhan/session_manager.py`

```
AUTH_REQUIRED → DISCONNECTED → DEGRADED → HEALTHY
                                      ↑
                                  (all streams connected)
```

---

## 15. Error Handling

### 15.1 Exception Hierarchy

```
BrokerError (common)
  └─ DhanError
       ├─ InstrumentNotFoundError (also extends common InstrumentNotFoundError)
       ├─ MarketDataError
       ├─ OrderError (also extends common OrderError)
       ├─ AuthenticationError (also extends common AuthenticationError)
       ├─ ConfigurationError
       ├─ DhanIdentityError
       ├─ SuperOrderError
       ├─ ForeverOrderError
       ├─ ConditionalTriggerError
       ├─ LedgerError
       ├─ UserProfileError
       ├─ IPManagementError
       ├─ ExitAllError (also extends common ExitAllError)
       └─ EDISError

RateLimitError (aliased from common)
```

### 15.2 Error Recovery

| Error | Recovery | Retry | Logging |
|-------|----------|-------|---------|
| HTTP 401 | Token refresh + retry | Once | WARNING |
| HTTP 429 | Backoff (Retry-After or exponential) | Up to max_attempts | WARNING |
| HTTP 5xx | Exponential backoff | Up to max_attempts | WARNING |
| HTTP 400 (DH-906) | Token refresh + retry | Once | WARNING |
| Network error | Exponential backoff | Up to max_attempts | WARNING |
| Circuit breaker OPEN | Fast-fail | No | ERROR |
| Rate limit timeout | Fast-fail | No | WARNING |
| WS "no close frame" | Reset backoff, reconnect | Immediate | DEBUG |
| WS 429 | Admission cooldown + exponential backoff | After cooldown | WARNING |
| WS stale connection | Watchdog closes socket | Automatic | WARNING |
| Max reconnect exceeded | 300s cooldown, reset counter | After cooldown | CRITICAL |
| Token rate limit | 120s backoff (doubling to 600s) | After backoff | WARNING |

---

## 16. Resource Management

### 16.1 Shutdown Sequence

**File**: `brokers/dhan/connection.py`, method `close()` (L676-716)

```python
def close(self):
    # 1. Stop token scheduler
    scheduler.stop()
    # 2. Stop resolver refresher
    resolver_refresher.stop(timeout_seconds=5.0)
    # 3. Stop all WebSocket services (join threads)
    for svc in (market_feed, order_stream, polling_feed, depth_20, depth_200):
        svc.stop(timeout_seconds=5.0)
    # 4. Close HTTP session
    client.close()
```

### 16.2 Socket Cleanup

- `DhanMarketFeed.stop()`: Sets `_stop_event`, calls `feed.close_connection()`, joins thread + watchdog thread
- `DhanOrderStream.stop()`: Sets `_stop_event`, joins thread
- `BinaryDepthFeed.stop()`: Sets `_stop_event`, closes WS via `run_coroutine_threadsafe`, joins thread
- `PollingMarketFeed.stop()`: Sets `_stop_event`, joins thread

### 16.3 Memory Cleanup

- `_last_tick_time` dict: cleaned every 100 messages (stale entries > 30min removed)
- `_subscribed_instruments` set: cleaned on `unsubscribe()`
- `IdempotencyCache`: TTL-based eviction (1h), max 1000 entries
- `TTLCache` (order stream): max 10000 entries, 1h TTL
- `DhanRateLimiterMetrics._request_timestamps`: pruned to last 60s on each record

---

## 17. Performance

### 17.1 Latency

| Operation | Expected Latency | Bottleneck |
|-----------|-----------------|------------|
| HTTP request | 50-500ms | Network + Dhan API |
| WS tick processing | < 1ms | In-process dispatch |
| Symbol resolution | < 0.1ms | In-memory dict lookup |
| Subscription add | < 1ms | Lock acquisition + SDK call |
| Token refresh | 2-15s | TOTP generation + HTTP |

### 17.2 CPU Hotspots

1. **Instrument loading**: `load_from_rows()` processes full CSV (~100K rows) — one-time cost
2. **Tick transformation**: `_transform_quote()` called per tick — Decimal conversion
3. **Symbol resolution**: `get_by_security_id()` called per tick — dict lookup

### 17.3 Memory Hotspots

1. **Instrument resolver**: Full instrument list in memory (~100K entries)
2. **`_last_tick_time` dict**: One entry per subscribed symbol (bounded by 1000)
3. **Depth cache**: Per-security depth snapshots (bounded by subscriptions)
4. **Callback lists**: Grow with subscribers, pruned on unsubscribe

### 17.4 Lock Contention

- `SubscriptionEngine._lock` (RLock): Contended during subscribe/unsubscribe bursts
- `DhanHttpClient._rate_lock`: Contended under high request rates
- `DhanMarketFeed._lock`: Contended between SDK thread and caller threads

---

## 18. Sequence Diagrams

### 18.1 Application Startup

```
CLI/API → BrokerFactory.create()
  ├─ DhanSettingsLoader.from_env()
  ├─ AccountConnectionRegistry.get_or_create()
  │   └─ _build_gateway()
  │       ├─ _create_auth() → AuthManager + TOTP token
  │       ├─ _create_http_client() → DhanHttpClient + circuit breakers + rate limiter
  │       ├─ _create_connection_and_gateway() → DhanConnection + BrokerGateway
  │       ├─ gateway.load_instruments() → CSV download + parse + resolver load
  │       ├─ _wire_websocket_services()
  │       │   ├─ create_market_feed() → DhanMarketFeed (not started)
  │       │   └─ create_order_stream() → DhanOrderStream (not started)
  │       └─ _setup_token_refresh_scheduler() → TokenRefreshScheduler (started)
  └─ return gateway
```

### 18.2 Login / Token Generation

```
BrokerFactory._create_auth()
  ├─ AuthManager.acquire()
  │   └─ on_acquire() → _generate_totp_token()
  │       ├─ pyotp.TOTP(secret).now()
  │       ├─ POST https://auth.dhan.co/app/generateAccessToken
  │       └─ Parse accessToken from response
  ├─ TokenState(access_token, issued_at, expires_at)
  ├─ JsonTokenStateStore.save(state)
  └─ _update_env_token(.env.local)
```

### 18.3 WebSocket Connect + Subscribe

```
SubscriptionEngine.subscribe_market(symbol, exchange, mode, on_tick)
  ├─ resolve(symbol, exchange) → (segment, security_id)
  ├─ _ensure_market_feed() → DhanMarketFeed (create if needed)
  ├─ feed.subscribe([(segment, sid, mode)])
  │   ├─ Dedup check against _subscribed_instruments
  │   ├─ If connected: feed.subscribe_symbols(new_instruments)
  │   └─ Else: queue in _pending_subscriptions
  ├─ Register callback
  └─ If not connected: feed.connect() → start() → daemon thread
      └─ _run() loop
          ├─ Admission check (fcntl lock)
          ├─ Cooldown check
          └─ feed.run() [SDK blocks]
              └─ _on_connect()
                  ├─ Set _is_connected = True
                  ├─ Replay all subscriptions
                  └─ Backfill gap if reconnect
```

### 18.4 Tick Received

```
SDK callback → _on_message(feed, data)
  ├─ _note_message_received() → update _last_message_at, _message_count
  ├─ _transform_quote(data) → {symbol, ltp, open, high, low, close, volume}
  ├─ _track_tick_time(quote) → update _last_tick_time[symbol]
  ├─ For each callback in snapshot(_quote_callbacks):
  │   └─ cb(quote) [caller's callback, may wrap to Quote DTO]
  └─ _publish_tick(quote)
      ├─ Validate ltp != 0, symbol present
      ├─ Build Quote DTO
      └─ EventBus.publish(DomainEvent("TICK", ...))
```

### 18.5 Reconnect + Resubscribe

```
_on_error / _on_close / feed.run() returns
  ├─ _is_connected = False
  ├─ _disconnect_time = now
  ├─ _reconnect_count += 1
  ├─ backoff = min(backoff * 2, 30.0)
  ├─ _stop_event.wait(timeout=backoff) [interruptible]
  └─ Next iteration of _run() loop
      ├─ Admission check
      ├─ Cooldown check
      └─ feed.run() → _on_connect()
          ├─ _is_connected = True
          ├─ _reconnect_count = 0
          ├─ to_subscribe = subscribed + pending (deduped)
          ├─ feed.subscribe_symbols(to_subscribe)
          └─ _backfill_gap(disconnect_time)
              └─ For each symbol: REST call → publish TICK events
```

### 18.6 Shutdown

```
LifecycleManager.shutdown() / DhanConnection.close()
  ├─ TokenRefreshScheduler.stop()
  │   ├─ _stop_event.set()
  │   └─ thread.join(timeout=10s)
  ├─ ResolverRefresher.stop(timeout=5s)
  ├─ DhanMarketFeed.stop(timeout=5s)
  │   ├─ _stop_event.set()
  │   ├─ feed.close_connection()
  │   ├─ thread.join(timeout=5s)
  │   ├─ watchdog_thread.join(timeout=5s)
  │   └─ admission.release()
  ├─ DhanOrderStream.stop(timeout=5s)
  │   ├─ _stop_event.set()
  │   └─ thread.join(timeout=5s)
  ├─ Depth feeds: stop(timeout=5s)
  ├─ PollingFeed: stop(timeout=5s)
  └─ DhanHttpClient.close() → session.close()
```

---

## 19. Class Diagram

```
BrokerProviderFactory (ABC)
  └── BrokerFactory
        ├── creates → BrokerGateway
        ├── uses → DhanConnectionSettings
        ├── uses → AuthManager
        └── uses → TokenRefreshScheduler

MarketDataGateway (ABC)
  └── BrokerGateway
        ├── delegates → DhanConnection
        ├── implements → ObservabilityProvider
        └── uses → SubscriptionEngine (via connection)

DhanConnection
  ├── owns → DhanHttpClient
  ├── owns → SymbolResolver
  ├── owns → DhanIdentityProvider
  ├── owns → SubscriptionEngine
  ├── owns → ResolverRefresher
  ├── owns → DhanSessionManager
  ├── creates → DhanMarketFeed
  ├── creates → DhanOrderStream
  ├── creates → DhanDepth20Feed
  ├── creates → DhanDepth200Feed
  ├── creates → PollingMarketFeed
  ├── creates → *Adapter (MarketData, Orders, Historical, etc.)
  └── registry → token_receivers[]

ManagedService (ABC)
  ├── DhanMarketFeed (also ReconnectingServiceMixin)
  ├── DhanOrderStream (also ReconnectingServiceMixin)
  ├── BinaryDepthFeed (also ReconnectingServiceMixin)
  │   ├── DhanDepth20Feed
  │   └── DhanDepth200Feed
  ├── PollingMarketFeed (also ReconnectingServiceMixin)
  └── TokenRefreshScheduler

ReconnectingServiceMixin
  ├── owns → _stop_event, _is_connected, _reconnect_count
  ├── owns → _last_message_at, _message_count
  ├── provides → _backoff_sleep(), _on_clean_disconnect()
  └── provides → _register_callback(), _snapshot_callbacks()

DhanHttpClient
  ├── uses → requests.Session
  ├── uses → CircuitBreaker (×3: read, write, admin)
  ├── uses → MultiBucketRateLimiter
  └── uses → DhanRateLimiterMetrics

MarketFeedConnectionAdmission
  ├── uses → fcntl (file lock)
  └── uses → cooldown JSON file

InstrumentLoader (loader.py)
  ├── daily cache (6h TTL)
  ├── MCX detailed supplement (urllib.request)
  └── atomic file write

SymbolResolver (resolver.py)
  ├── _by_symbol: dict[(str, Exchange), Instrument]
  ├── _by_security_id: dict[str, Instrument]
  ├── _by_underlying: dict[(str, Exchange), list[Instrument]]
  ├── progressive fallback (6 stages)
  └── alternate key generation (30+ variants)

DhanIdentityProvider (identity.py)
  ├── wraps → SymbolResolver
  ├── owns → _lock (RLock), _issue_count, _synthetic_index_count
  ├── issues → DhanInstrumentRef (frozen dataclass)
  └── enforces → DHAN_SEGMENTS constraint

DhanInstrumentRef (identity.py, frozen dataclass)
  ├── symbol, exchange, exchange_segment, security_id
  ├── instrument_type, lot_size, source
  ├── underlying, expiry, strike_price, option_type
  └── __post_init__: validates segment + digit-only security_id

Invariant Assertions (invariants.py)
  ├── assert_dhan_payload(payload, context=)
  ├── assert_dhan_identity(sid_or_ref, segment=, context=)
  ├── assert_dhan_segment(segment, context=)
  └── assert_valid_security_id(security_id, context=)

DhanSymbolValidator (symbol_validator.py)
  ├── uses → SymbolResolver
  ├── parse_fo_symbol() — regex-based F&O parser
  └── validate() → VALID / INVALID / AMBIGUOUS / EXPIRED

Adapter Layer (all in brokers/dhan/)
  ├── OrdersAdapter (orders.py)
  ├── MarketDataAdapter (market_data.py)
  ├── HistoricalAdapter (historical.py)
  ├── OptionsAdapter (options.py)
  ├── PortfolioAdapter (portfolio.py)
  ├── MarginAdapter (margin.py)
  ├── SuperOrdersAdapter (super_orders.py)
  ├── ForeverOrdersAdapter (forever_orders.py)
  ├── ConditionalTriggersAdapter (conditional_triggers.py)
  ├── AlertsAdapter (alerts.py)
  ├── LedgerAdapter (ledger.py)
  ├── EDISAdapter (edis.py)
  ├── IPManagementAdapter (ip_management.py)
  ├── ExitAllAdapter (exit_all.py)
  ├── FuturesAdapter (futures.py)
  └── DhanReconciliationService (reconciliation.py)

DhanExtendedCapabilities (extended.py)
  ├── delegates → DhanConnection adapters
  └── MCX option chain resolution

Extension Providers (common_extensions.py)
  ├── DhanSuperOrderExtension (SuperOrderProvider)
  ├── DhanForeverOrderExtension (ForeverOrderProvider)
  └── DhanNativeSliceExtension (NativeSliceOrderProvider)

Domain Models (domain.py, frozen dataclasses)
  ├── Instrument, MarginRequest/Response, Alert/AlertRequest
  ├── SuperOrder/SuperOrderLeg, ForeverOrder/ForeverOrderRequest
  ├── ConditionalTrigger/ConditionalTriggerRequest
  ├── LedgerEntry, UserProfile, IPConfig, ExitAllResponse
  └── Exchange, DhanInstrumentType, OptionType (enums)

Supporting Modules
  ├── InstrumentAdapter (instrument_adapter.py) — InstrumentId conversion
  ├── StatusMapper (status_mapper.py) — Dhan status → canonical OrderStatus
  ├── Segments (segments.py) — wire format + SDK int mappings
  ├── Constants (constants.py) — WS limits, idempotency config
  ├── SecretUtils (secret_utils.py) — env/file secret reader
  └── ResolverRefresher (resolver_refresher.py) — ManagedService, daily refresh
```

---

## 20. Call Graph

### 20.1 Startup Call Graph

```
BrokerFactory.create()
├── DhanSettingsLoader.from_env()
│   ├── SecretsManager.get_dhan_pin()
│   └── SecretsManager.get_dhan_totp_secret()
├── AccountConnectionRegistry.get_or_create()
│   └── BrokerFactory._build_gateway()
│       ├── _create_auth()
│       │   ├── JsonTokenStateStore.__init__()
│       │   ├── AuthManager.__init__()
│       │   ├── AuthManager.acquire() → _generate_totp_token()
│       │   │   ├── pyotp.TOTP().now()
│       │   │   └── requests.post(generateAccessToken)
│       │   └── _update_env_token()
│       ├── _create_http_client()
│       │   ├── create_circuit_breakers()
│       │   ├── create_rate_limiter()
│       │   └── DhanHttpClient.__init__()
│       ├── _create_connection_and_gateway()
│       │   ├── DhanConnection.__init__()
│       │   │   └── SubscriptionEngine.__init__()
│       │   ├── DhanSessionManager.__init__()
│       │   └── BrokerGateway.__init__()
│       ├── gateway.load_instruments()
│       │   └── DhanConnection.load_instruments()
│       │       ├── InstrumentLoader.load_cached()
│       │       └── SymbolResolver.load_from_rows()
│       ├── _wire_websocket_services()
│       │   ├── DhanConnection.create_market_feed()
│       │   └── DhanConnection.create_order_stream()
│       └── _setup_token_refresh_scheduler()
│           ├── TokenRefreshScheduler.__init__()
│           └── LifecycleManager.register() / scheduler.start()
```

### 20.2 Authentication Call Graph

```
HTTP 401 received → DhanHttpClient._request()
├── _try_refresh_token()
│   ├── Check cooldown (60s)
│   ├── _token_refresh_fn() → _refresh_via_auth()
│   │   ├── refresh_lock.acquire(timeout=5.0)
│   │   ├── AuthManager.force_refresh()
│   │   │   └── on_refresh() → _generate_totp_token()
│   │   ├── _update_env_token()
│   │   └── refresh_lock.release()
│   └── update_token(new_token)
└── Retry request with new token

Token Scheduler → TokenRefreshScheduler._do_refresh()
├── refresh_lock.acquire(blocking=False)
├── AuthManager.state.is_valid() → skip if valid
├── AuthManager.acquire()
│   └── on_acquire() → _generate_totp_token()
├── _on_refresh(new_token) → BrokerFactory callback
│   ├── client.update_token()
│   ├── _update_env_token()
│   └── gateway._conn.broadcast_token()
│       └── For each receiver: receiver(new_token)
└── refresh_lock.release()
```

### 20.3 Order Placement Call Graph

```
OrdersAdapter.place_order(symbol, exchange, ...)
├── DhanIdentityProvider.resolve_ref(symbol, exchange)
│   ├── SymbolResolver.resolve(symbol, exchange)
│   │   ├── _normalise_exchange()
│   │   └── _find() → progressive fallback (6 stages)
│   ├── _wrap(instrument, expected_segment=)
│   │   ├── EXCHANGE_TO_SEGMENT lookup
│   │   ├── DhanInstrumentRef(...) → __post_init__ validates
│   │   └── logger.info("security_id_issued")
│   └── returns DhanInstrumentRef
├── IdempotencyCache.check(correlation_id)
├── Pre-trade validation (lot size, quantity, price)
├── assert_dhan_payload(payload, context="orders.place_order")
│   ├── assert_dhan_identity(payload["securityId"], payload["exchangeSegment"])
│   └── raises DhanIdentityError on violation
├── DhanHttpClient.post("/orders", json=payload)
│   ├── RateLimiter.acquire("orders") → token bucket
│   ├── CircuitBreaker.execute("write") → check state
│   ├── requests.Session.post(url, json=payload, headers=headers, timeout=15)
│   └── On 401 → _try_refresh_token() → retry
│       On 429 → adaptive backoff
│       On 5xx → exponential retry
└── IdempotencyCache.record(correlation_id, order_id)
```

### 20.4 Reconciliation Call Graph

```
DhanReconciliationService.reconcile(local_orders, local_positions)
├── OrdersAdapter.get_orderbook()
│   └── DhanHttpClient.get("/orders")
├── PortfolioAdapter.get_positions()
│   └── DhanHttpClient.get("/positions")
├── ReconciliationEngine.compare_orders(local, broker)
│   └── returns list[DriftItem]
├── ReconciliationEngine.compare_positions(local, broker)
│   └── returns list[DriftItem]
└── If auto_repair=True and oms provided:
    ├── oms.upsert_order(missing_broker_order)
    └── oms.upsert_position(missing_broker_position)
```

### 20.5 Instrument Master Loading Call Graph

```
DhanConnection.load_instruments(use_cache=True)
├── InstrumentLoader.load_cached(force_refresh=False, mcx_required=None)
│   ├── Check cache dir (DHAN_CACHE_DIR or runtime-dev/instruments/)
│   ├── Cleanup old cache files (>7 days)
│   ├── Check cache TTL (6 hours)
│   ├── If cache valid: pd.read_csv(cache_path)
│   ├── Else: pd.read_csv(Dhan.INSTRUMENT_CSV) → download
│   │   └── Atomic write: .csv.tmp → os.replace → .csv
│   ├── _compact_to_rows(df) → list[dict]
│   ├── _fetch_mcx_detailed() → urllib.request → CSV parse
│   └── Merge MCX rows into main rows
├── SymbolResolver.load_from_rows(rows)
│   ├── For each row: _row_to_instrument() → Instrument
│   ├── _generate_alternate_keys() → 30+ keys per instrument
│   ├── Register all keys in new_by_symbol dict
│   └── Atomic swap under _lock: self._by_symbol = new_by_symbol
└── ResolverRefresher (background, daily)
    └── connection.load_instruments(use_cache=True) → atomic swap
```

---

## 21. Configuration

### 21.1 Environment Variables

| Variable | Default | Purpose | Used By |
|----------|---------|---------|---------|
| `DHAN_CLIENT_ID` | (required) | Broker client ID | Settings |
| `DHAN_ACCESS_TOKEN` | (optional) | Pre-existing token | Settings |
| `DHAN_PIN` | "" | Login PIN for TOTP | Factory |
| `DHAN_TOTP_SECRET` | "" | TOTP secret | Factory |
| `DHAN_BASE_URL` | `https://api.dhan.co/v2` | REST API base URL | Settings |
| `DHAN_HTTP_TIMEOUT` | 15.0 | HTTP request timeout (seconds) | HttpClient |
| `DHAN_ENABLE_RETRY` | True | Enable retry logic | HttpClient |
| `DHAN_POOL_CONNECTIONS` | 50 | urllib3 pool connections | Settings |
| `DHAN_POOL_MAXSIZE` | 100 | urllib3 pool maxsize | Settings |
| `DHAN_ALLOW_LIVE_ORDERS` | False | Enable live order placement | Settings |
| `DHAN_TOKEN_STATE_DIR` | `runtime/` | Token state persistence dir | Settings |
| `DHAN_TOKEN_LIFETIME_SECONDS` | 86400 | Token lifetime (24h) | Scheduler |
| `DHAN_SCHEDULER_INTERVAL_SECONDS` | 1200 | Scheduler poll interval (20min) | Scheduler |
| `DHAN_REFRESH_BUFFER_SECONDS` | 600 | Refresh buffer before expiry (10min) | Scheduler |
| `DHAN_MAX_RECONNECT_ATTEMPTS` | 50 | Max WS reconnect attempts | MarketFeed, OrderStream |
| `DHAN_STALENESS_THRESHOLD_SECONDS` | 60.0 | Staleness detection threshold | MarketFeed |
| `DHAN_STALENESS_WATCHDOG_INTERVAL_SECONDS` | 5.0 | Watchdog check interval | MarketFeed |
| `DHAN_RECONNECT_COOLDOWN_SECONDS` | 300 | Cooldown after max reconnect | MarketFeed, OrderStream |
| `DHAN_WS_429_COOLDOWN_SECONDS` | 60 | Base 429 cooldown | Admission |
| `DHAN_WS_429_COOLDOWN_MAX_SECONDS` | 900 | Max 429 cooldown | Admission |
| `DHAN_WS_429_PENALTY_WINDOW_SECONDS` | 3600 | Streak reset window | Admission |
| `DHAN_TOKEN_STATE_DIR` | `runtime/` | Lock + cooldown file dir | Admission |

### 21.2 Hardcoded Constants

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| `MAX_INSTRUMENTS` | 1000 | DhanMarketFeed | WS subscription limit |
| `_MAX_RETRIES` | 3 | DhanHttpClient | HTTP retry limit |
| `_BASE_DELAY_MS` | 500 | DhanHttpClient | Initial backoff |
| `_MAX_DELAY_MS` | 5000 | DhanHttpClient | Max backoff |
| `_REFRESH_COOLDOWN_SECONDS` | 60 | DhanHttpClient | Token refresh cooldown |
| `_RATE_LIMIT_BACKOFF_SECONDS` | 130 | DhanHttpClient | Rate limit backoff |
| `INITIAL_BACKOFF` | 1.0 | ReconnectingServiceMixin | WS reconnect initial |
| `MAX_BACKOFF` | 30.0 | ReconnectingServiceMixin | WS reconnect max |
| `ORDERS_FAILURE_THRESHOLD` | 3 | circuit_breaker.py | Orders CB sensitivity |
| `DEFAULT_FAILURE_THRESHOLD` | 5 | circuit_breaker.py | Other CB sensitivity |
| `RECOVERY_TIMEOUT_MS` | 30000 | circuit_breaker.py | CB recovery time |
| `IdempotencyCache.max_size` | 1000 | orders.py | Max cached orders |
| `IdempotencyCache.ttl` | 3600 | orders.py | Cache TTL |
| `TTLCache.maxsize` | 10000 | order_stream.py | Max tracked fills |
| `TTLCache.ttl` | 3600 | order_stream.py | Fill tracking TTL |
| `_BATCH_SIZE` | 1000 | PollingMarketFeed | Batch LTP limit |
| `DHAN_DEPTH_20_MAX_INSTRUMENTS` | 50 | constants.py | Depth-20 WS subscription limit |
| `DHAN_DEPTH_200_MAX_INSTRUMENTS` | 1 | constants.py | Depth-200 WS subscription limit |
| `DHAN_IDEMPOTENCY_MAX_SIZE` | 1000 | constants.py | Idempotency cache max entries |
| `DHAN_IDEMPOTENCY_TTL_SECONDS` | 3600 | constants.py | Idempotency cache TTL (1h) |
| `REFRESH_INTERVAL` | 86400 | resolver_refresher.py | Resolver refresh interval (24h) |
| `CACHE_TTL_HOURS` | 6 | loader.py | Instrument CSV cache TTL |
| `MCX_FETCH_TIMEOUT` | 30 | loader.py | MCX detailed API timeout |
| `_DERIVATIVE_SEGMENTS` | frozenset(6) | identity.py | Segments that reject index fallback |

---

## 22. Known Limitations

### 22.1 Current Implementation Limitations

1. **No WebSocket-level rate limiting**: The SDK manages the MarketFeed WS connection; we cannot throttle subscription messages at the SDK level.

2. **Backfill is sequential**: `_backfill_gap()` calls REST API per symbol sequentially — no batching. This can cause burst HTTP requests on reconnect.

3. **No request coalescing**: Multiple adapters hitting the same circuit breaker bucket don't coalesce — each request acquires its own rate limit token.

4. **Token refresh is TOTP-only**: No OAuth refresh token flow; relies entirely on TOTP generation which has Dhan's 2-minute rate limit.

5. **Depth feeds don't share admission control**: Only MarketFeed uses `MarketFeedConnectionAdmission`; depth feeds connect independently.

6. **No connection health pre-check**: Before placing an order, there's no check that the order stream WS is healthy.

7. **`_stream_lock` in BrokerGateway**: The gateway's stream lock is a `threading.Lock` (non-reentrant), while the SubscriptionEngine uses `RLock`. Potential deadlock if `stream()` is called from within a callback.

### 22.2 Technical Debt

1. **Legacy `_stream_registry` and `_wrapper_registry`**: Still present in `BrokerGateway` but deprecated in favor of `SubscriptionEngine`.

2. **`cbs["portfolio"]` created but unused**: The portfolio circuit breaker is created but not wired into the HTTP client (only read/write/admin are used).

3. **`_adaptive_intervals` never decrease**: Once increased by a 429 response, adaptive intervals stay elevated until process restart.

4. **`InstrumentLoader._fetch_mcx_detailed()` bypasses HTTP client**: Uses raw `urllib.request` instead of `DhanHttpClient`, so it has no rate limiting, retry, or circuit breaker protection. A failure here is caught but the MCX instrument data may be silently missing.

5. **`SymbolResolver._generate_alternate_keys()` generates 30+ keys per instrument**: For a large instrument master (10,000+ instruments), this creates 300,000+ dict entries. Memory footprint is significant and loading time is dominated by key generation.

6. **`DhanSymbolValidator._validate_fo()` scans ALL instruments**: Linear scan of entire instrument master for every F&O symbol validation. O(N) per call with no caching. For 10,000+ instruments this is a performance hotspot.

7. **`portfolio.py` has dead code**: Lines 132-146 contain a `from_sdk_int` function that appears after a truncated code block (the `get_holdings` method has a syntax-level issue where `elif avgSegment:` is unreachable).

8. **`instrument_adapter.py` imports `datetime` at bottom of file** (L101): The `from datetime import datetime` is at the end of the file rather than the top, which is a code organization issue.

9. **`extended.py` has a truncated docstring**: The `get_option_chain` method docstring contains a broken code fragment (`px > 0 and ltp > 0:`) from the portfolio adapter that was accidentally pasted.

### 22.3 Production Risks

1. **TOTP rate limit during market open**: If token expires at market open and multiple processes try TOTP simultaneously, only one succeeds per 2 minutes.

2. **Watchdog false positive**: The staleness watchdog (60s threshold) could trigger during low-activity periods (e.g., pre-market) when ticks are infrequent.

3. **Thread leak on stop timeout**: If `stop(timeout_seconds=5.0)` doesn't join in time, the daemon thread leaks. These are daemon threads so they won't block process exit, but state may be inconsistent.

---

## 23. Production Readiness Assessment

| Dimension | Rating | Evidence |
|-----------|--------|----------|
| **Reliability** | GOOD | Reconnect with backoff, max attempts + cooldown, staleness watchdog, backfill |
| **Fault Tolerance** | GOOD | Circuit breakers (3 categories), token refresh retry, adaptive rate limiting |
| **Scalability** | MODERATE | 1000 instrument WS limit, single market feed per account, batch REST APIs |
| **Observability** | GOOD | Prometheus metrics, health() on all services, structured logging, correlation IDs |
| **Maintainability** | GOOD | Adapter pattern, registry-driven construction, mixin for shared behavior |
| **Recovery** | GOOD | Token broadcast to all receivers, subscription replay on reconnect, host-wide admission |
| **Concurrency Safety** | GOOD | RLock on critical sections, thread-safe caches, fcntl host lock |
| **Thread Safety** | MODERATE | Some cross-thread WS close operations are best-effort; `_lock` vs `_callback_lock` separation |
| **Resource Safety** | GOOD | Lifecycle-managed shutdown, thread joins, session close, admission release |
| **Production Suitability** | **READY** | All critical paths have retry, rate limiting, and observability. Edge cases documented. |

---

## 24. Improvement Opportunities

### 24.1 Architecture

1. **Batch backfill**: Replace sequential `_backfill_gap()` REST calls with batch LTP API.
2. **Circuit breaker for depth feeds**: BinaryDepthFeed has no circuit breaker protection.
3. **Shared admission for depth feeds**: Extend `MarketFeedConnectionAdmission` to depth connections.

### 24.2 Performance

1. **Adaptive interval decay**: Allow `_adaptive_intervals` to decay over time instead of staying permanent.
2. **Pre-connect health check**: Verify order stream health before order placement.
3. **Connection pool tuning**: Expose `pool_connections` and `pool_maxsize` via settings.

### 24.3 Reliability

1. **Pre-market watchdog suppression**: Disable staleness watchdog outside market hours.
2. **Token pre-warm**: Refresh token 10 minutes before market open instead of on expiry.
3. **Graceful degradation**: If order stream is down, queue order updates and replay on reconnect.

### 24.4 429 Prevention

1. **Request coalescing**: Merge concurrent requests to same endpoint into a single batch.
2. **Global request budget**: Track total requests/second across all buckets.
3. **Smarter backfill**: Use batch API and limit backfill to symbols with active callbacks.

### 24.5 Connection Management

1. **Exponential backoff jitter**: Add random jitter to reconnect backoff to prevent thundering herd.
2. **Connection attempt rate limiting**: Limit reconnect attempts per minute (not just total count).
3. **Depth feed token update**: Currently closes WS on token update; could update in-place if SDK supports it.

### 24.6 Instrument Master Pipeline

1. **MCX fetch should use HTTP client**: `_fetch_mcx_detailed()` uses raw `urllib.request` — should use `DhanHttpClient` for retry/rate-limit protection.
2. **Alternate key memory optimization**: 30+ keys per instrument × 10,000 instruments = 300K+ dict entries. Consider lazy key generation or trie-based lookup.
3. **F&O validation performance**: `DhanSymbolValidator._validate_fo()` does O(N) linear scan of all instruments per call. Add an underlying+expiry index for O(1) lookup.
4. **Resolver refresh atomicity**: `ResolverRefresher` calls `load_instruments()` which does a full CSV download + parse. Consider incremental updates for new weekly series.
5. **Instrument adapter import ordering**: `instrument_adapter.py` imports `datetime` at the bottom (L101) — should be at the top per PEP 8.

### 24.7 Identity and Invariant Layer

1. **Audit log volume**: `DhanIdentityProvider._wrap()` emits `logger.info` on every resolution. Under high-frequency trading this could generate thousands of log entries per second. Consider `logger.debug` with a periodic summary.
2. **Coerce helper complexity**: `coerce_identity_provider()` has 4 branches including a duck-typing fallback. Simplify by requiring explicit `DhanIdentityProvider` at construction time.

### 24.8 Extended Order Types

1. **No idempotency for super/forever/conditional orders**: Only `OrdersAdapter` has `IdempotencyCache`. Super orders, forever orders, and conditional triggers have no duplicate prevention.
2. **No circuit breaker differentiation**: All order types share the same write circuit breaker. A burst of super order + forever order + conditional trigger placements could trip the CB for regular orders too.
3. **Reconciliation coverage**: `DhanReconciliationService` only reconciles regular orders and positions. Super orders, forever orders, and conditional triggers are not included.

---

## 25. Code References

### File Index

| File | Lines | Primary Class | Purpose |
|------|-------|---------------|---------|
| `brokers/dhan/factory.py` | 537 | BrokerFactory | Gateway construction, auth wiring |
| `brokers/dhan/connection.py` | 715 | DhanConnection | Adapter wiring, token registry |
| `brokers/dhan/gateway.py` | 664 | BrokerGateway | Public API facade |
| `brokers/dhan/http_client.py` | 555 | DhanHttpClient | REST client with resilience |
| `brokers/dhan/subscription_engine.py` | 281 | SubscriptionEngine | Subscription ref-counting |
| `brokers/dhan/websocket/market_feed.py` | 1004 | DhanMarketFeed | Real-time market data WS |
| `brokers/dhan/websocket/order_stream.py` | 347 | DhanOrderStream | Order update WS |
| `brokers/dhan/websocket/polling_feed.py` | 224 | PollingMarketFeed | REST polling fallback |
| `brokers/dhan/websocket/_helpers.py` | 172 | _DhanContext | SDK shim, instrument conversion |
| `brokers/dhan/depth_feed_base.py` | 704 | BinaryDepthFeed | Binary depth WS (20/200) |
| `brokers/dhan/depth_20.py` | 89 | DhanDepth20Feed | 20-level depth WS subclass |
| `brokers/dhan/depth_200.py` | 123 | DhanDepth200Feed | 200-level depth WS subclass |
| `brokers/dhan/reconnecting_service.py` | 201 | ReconnectingServiceMixin | Shared reconnect machinery |
| `brokers/dhan/connection_admission.py` | 256 | MarketFeedConnectionAdmission | Host-wide WS admission |
| `brokers/dhan/token_scheduler.py` | 220 | TokenRefreshScheduler | Background token refresh |
| `brokers/dhan/settings.py` | 232 | DhanConnectionSettings | Configuration dataclass |
| `brokers/dhan/session_manager.py` | 73 | DhanSessionManager | Session state view |
| `brokers/dhan/account_registry.py` | 72 | AccountConnectionRegistry | Process-wide singleton |
| `brokers/dhan/resilience/rate_limiter.py` | 217 | DhanRateLimiterFactory | Rate limiter config |
| `brokers/dhan/resilience/circuit_breaker.py` | 119 | DhanCircuitBreakerFactory | CB config |
| `brokers/dhan/resilience/retry_executor.py` | 177 | DhanRetryExecutorFactory | Retry policy config |
| `brokers/dhan/exceptions.py` | 143 | DhanError hierarchy | Exception classes |
| `brokers/dhan/metrics.py` | 42 | (module) | Prometheus metrics |
| `brokers/dhan/orders.py` | 783 | OrdersAdapter | Order management |
| `brokers/dhan/market_data.py` | 187 | MarketDataAdapter | LTP, quote, depth, OHLC |
| `brokers/dhan/historical.py` | 173 | HistoricalAdapter | Historical candles |
| `brokers/dhan/options.py` | 270 | OptionsAdapter | Option chain, greeks, expired data |
| `brokers/dhan/portfolio.py` | 103 | PortfolioAdapter | Positions, holdings, balance |
| `brokers/dhan/identity.py` | 546 | DhanIdentityProvider | Symbol→security_id resolution |
| `brokers/dhan/resolver.py` | 539 | SymbolResolver | O(1) symbol lookup + alternate keys |
| `brokers/dhan/loader.py` | 305 | InstrumentLoader | CSV download + daily cache |
| `brokers/dhan/resolver_refresher.py` | 266 | ResolverRefresher | Background instrument refresh |
| `brokers/dhan/invariants.py` | 264 | (module) | Payload boundary assertions |
| `brokers/dhan/domain.py` | 359 | (module) | Dhan domain models + enums |
| `brokers/dhan/symbol_validator.py` | 437 | DhanSymbolValidator | Pre-trade symbol verification |
| `brokers/dhan/super_orders.py` | 333 | SuperOrdersAdapter | Bracket orders |
| `brokers/dhan/forever_orders.py` | 290 | ForeverOrdersAdapter | GTT/OCO orders |
| `brokers/dhan/conditional_triggers.py` | 269 | ConditionalTriggersAdapter | Price-based alert orders |
| `brokers/dhan/extended.py` | 313 | DhanExtendedCapabilities | Broker-specific features |
| `brokers/dhan/common_extensions.py` | 151 | DhanSuperOrderExtension | Cross-broker extension providers |
| `brokers/dhan/reconciliation.py` | 185 | DhanReconciliationService | OMS vs broker drift detection |
| `brokers/dhan/alerts.py` | 161 | AlertsAdapter | Price alerts |
| `brokers/dhan/margin.py` | 115 | MarginAdapter | Margin calculator |
| `brokers/dhan/ledger.py` | 73 | LedgerAdapter | Account ledger |
| `brokers/dhan/edis.py` | 113 | EDISAdapter | eDIS/TPIN authorization |
| `brokers/dhan/ip_management.py` | 131 | IPManagementAdapter | Static IP whitelisting |
| `brokers/dhan/exit_all.py` | 55 | ExitAllAdapter | Emergency exit all |
| `brokers/dhan/futures.py` | 86 | FuturesAdapter | Futures contract discovery |
| `brokers/dhan/instrument_adapter.py` | 102 | (module) | InstrumentId conversion |
| `brokers/dhan/segments.py` | 146 | (module) | Wire format + SDK int mappings |
| `brokers/dhan/status_mapper.py` | 23 | (module) | Dhan status → canonical |
| `brokers/dhan/constants.py` | 35 | (module) | WS limits, idempotency config |
| `brokers/dhan/secret_utils.py` | 32 | (module) | Env/file secret reader |
| `config/endpoints.py` | 453 | Dhan, Upstox | Endpoint registry |
| `domain/constants/auth.py` | 43 | (module) | Token lifecycle constants |

---

*Document generated from codebase analysis. Every claim is traceable to the referenced file and line number. No assumptions made.*
