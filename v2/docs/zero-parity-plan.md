# Zero-Parity Implementation Plan — v2 `broker` package vs legacy `src` (Trade_J)

**Scope:** Achieve functional AND non-functional parity between the v2 `plugins/brokers`
package and the legacy `src/brokers` implementation, covering instrument mapping,
token management, extensions, rate limiting, and resilience. Tokenless instrument
masters, the gateway public-API surface, and per-broker connection seams are the
anchors. Verified by reading source on both sides (no assumptions).

**Status of exploration (done):** All broker source on both sides traced; live
probes against Dhan + Upstox gateways confirm current behavior. 338 unit tests
pass. This plan closes the remaining parity gaps with targeted edits (no shotgun
surgery) and adds regression tests at the gateway surface.

---

## A. Current State — What's Already Parity-Correct

| Area | v2 status |
|---|---|
| Gateway public API (ltp/quote/depth/history/orders/funds/stream/extension) | ✅ superset of legacy `BrokerGateway` |
| Per-broker connection (Gateway→Connection→adapters) | ✅ 3-layer, faithful |
| `BrokerAdapter` Protocol enforcement at composition root | ✅ runtime `isinstance` check |
| Token lifecycle (probe-before-mint, 401→force-refresh, JWT-expiry buffer) | ✅ Dhan + Upstox |
| Per-request re-auth + 401 retry (`on_auth_failure`) | ✅ wired in transport |
| Tokenless instrument master (Dhan CSV, Upstox JSON.gz) | ✅ both verified HTTP 200 |
| Index resolution (NIFTY/BANKNIFTY) | ✅ Dhan wire + Upstox wire (fixed this pass) |
| Rolling-window rate caps + 429 cooldown + metrics | ✅ `RollingWindowCounter`, `trigger_cooldown`, `BrokerMetrics` |
| Retry/backoff (429,5xx) + jitter | ✅ matches legacy |
| Circuit breaker | ✅ closed/open/half-open |
| Dhan depth extension wired to streaming | ✅ `DhanDepth20/200Extension` |

---

## B. Parity Gaps (prioritized, evidence-linked)

### P0 — Correctness gaps that break data/orders
| ID | Gap | Evidence | Legacy reference |
|---|---|---|---|
| **P0-1** | **Order idempotency missing** — no dedupe/reservation on `place_order`; duplicate submits possible on retry/restart | No `idempot`/`nonce`/`client_order_id` in v2; legacy `common/idempotency.py` has `IdempotencyCache.reserve/commit` | `src/brokers/common/idempotency.py` |
| **P0-2** | **`TokenRefreshScheduler` is dead code** — defined, never `.start()`-ed; no background proactive refresh loop runs | Only definition at `common/token_lifecycle.py:88`; zero instantiations | `src/brokers/providers/*/auth/token_scheduler.py` |
| **P0-3** | **Upstox extensions seam empty** — no depth/quote extensions registered; `BrokerExtensions()` is empty | `upstox/gateway.py:45` `BrokerExtensions()` | legacy `DhanExtendedCapabilities` (4 sub-facades) |
| **P0-4** | **Rate-limit profile not sourced from canonical `RateLimitProfile`** — v2 hardcodes `DHAN_RATE_LIMITS`/`UPSTOX_RATE_LIMITS` and uses fixed 60s cooldown, ignoring legacy `cooldown_on_429_s=130` (Dhan) / `min_interval_ms` | `common/rate_limit.py` has no `RateLimitProfile` import; legacy `rate_limit_config.py:24` `cooldown_on_429_s:130` | `src/brokers/common/rate_limit_config.py` |

### P1 — Functional coverage gaps
| ID | Gap | Evidence |
|---|---|---|
| **P1-1** | **Dhan super/forever orders, EDIS, TPIN** not exposed via extensions (only depth) | `dhan/extensions.py` has only depth; legacy `DhanOrderCapabilities` / `account_capabilities` |
| **P1-2** | **Upstox depth streaming not implemented** — `upstox/adapters/streaming.py` has no `stream_depth`; only Dhan does | grep `stream_depth` in upstox streaming = empty |
| **P1-3** | **Instrument `search()` return-type divergence** — v2 returns `list[Instrument]`; legacy returns dicts; no `limit` cap (legacy caps 20) | `dhan/adapters/instruments.py` `search` |
| **P1-4** | **`load_instruments` not wired into runtime boot** — `load_v2_env` only called by `check_connection.py`, not by `broker_factory.build_broker_adapter` | grep `load_v2_env` callers = 1 (diagnostic CLI) |
| **P1-5** | **No `get_trade_book`/`get_margin` on Dhan/Upstox gateways** (legacy `gateway.funds()/margin()`) | v2 gateway has funds/positions/holdings only |

### P2 — Non-functional gaps
| ID | Gap | Evidence |
|---|---|---|
| **P2-1** | **No observability for rate-limit events in production** — `NoOpMetrics` default; no Prometheus/OTLP wiring | `common/metrics.py` only Logging/NoOp |
| **P2-2** | **Async path absent** — legacy has `acquire_async`; v2 sync-only (OK if runtime sync, but document) | `common/rate_limiter.py` no async |
| **P2-3** | **`connect()` is a no-op** in both connections (lazy WS) — misleading; should at least validate config | `dhan/connection.py:91` |
| **P2-4** | **No contract/integration test module** mirroring legacy `common/contracts/module_test_suite.py` | v2 has unit tests only |
| **P2-5** | **Streaming reconnect lacks backoff config parity** — v2 `WsReconnectManager` defaults vs legacy `reconnecting_service` | compare `common/ws_reconnect.py` |

---

## C. Implementation Plan (phased, targeted)

### Phase 1 — Token management parity (P0-2, P0-4)
1. **Wire `TokenRefreshScheduler` into connection lifecycle.**
   - In `DhanConnection.__init__` / `UpstoxConnection.__init__`, after building `self._tokens`, create `self._scheduler = TokenRefreshScheduler(broker_id, self._tokens, broadcast=self._tokens._broadcast)` and `.start()` it in `connect()`, `.stop()` in `disconnect()`.
   - Register the streaming adapter as a `broadcast` receiver so live WS tokens update on refresh (`self._tokens.register_receiver(self.streaming.on_token_changed)`).
   - Add a `streaming.on_token_changed(token)` no-op-now hook (WS lib re-auth later).
2. **Source rate-limit profile from canonical `RateLimitProfile`.**
   - Add `limiter_from_profile(broker_id)` in `common/rate_limit.py` that reads `domain.capabilities.broker_capabilities.RateLimitProfile` (carries `min_interval_ms`, `cooldown_on_429_s`) and builds the multi-bucket limiter + rolling windows.
   - Replace `DHAN_RATE_LIMITS`/`UPSTOX_RATE_LIMITS` hardcoded dicts with profile-driven config; keep fallback constants.
   - Use profile `cooldown_on_429_s` (130 Dhan / 60 Upstox) in `_maybe_restore_rate` instead of hardcoded 60.

### Phase 2 — Order safety parity (P0-1)
3. **Add idempotency to order placement.**
   - Port `IdempotencyCache` (reserve/commit/clear_reservation) into `common/idempotency.py`.
   - Inject into `DhanOrdersAdapter`/`UpstoxOrdersAdapter`; key on `correlation_id`; `reserve()` before send, `commit()` on success, `clear_reservation()` on non-retryable error.
   - Expose `client_order_id` pass-through to wire body where broker supports it.

### Phase 3 — Extensions parity (P0-3, P1-1, P1-2)
4. **Upstox depth extension + streaming depth.**
   - Add `stream_depth()` to `UpstoxStreamingAdapter` (subscribe to Upstox depth feed; route via `wire.to_depth`).
   - Add `UpstoxDepthExtension` (+200) in `upstox/extensions.py`; register in `UpstoxGateway`.
5. **Dhan super/forever/EDIS extensions.**
   - Add `DhanSuperOrderExtension`, `DhanForeverOrderExtension`, `DhanEdisExtension` delegating to new `dhan/adapters/orders_execute.py` (port `execution/forever_orders.py`, `execution/order_placement.py`, `auth/edis.py`).
   - Register all in `DhanGateway.extensions`.

### Phase 4 — Instrument mapping & boot parity (P1-3, P1-4, P1-5)
6. **Standardize `search()`** — cap at 20 (mirror legacy), return canonical `Instrument`.
7. **Wire `load_v2_env` into `broker_factory.build_broker_adapter`** so LIVE boot reads `.env.local` (currently only diagnostic CLI does).
8. **Add `get_trade_book()` / `get_margin()`** to Dhan/Upstox gateways (delegate to portfolio adapter; port legacy endpoints).

### Phase 5 — Non-functional hardening (P2-1..P2-5)
9. **Metrics**: provide a `PrometheusMetrics` impl of `BrokerMetrics` (optional, behind flag) + wire into transport.
10. **Contract tests**: add `tests/contract/test_broker_adapter_contract.py` asserting every `BrokerAdapter` method exists + returns domain types (mirrors legacy `module_test_suite`).
11. **`connect()`**: validate config (base_url/client_id present) instead of no-op flag.
12. **Streaming reconnect**: align `WsReconnectManager` defaults with legacy (backoff base/dates).

---

## D. Verification Strategy (every phase)
- **Unit**: extend `test_market_data_parity.py` + add `test_token_scheduler.py`, `test_idempotency.py`, `test_extensions_parity.py`, `test_rate_limit_profile.py`.
- **Contract**: `test_broker_adapter_contract.py` runs against Dhan/Upstox/Paper gateways (no network) — asserts Protocol conformance + return types.
- **Live (gateway-only, per your constraint)**: `tradex.check_connection --broker dhan|upstox` + a gateway probe script exercising ltp/quote/depth/history/place_order(cancelled)/extensions.
- **Regression gate**: `env -u PYTHONPATH venv/bin/python -m pytest tests/unit/plugins -q` must stay green (currently 338).

## E. Anti-patterns to avoid (your "no shotgun surgery" mandate)
- Do NOT widen `BrokerAdapter` Protocol for broker-unique features → use the extension seam (already built).
- Do NOT duplicate `InMemoryInstrumentResolver` (shared, already used by both wires).
- Do NOT register stub extensions that return `None` (dead code) — only register when the backing adapter exists.
- Keep `plugins/` dependent only on `domain/` + `shared/` (composition root owns infra wiring).

## F. Suggested sequencing
P0-2 + P0-4 (token/rate) → P0-1 (idempotency) → P0-3 + P1-2 (Upstox ext) → P1-1 (Dhan super/EDIS) → P1-4 (boot env) → P2 hardening. Each phase is independently shippable + testable.
