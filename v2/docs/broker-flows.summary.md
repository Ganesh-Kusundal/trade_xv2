# Broker Implementation & Flows — v2 (graphviz summary)

**Produced by:** `system-modeler` + `flow-visualizer` + `graphviz`
**Scope:** `src/plugins/brokers/**`, `src/runtime/**`, `src/domain/ports/broker_adapter.py`
**Artifacts:**
- `broker-architecture.dot` — layered component / dependency view (all 3 brokers)
- `broker-classes.dot` — UML-style class diagram (fields + methods + implements/owns/depends-on)
- `broker-layers.dot` — C4-L3/L4 layered architecture (one cluster per layer, shows layer-crossing edges)
- `broker-order-flow.dot` — LIVE order + market-data + streaming runtime flow (Dhan example)

Render with any DOT viewer: `dot -Tsvg broker-classes.dot -o broker-classes.svg`
(Graphviz CLI was not installed in this environment, so only `.dot` sources are committed.)

## Reading order

1. **Domain (green)** — `BrokerAdapter` + `BaseTransport` protocols define the broker-agnostic contract. No broker code lives here.
2. **Runtime (blue)** — the composition root. `build_broker_adapter()` is the *only* place gateways are constructed; it resolves `BrokerId → gateway`, merges env credentials, and enforces the `BrokerAdapter` Protocol via an `isinstance` guard before returning.
3. **Gateways (gold)** — thin `BrokerAdapter` facades (`Paper/Dhan/UpstoxGateway`). They hold capability flags + an extension registry and delegate every method to their `Connection`.
4. **Connections (purple)** — own auth, transport, rate limiter and the five sub-adapters; implement `ConnectionLiveness` and `mass_status()`.
5. **Adapters (teal)** — identical 5-way split per broker: `orders / market_data / portfolio / instruments / streaming`, plus a `Wire` mapper translating native venue dicts ↔ domain types.
6. **Common (grey)** — shared plumbing: `HttpTransport`, `MultiBucketRateLimiter`, circuit-breaker/retry decorators, TOTP `TokenManager`, `WsReconnectManager`, `BrokerExtensions`.
7. **External venues (red)** — Dhan/Upstox REST + WebSocket endpoints.

## Class diagram (`broker-classes.dot`) — what each class holds

The class diagram shows fields and methods on every broker class, with UML-style relationships:

- **`BrokerAdapter` (Protocol)** — `submit_order / cancel_order / modify_order / get_order / get_orderbook / get_positions / get_funds / mass_status`. All three gateways implement it.
- **`BaseTransport` (Protocol)** — `get / post / put / delete`. `HttpTransport` implements it.
- **`FillSource` (Protocol)** — `submit / cancel`. `BrokerFillSource` (LIVE) implements it.
- **`ConnectionLiveness`** — abstract `connect / authenticate / disconnect + is_connected / is_authenticated`. `DhanConnection` and `UpstoxConnection` extend it.
- **`BrokerCapabilities`** — frozen dataclass of capability flags (market/limit/stop order, modify, cancel, asset classes, qty/value caps).
- **`*Gateway`** — thin facades; each owns a `*Connection` + a `BrokerExtensions` registry. `DhanGateway` adds `extension(ext_type)` for broker-unique capabilities.
- **`*Connection`** — owns `config`, `wire`, `TokenManager`, `MultiBucketRateLimiter`, `BaseTransport`, and the five sub-adapters (`orders`, `market_data`, `portfolio`, `instruments`, `streaming`).
- **`*OrdersAdapter`** — holds `_transport`, `_wire`, `_cache: dict[str, Order]`; implements `place_order / cancel_order / modify_order / get_order / get_orderbook`.
- **`*MarketDataAdapter`** — `get_quote / get_ltp / get_depth / get_history` (+ `get_batch_ltp / get_batch_quote` on Dhan).
- **`*StreamingAdapter`** — holds `_quote_subs`, `_depth_subs`, `_order_cb`, `_ws`, `_reconnect_manager`; implements `stream / unstream / stream_depth / stream_order / feed_raw / close`.
- **`*Wire`** — holds `_resolver: InMemoryInstrumentResolver`; maps native dicts ↔ domain types (`from_place_command`, `to_order_id`, `to_quote`, `to_ltp`, `to_depth`, `to_order`, `to_position`, `to_account`).
- **`HttpTransport`** — decorator stack: wraps `HttpClient` with `CircuitBreakerHttpClient` → `RetryableHttpClient`, plus `MultiBucketRateLimiter.acquire` and `token_provider` on every request.
- **`TokenManager`** — `Dhan/UpstoxTokenManager` with `TokenStore`, `TotpClient`, `TokenBroadcast`; `ensure_token(force_refresh=False)` follows store → env → TOTP with `JwtExpiry` + `TotpCooldownGuard`.
- **`WsReconnectManager`** — reconnect + subscription replay on WS close/drop.
- **`BrokerExtensions`** — per-gateway registry of broker-specific extension objects; `get(ext_type)` raises `LookupError` if not registered.

## Layered architecture (`broker-layers.dot`) — how a call crosses layers

Seven layers, top-down:

| Layer | Role | Key types |
| --- | --- | --- |
| **L0 · application** | strategy / risk / OMS | `StrategyEngine`, `RiskManager`, `OrderManager`, `ExecutionEngine`, `BrokerFillSource` |
| **L1 · domain ports** | broker-agnostic contracts | `BrokerAdapter`, `BaseTransport`, `FillSource` |
| **L2 · runtime** | composition root (only place brokers are constructed) | `build_broker_adapter`, `registry` |
| **L3 · broker plugins** | gateway facades | `PaperGateway`, `DhanGateway`, `UpstoxGateway` |
| **L4 · broker connections** | auth + transport + sub-adapter ownership | `*Connection` |
| **L5 · sub-adapters + wire** | per-broker 5-way split + native↔domain mapping | `*OrdersAdapter`, `*MarketDataAdapter`, `*StreamingAdapter`, `*Wire` |
| **L6 · common plumbing** | shared transport & resilience | `HttpTransport`, `WsReconnectManager`, `TokenManager`, `MultiBucketRateLimiter`, `BrokerExtensions` |
| **L7 · external venues** | Dhan / Upstox REST + WS | — |

Every broker call crosses L0 → L1 → L3 → L4 → L5 → L6 → L7 in that order; no layer reaches upward.

## Key architectural findings

- **Clean, uniform layering.** All three brokers follow the exact same
  `Gateway → Connection → {5 adapters + Wire}` shape. Paper mirrors the real
  brokers' surface (with `get_*`/no-prefix aliases) so it is a true drop-in.
- **Ports & Adapters done right.** Application code depends only on the
  `BrokerAdapter` / `BaseTransport` protocols; concrete brokers are wired at the
  composition root. A runtime `isinstance(gateway, BrokerAdapter)` check fails
  fast if a gateway drifts from the protocol.
- **Broker-unique features avoid protocol bloat.** `BrokerExtensions` is a typed
  registry seam (`gateway.extension(DhanDepth20Extension)`) so Dhan's 20/200-level
  depth doesn't widen the shared protocol or add broker `if` branches upstream.
- **Resilience centralised in `common`.** Rate limiting (bucket-per-path),
  circuit breaker, retry (write-safe — ambiguous writes are not blind-retried),
  and single-shot 401/403 re-auth all live in `HttpTransport`, shared by Dhan &
  Upstox. Streaming reconnect + subscription replay is shared via `WsReconnectManager`.
- **Real-money safety in the fill path.** `BrokerFillSource` (LIVE) never
  fabricates a `FILLED` order from a place-ack id — it returns a `SUBMITTED`
  shell or the gateway's `get_order`. Only `SimulatedFillSource` (BACKTEST)
  self-fills.
- **Token discipline.** `TokenManager` is probe-before-mint (store → env → TOTP),
  guarded by `TotpCooldownGuard` and `JwtExpiry`, with proactive refresh inside
  the expiry buffer.

## Edge-type legend (both graphs)

| Style | Meaning |
| --- | --- |
| solid black | implements / satisfies protocol |
| solid blue | constructs / owns (composition) |
| solid green | in-process delegate call |
| dashed red | network REST (HTTPS) |
| dotted purple | WebSocket stream |
| solid orange | failure / recovery path |

All nodes and edges are **high confidence** — traced directly to source files
listed under *Scope*. No inferred/runtime-only relationships were drawn.

## Follow-up / gaps observed

- **Upstox has no registered extensions yet** — its depth-streaming path is not
  implemented (noted in `common/extensions.py`). Dhan is the only broker with
  extension objects wired.
- **Paper `modify_order`** exists but `PAPER_CAPABILITIES.supports_stop_order=False`;
  confirm strategy/risk layers respect capability flags before routing stop orders.
- Rendering to SVG requires installing Graphviz (`brew install graphviz`).
