export const meta = {
  name: 'broker-marketdata-remediation',
  description: 'Remediate broker integration + market data findings per dependency graph (4 phased barriers).',
  phases: [
    { title: 'Foundations', detail: 'shared capability + tick validators (new files)' },
    { title: 'Gateway interface fixes', detail: 'Dhan + Upstox gateway wiring' },
    { title: 'Reliability & rate limits', detail: 'locks, retry/backoff, dead-limiter, validation' },
    { title: 'Market data layer', detail: 'leaks, dedup, staleness, backfill' },
  ],
};

const REPO = '/Users/apple/Downloads/Trade_XV2';

function preamble() {
  return (
    'Repo root: ' + REPO + '. You are fixing a SPECIFIC issue in a trading-system codebase. ' +
    'RULES: (1) DO NOT run git commit/push or any destructive command. ' +
    '(2) Make surgical, minimal edits; preserve existing public signatures unless the task requires a change (then update all callers you can find). ' +
    '(3) Read the target files fully before editing. ' +
    '(4) After editing, verify with targeted tests: "cd ' + REPO + ' && ./venv/bin/python -m pytest <relevant paths> -q" if tests exist for the module; otherwise do an import smoke test ("cd ' + REPO + ' && ./venv/bin/python -c \'import <module>\'"). Note any PRE-EXISTING failures that are unrelated to your change; do not try to fix unrelated issues. ' +
    '(5) Report: changed file:line(s), the before/after behavior, and test outcome. Keep the report under 250 words.'
  );
}

phase('Foundations', async () => {
  await parallel([
    () => agent(
      preamble() + '\n\nTASK F1 (new file, no edits to existing files): Create ' + REPO + '/brokers/common/capabilities_validator.py. ' +
      'Implement `validate_gateway_capabilities(gateway, log=logging.getLogger(__name__))` that: ' +
      '(a) calls gateway.capabilities() (a BrokerCapabilities-like object with supports_* bool attributes); ' +
      '(b) for each known capability maps to the expected method name, e.g. supports_modify_order -> "modify_order", supports_order_cancellation -> "cancel_order", supports_positions -> "positions", supports_holdings -> "holdings", supports_stream_order -> "stream_order", supports_depth -> "depth"/"stream_depth"; ' +
      '(c) if a capability is True but the gateway does NOT have the method (getattr(gateway, name, None) is None), log a WARNING naming the mismatch. Return a list of mismatch strings. ' +
      'Do NOT edit any gateway file. Do NOT modify brokers/common/__init__.py. Just create the file with a module docstring. Run an import smoke test.',
      { label: 'F1-cap-validator', phase: 'Foundations', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK F2 (new file, no edits to existing files): Create ' + REPO + '/brokers/common/tick_validation.py. ' +
      'Implement `is_valid_quote(quote, log=...) -> bool` that returns False when the quote should be DROPPED, mirroring Dhan strict mode (see brokers/dhan/websocket/market_feed.py:_publish_tick around 886/896): ' +
      'drop when ltp is None, ltp == 0, ltp is negative, ltp is not a finite number (NaN/inf via math.isfinite), or symbol/instrument is missing/empty. ' +
      'Also implement `validate_depth(book) -> bool` that returns False when the book is empty or its top-of-book price is None/0/negative. ' +
      'Use a Decimal-aware comparison (accept int/float/Decimal). Add a module docstring. Do NOT edit any existing file or __init__. Import smoke test only.',
      { label: 'F2-tick-validation', phase: 'Foundations', model: 'sonnet', agentType: 'general-purpose' }
    ),
  ]);
});

phase('Gateway interface fixes', async () => {
  await parallel([
    () => agent(
      preamble() + '\n\nTASK G1 (Dhan gateway + orders): In ' + REPO + '/brokers/dhan/gateway.py and ' + REPO + '/brokers/dhan/orders.py fix these: ' +
      '(1) Add a `modify_order(self, order_id, **changes)` method on DhanBrokerGateway that delegates to self._conn (the DhanConnection/orders adapter) modify_order. Use the same pattern as existing place_order/cancel_order delegation. ' +
      '(2) Add a `cancel_all_orders(self, **kwargs)` method on DhanBrokerGateway delegating to the orders adapter cancel_all_orders. ' +
      '(3) Fix `gateway.stream()`: it currently builds DhanMarketFeed directly and never registers feed.update_token as a token receiver (see gateway.py ~415-423). Route through the existing create_market_feed / lifecycle helper so feed.update_token is registered (look at brokers/dhan/connection_lifecycle.py / lifecycle_helper.py ~116 for how other feeds register). Keep behavior equivalent. ' +
      '(4) In DhanBrokerGateway.__init__, after super().__init__/setup, call `from brokers.common.capabilities_validator import validate_gateway_capabilities; validate_gateway_capabilities(self)` (import at top of file). ' +
      '(5) In brokers/dhan/orders.py cancel_all_orders: guard the response parsing so a non-dict (list/None) response does not raise AttributeError — use `data if isinstance(data, dict) else {}`, and return an empty list distinctly (do not silently swallow a real error; if live orders disabled, keep returning [] but that is acceptable). ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/dhan/tests -q (and import smoke test of gateway). Report changed file:line.',
      { label: 'G1-dhan-gateway', phase: 'Gateway interface fixes', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK G2 (Upstox broker wiring): In ' + REPO + '/brokers/upstox/broker.py, ' + REPO + '/brokers/upstox/factory.py, ' + REPO + '/brokers/upstox/extended.py, ' + REPO + '/brokers/upstox/gateway.py: ' +
      '(1) UpstoxBroker currently never assigns self.portfolio_stream, so gateway.stream_order (gateway.py ~520) and factory.create(lifecycle=...) (factory.py ~88) crash with AttributeError. Fix: in UpstoxBroker.__init__/construction, create `self.portfolio_stream = UpstoxPortfolioStream(...)` using the EXISTING class (it exists; only instantiated in tests). Wire it the same way the market-data feed is wired (token/connection). Ensure factory.create passes it and gateway.stream_order works. ' +
      '(2) gateway.extended is broken: UpstoxExtendedCapabilities.__init__ calls broker._ensure_extended() (extended.py ~50) but UpstoxBroker does not define _ensure_extended / _extended_ready / the lazy ipo/payments/mutual_funds/fundamentals/trade_pnl/profile/position_conversion attributes. Add these to UpstoxBroker (lazy-load pattern consistent with the rest of the broker) so gateway.extended returns a working object. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/upstox -q (and any test_extended_lazy_load.py). Report changed file:line.',
      { label: 'G2-upstox-wiring', phase: 'Gateway interface fixes', model: 'sonnet', agentType: 'general-purpose' }
    ),
  ]);
});

phase('Reliability & rate limits', async () => {
  await parallel([
    () => agent(
      preamble() + '\n\nTASK R1 (Dhan depth-200 limiter): In ' + REPO + '/brokers/dhan/depth_200.py and ' + REPO + '/brokers/dhan/resilience/websocket_rate_limiter_simple.py: ' +
      'The SimpleWebSocketRateLimiter is effectively dead (its _depth_200_connections counter is never incremented/decremented so can_create_depth_200_connection() always returns True). Worse, depth_200.py ~217-235 does `while not ws_rate_limiter.can_create_depth_200_connection(): time.sleep(0.1)` — an UNBOUNDED busy-wait that can spin a thread forever when the pool is full, and it holds a lock while doing so. ' +
      'Fix: remove the spin-wait loop. Use the REAL limiter (MarketFeedConnectionAdmission / connection_admission.py) that is already wired into market_feed, OR replace the pool cap enforcement with a bounded wait (e.g. a condition variable / short bounded retries with timeout that raises a clear exception instead of spinning). If you keep a limiter, make can_create_* actually track connections. Add a module-level deprecation note to websocket_rate_limiter_simple.py if left unused. Do NOT break the Depth200ConnectionPool eviction-by-oldest behavior. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/dhan/tests -k depth -q (import smoke test if no depth tests). Report.',
      { label: 'R1-dhan-limiter', phase: 'Reliability & rate limits', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK R2 (Dhan order-stream auth on reconnect): In ' + REPO + '/brokers/dhan/websocket/order_stream.py: ' +
      'The order-stream reconnect loop (OrderStream._run ~116-163) backs off on any exception but never triggers a token refresh or distinguishes an AUTH failure (401/403/expired token) from a transient drop — it depends entirely on an external scheduler to push a fresh token, so during the gap reconnects may repeat-fail on a stale token. ' +
      'Fix: when a reconnect failure looks like an auth/token-expiry error (catch the specific auth exception type from brokers/dhan/exceptions.py, or detect 401/403/expired in the error text), proactively request a token refresh/rotation via the connection\'s token manager (available on the connection/feed) BEFORE backing off, and avoid tight reconnect storms (cap retry frequency). Keep the existing backoff discipline. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/dhan/tests -k order_stream -q (import smoke test otherwise). Report.',
      { label: 'R2-dhan-ostream', phase: 'Reliability & rate limits', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK R3 (Dhan idempotency lock scope): In ' + REPO + '/brokers/dhan/orders.py, the place_order method (around 249-379) holds a single idempotency RLock across the ENTIRE method including the blocking HTTP post to /orders (around 338). This serializes all concurrent order placements per adapter and a hung broker call stalls everything. ' +
      'Fix: restructure so the lock is held ONLY for the idempotency cache check-and-reserve, then RELEASED before the blocking self._client.post(...), then re-acquired to record the result. Preserve the correlation-id idempotency semantics (same correlation id must not double-submit). Ensure thread-safety: use a clear check-reserve / commit pattern (e.g. mark correlation id reserved under lock; send; record outcome under lock; on exception clear the reservation so a retry is allowed). ' +
      'Do NOT change place_order\'s public signature or return type. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/dhan/tests -k "order or idempot" -q (import smoke test otherwise). Report.',
      { label: 'R3-dhan-lock', phase: 'Reliability & rate limits', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK R4 (Upstox retry/backoff + bounded acquire): In ' + REPO + '/brokers/upstox/auth/http.py, ' + REPO + '/brokers/upstox/auth/context.py, ' + REPO + '/brokers/upstox/rate_limiter.py: ' +
      '(1) _execute_request only special-cases 401/403 (token refresh). A 429 Too Many Requests falls through to raise UpstoxApiError with NO backoff, and there is no retry for transient 5xx/network errors even though ctx.make_retry_executor exists but is never called. Wire the existing RetryExecutor (or a simple bounded retry with exponential backoff + Retry-After for 429) into _execute_request for transient failures (429, 5xx, requests.exceptions.*). Keep the 401/403 token-refresh path. ' +
      '(2) _execute_request calls self._rate_limiter.acquire(bucket) with no timeout (auth/http.py ~259); rate_limiter.acquire with timeout=None blocks FOREVER. Change the default acquire to use a finite timeout (e.g. 30s) and raise a clear timeout error instead of hanging the thread/event-loop. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/upstox -k "auth or rate or http" -q (import smoke test otherwise). Report.',
      { label: 'R4-upstox-retry', phase: 'Reliability & rate limits', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK R5 (Upstox modify fallback): In ' + REPO + '/brokers/upstox/orders/order_command_adapter.py, modify_order (around 99-130) does a blocking get_order lookup to recover instrument_key; if that lookup fails it FALLS BACK to `instrument_key = order_id` (around 119-124), which is a guaranteed-bad request sent to Upstox V3. ' +
      'Fix: when instrument_key cannot be resolved (get_order fails or returns no instrument_key), raise a clear, specific error (e.g. ValueError/OrderError) describing that instrument_key is required, instead of sending order_id as the key. Do not change the success path. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/upstox -k "modify or order_command" -q (import smoke test otherwise). Report.',
      { label: 'R5-upstox-modify', phase: 'Reliability & rate limits', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK R6 (Upstox strict tick validation): In ' + REPO + '/brokers/upstox/adapters/tick_translator.py and ' + REPO + '/brokers/upstox/websocket/market_data_v3.py, the Upstox live path performs NO validation (tick_translator _extract_price returns Decimal("0") for missing fields and builds Quote(ltp=0) with no drop), unlike Dhan strict mode. ' +
      'Fix: import `is_valid_quote` from brokers.common.tick_validation (created in Phase 0) and DROP invalid quotes (ltp None/0/negative/non-finite, missing symbol) before forwarding to listeners in market_data_v3.py (around the _publish/_track_tick path ~344-368). Keep the decoded exchange_timestamp. Do not change valid-data behavior. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/upstox -k "tick or translator" -q (import smoke test otherwise). Report.',
      { label: 'R6-upstox-tick', phase: 'Reliability & rate limits', model: 'sonnet', agentType: 'general-purpose' }
    ),
  ]);
});

phase('Market data layer', async () => {
  await parallel([
    () => agent(
      preamble() + '\n\nTASK M1 (Dhan depth feed off_depth + staleness): In ' + REPO + '/brokers/dhan/depth_feed_base.py (BinaryDepthFeed): ' +
      '(1) It exposes on_depth but has NO off_depth/unregister method, so consumers that unsubscribe leak callbacks for the feed lifetime. Add symmetric off_depth / off_quote unregister methods that remove the callback from the same list on_depth appends to (mirror DhanMarketFeed.off_depth/off_quote around market_feed.py 582-596). ' +
      '(2) The depth feed has no self-healing staleness: depth_feed_base.py ~411-421 only does asyncio.wait_for(ws.recv(), 30.0) then continue on timeout, so a half-open silent-but-connected socket persists forever. Add an application-level freshness check: if no message received for a threshold (e.g. reuse DHAN_STALENESS_THRESHOLD_SECONDS or a depth-specific constant), force a reconnect. Keep health() reporting last_message_age. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/dhan/tests -k depth -q (import smoke test otherwise). Report.',
      { label: 'M1-depth-off-stale', phase: 'Market data layer', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK M2 (EventLog._seen_ids memory leak): In ' + REPO + '/infrastructure/event_bus/event_log.py, `_seen_ids` is an unbounded set (around 147, 184-185) that grows for every event_id seen in the process lifetime and is inherited by BufferedEventLog — a genuine memory leak under high tick volume. ' +
      'Fix: bound it. Use a fixed-size LRU-ish structure (e.g. collections.OrderedDict capped at a max size with eviction of oldest, or a sets with periodic trim, or a TTL). Preserve the dedup semantics (an id seen recently is still detected as duplicate). Choose a sensible max (e.g. 200_000) and add a module constant. Do NOT change the public EventLog/BufferedEventLog API. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest infrastructure/event_bus -q (import smoke test otherwise). Report.',
      { label: 'M2-seen-ids', phase: 'Market data layer', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK M3 (Orchestrator exchange-ts + dedup): In ' + REPO + '/tradex/runtime/stream_orchestrator.py: ' +
      '(1) It sets MarketTick.event_time = now (around 576) and discards the exchange timestamp carried by Upstox quotes, while Dhan quotes have no timestamp. Preserve exchange time: when the incoming Quote has a non-null timestamp (exchange time), use it as MarketTick.event_time (fall back to local now when absent). ' +
      '(2) There is NO dedup across reconnect/backfill: every tick gets a fresh event_id so the bus idempotency never fires, and MarketTick.sequence is unused, causing duplicate ticks delivered to all consumers after a reconnect/backfill overlap. Add dedup: use (instrument, exchange_time/sequence) to drop duplicates within a short window before publishing/normalizing. Keep it cheap (bounded cache). ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest tradex/runtime -k "stream or orchestrator or tick" -q (import smoke test otherwise). Report.',
      { label: 'M3-orch-ts-dedup', phase: 'Market data layer', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK M4 (Polling fallback emits TICK + real OHLC): In ' + REPO + '/brokers/dhan/websocket/polling_feed.py (around 206-216), the polling fallback fetches LTP only, hardcodes open/high/low/close=0 and volume=0, and NEVER publishes TICK events to the event bus (its constructor has no event_bus). During a WS outage this causes a full data gap. ' +
      'Fix: (1) accept an optional event_bus (or reuse the feed\'s bus) and publish TICK events from the polled quotes so they are persisted; (2) populate OHLC/volume from the polled quote fields when available instead of zeroing them (only zero when genuinely absent). Keep the polling cadence/behavior otherwise identical. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest brokers/dhan/tests -k "poll or feed" -q (import smoke test otherwise). Report.',
      { label: 'M4-polling-tick', phase: 'Market data layer', model: 'sonnet', agentType: 'general-purpose' }
    ),
    () => agent(
      preamble() + '\n\nTASK M5 (Default gap backfill wiring): In ' + REPO + '/application/composer/factory.py (and any related broker composition), the default composition does NOT supply a backfill_callback to broker market feeds, so on reconnect the gap between disconnect_time and reconnect is unfilled (silent data loss). Both broker feeds support a backfill_callback (see brokers/dhan/websocket/market_feed.py ~645-678 and brokers/upstox/websocket/market_data_v3.py ~370-412). ' +
      'Fix: supply a default backfill_callback (or wire the existing historical coordinator / a history fetch) when constructing the broker feeds in the composer factory, so reconnect gaps are reconciled by default. Keep it defensive: if no historical source is configured, log and skip rather than crash. ' +
      'Run: cd ' + REPO + ' && ./venv/bin/python -m pytest application/composer -q (import smoke test otherwise). Report.',
      { label: 'M5-backfill', phase: 'Market data layer', model: 'sonnet', agentType: 'general-purpose' }
    ),
  ]);
});
