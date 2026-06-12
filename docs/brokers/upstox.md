# Upstox Broker Adapter

The Upstox adapter for Trade_XV2 — full V2 + V3 + HFT coverage, OAuth 2.0
auth, Protobuf WebSocket V3 feed, and 25 broker capabilities.

## Quickstart

```python
from brokers.gateway import Gateway
g = Gateway("upstox")
print(g.ltp("RELIANCE"))          # MarketDataProvider via get_quote
print(g.funds())                   # PortfolioProvider
print(g.orders())                  # OrderQueryAdapter
g.buy("RELIANCE", qty=1)          # OrderCommandAdapter (V3 HFT)
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `UPSTOX_CLIENT_ID` | required | OAuth client id |
| `UPSTOX_CLIENT_SECRET` | empty | OAuth client secret (required for OAuth flows) |
| `UPSTOX_ACCESS_TOKEN` | empty | Static access token (STATIC mode) |
| `UPSTOX_REFRESH_TOKEN` | empty | Refresh token grant (OAUTH mode) |
| `UPSTOX_EXTENDED_TOKEN` | empty | 1-year read-only extended token (EXTENDED mode) |
| `UPSTOX_ANALYTICS_TOKEN` | empty | 1-year read-only analytics token |
| `UPSTOX_REDIRECT_URI` | `http://localhost:18080` | OAuth redirect URI |
| `UPSTOX_AUTH_MODE` | `STATIC` | `STATIC` / `OAUTH` / `INTERACTIVE` / `EXTENDED` / `WEBHOOK` |
| `UPSTOX_ENVIRONMENT` | `LIVE` | `LIVE` / `SANDBOX` |
| `UPSTOX_TOKEN_STATE_FILE` | empty | JSON state file (default `.upstox-token.json`) |
| `UPSTOX_REFRESH_BUFFER_MINUTES` | `30` | Proactive refresh before expiry |
| `UPSTOX_INSTRUMENT_CACHE` | `.cache/upstox/complete.json.gz` | Instrument master file |
| `UPSTOX_ALGO_NAME` | empty | Value for the `X-Algo-Name` header (SEBI-registered algos) |
| `UPSTOX_STATIC_IP` | empty | Current static IP (read-only convenience) |
| `UPSTOX_ALLOW_LIVE_ORDERS` | `true` | Safety guard for live orders |
| `UPSTOX_WS_PLUS_PLAN` | `false` | Increase WS connection cap to 5 |
| `UPSTOX_MARKET_PROTECTION_DEFAULT` | `-1` | Default market_protection (V3 place) |
| `UPSTOX_SLICE_DEFAULT` | `false` | Default server-side slice |
| `UPSTOX_REST_BASE_URL` | empty | Override the regular base URL |
| `UPSTOX_SANDBOX_REST_BASE_URL` | empty | Override the sandbox base URL |

## Auth flow (interactive PKCE)

```bash
UPSTOX_CLIENT_ID=xxx \
UPSTOX_CLIENT_SECRET=yyy \
UPSTOX_REDIRECT_URI=http://localhost:18080/cb \
python -m brokers.upstox.auth.login --env-file .env.local.sandbox
```

The script will:
1. Generate a PKCE pair.
2. Start the aiohttp redirect server on `127.0.0.1:18080`.
3. Print the authorization URL (and open the browser).
4. Capture the code from the callback.
5. Exchange code for `access_token` + `refresh_token`.
6. Persist to `UPSTOX_TOKEN_STATE_FILE` (default `.upstox-token.json`).
7. Optionally print the tokens for `.env` authoring.

Subsequent restarts auto-bootstrap from the persisted JSON state.

## Token lifecycle

`UpstoxTokenManager` supports:
* **STATIC** — fixed access token; no refresh, no 3:30 AM IST fallback.
* **OAUTH** — bootstrap from configured `access_token` + `refresh_token`, then proactively refresh within `refresh_buffer_minutes` of expiry.
* **EXTENDED** — 1-year read-only token; no refresh.
* **ANALYTICS** — 1-year read-only token; no refresh.
* **WEBHOOK** — daily token delivered via Upstox's notifier URL; use
  `UpstoxTokenWebhookController` to receive.

Access tokens expire daily at 3:30 AM IST. The manager falls back to
`UpstoxTokenExpiry.next_expiry_epoch_ms()` when the JWT/profile API doesn't
provide a concrete expiry.

## WebSocket V3 (market data feed)

The V3 server pushes **Protobuf-encoded binary frames** (4 modes:
`ltpc`, `option_greeks`, `full`, `full_d30` — `full_d30` is Plus-only).

Hard limits:
* 2 connections per user (5 for Plus)
* LTPC: 5000 individual / 2000 combined
* Option Greeks: 3000 individual / 2000 combined
* Full: 2000 individual / 1500 combined
* Full D30: 50 individual / 1500 combined (Plus)

Enforced by `UpstoxV3SubscriptionManager` which raises
`SubscriptionLimitExceeded` on overflow.

```python
from brokers.upstox import UpstoxBroker
b = UpstoxBroker()
b.market_data_websocket.subscribe(["NSE_EQ|INE001A01023"], mode="ltpc")

def on_tick(event_type, payload):
    if event_type == "tick":
        print(payload)

b.market_data_websocket.add_listener(on_tick)
```

Auto-reconnect uses exponential backoff + jitter, capped at
`UPSTOX_WS_PLUS_PLAN`-tunable retries.

## Portfolio stream (V2 JSON)

```python
from brokers.upstox import UpstoxBroker
b = UpstoxBroker()
async with b.market_data_websocket:
    pass  # portfolio stream opened via feed_authorizer.authorize_portfolio_stream()
```

Updates are normalised to `OrderUpdateEvent`, `PositionUpdateEvent`,
`HoldingUpdateEvent`, `GTTUpdateEvent` domain events.

## Capabilities registered

25 capabilities are registered on the `UpstoxBroker` facade (see
[spec.md](../../.trae/specs/plan-upstox-adapter/spec.md) for the full list):

`MARKET_DATA`, `DEPTH`, `ORDER_COMMAND`, `ORDER_QUERY`, `PORTFOLIO`,
`OPTIONS_CHAIN`, `FUTURES`, `HISTORICAL_DATA`, `MARGIN`, `INSTRUMENTS`,
`MARKET_STATUS`, `GTT_ORDER`, `SLICE_ORDER`, `ORDER_SLICING`,
`COVER_ORDER`, `ALERTS`, `WEBSOCKET`, `IDEMPOTENCY`, `NEWS`,
`MARKET_INTELLIGENCE`, `KILL_SWITCH`, `STATIC_IP`, `PORTFOLIO_STREAM`,
`WEBHOOKS`, `OPTION_GREEKS`.

## Testing

```bash
# Unit tests
pytest brokers/upstox/tests/unit/ -q
# 150 passed

# Conformance (recorded Trade_J fixtures)
pytest brokers/upstox/tests/conformance/ -q

# Sandbox integration (requires real Upstox sandbox app)
UPSTOX_INTEGRATION=1 \
UPSTOX_ALLOW_LIVE_ORDERS=true \
pytest brokers/upstox/tests/integration/ -m upstox_sandbox

# Live read-only
UPSTOX_INTEGRATION=1 \
pytest brokers/upstox/tests/integration/ -m upstox_live_readonly
```

## Files

| Directory | Contents |
|---|---|
| `auth/` | PKCE, OAuth, holders, token manager, redirect server, login |
| `instruments/` | Definition, loader, resolver, segment mapper, search |
| `mappers/` | Domain mapper (OrderRequest ↔ Upstox payload), price parser |
| `orders/` | Order + GTT REST clients, command/query/GTT/slice/cover/alert adapters |
| `market_data/` | V2/V3 clients, options, portfolio, margin, status, futures, expired |
| `market_intelligence/` | PCR, MaxPain, OI, FII/DII, Smartlist client + snapshot aggregator |
| `websocket/` | Protobuf stub, decoder, subscription manager, auto-reconnect, feed authorizer, market data V3 multiplexer, portfolio stream |
| `reconciliation/` | Drift detection + repair service |
| `news/`, `fundamentals/`, `ipo/`, `mutual_funds/`, `payments/`, `static_ip/`, `kill_switch/` | Per-domain clients + adapters |
| `tests/conformance/fixtures/` | Recorded JSON fixtures from Trade_J |
