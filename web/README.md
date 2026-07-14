# TradeXV2 — Web Trading Terminal (Tier 3-I)

A **Vite + React + TypeScript** single-page app that is the browser face for the
TradeXV2 trading OS. It consumes the existing FastAPI backend
(`src/interface/api/`) and mirrors the feature set of the Textual TUI
(`src/interface/ui/`): broker status, market quotes, positions, orders,
diagnostics, and performance.

> The SPA consumes the FastAPI backend under `src/interface/api/`. Lake-backed
> routes resolve parquet under `data/lake/` (see API bootstrap). Contract
> regression tests live in `tests/integration/api/test_contract.py` and
> `web/src/test/contract.test.tsx`.

## Pages

| Route          | Component              | What it shows                                         |
|----------------|------------------------|-------------------------------------------------------|
| `/broker`      | `BrokerStatus`         | Broker connectivity / health                         |
| `/market`      | `MarketQuotes`         | Symbol quote + L2 depth + live LTP (WS)               |
| `/candles`     | `Candles`              | Historical OHLCV candlestick chart (`/market/candles`)|
| `/options`     | `Options`              | Chain, PCR, Max Pain, IV surface, CE/PE vol profile  |
| `/positions`   | `Positions`            | Open positions + P&L                                  |
| `/orders`      | `Orders`               | Order book (place / cancel)                           |
| `/diagnostics` | `Diagnostics`          | Service diagnostics                                   |
| `/performance` | `Performance`          | Performance metrics                                    |

> **Note on `/options` analytics:** PCR / Max-Pain / IV-Surface read DuckDB
> views (`v_pcr`, `v_max_pain`, `v_iv_surface`) in `data/lake/catalog.duckdb`.
> If those return 404/500, materialize once with
> `ViewManager(catalog_path="data/lake/catalog.duckdb").create_all()` (or
> `python -m analytics.precompute_features`). Option-chain and volume-profile
> read `data/lake/options/candles/` parquet directly (`CALL`/`PUT` normalized
> to CE/PE in the SPA).
>
> **Note on `/candles`:** equity and index candles live under
> `data/lake/equities/candles/` and `data/lake/indices/candles/`. The gateway
> resolves both (e.g. `RELIANCE`, `NIFTY`). Missing symbols still 404.
>
> **Note on `/market/quote` bid/ask:** lake quotes omit bid/ask (live-only via
> `/live/depth`). The SPA shows "—" when those fields are absent.

## Stack

- Vite 5 + React 18 + TypeScript 5 (`strict`)
- React Router 6 (shell + per-feature pages)
- Vitest + React Testing Library + jsdom (component tests)
- Playwright (e2e stub only — `e2e/smoke.spec.ts`)
- Typed `fetch` API client + a minimal WebSocket client

## Run it

### 1. Start the backend (paper broker — safe local dev)

From the repo root, run the API server. For a safe local setup **with the
paper broker** and **no auth** (so both REST-via-proxy and WebSocket work
from the browser), use:

```bash
# from repo root
TRADEX_ALLOW_AUTH_NONE=1 AUTH_MODE=none \
  python scripts/run_api_server.py
```

The server listens on `127.0.0.1:8080` and mounts routes under
`/api/v1` (see `src/interface/api/main.py`). OpenAPI docs:
`http://127.0.0.1:8080/docs`.

> **Why `AUTH_MODE=none`?** Two backend constraints block a browser SPA
> unless auth is disabled (gaps documented below): the REST API requires an
> `X-API-Key` header that the CORS allow-list omits, and the WebSocket
> authenticates via an `x-api-key` *header* which browsers cannot set.
> With `AUTH_MODE=none` both are bypassed. To instead use real keys,
> start with `API_KEY=devkey` and pass `VITE_API_KEY=devkey` to the SPA
> (the Vite dev proxy forwards the header to the backend for REST).

### 2. Install and run the SPA

```bash
cd web
cp .env.example .env      # optional; defaults work via the dev proxy
npm install
npm run dev              # http://127.0.0.1:5173
```

In dev, Vite proxies `/api` → `http://127.0.0.1:8080` and `/ws` →
the backend WebSocket, so the SPA talks same-origin and you avoid CORS
issues. Requests hit `/api/v1/...`.

### 3. Production build

```bash
npm run build      # tsc --noEmit + vite build  → dist/
npm run preview    # serve the built bundle locally
```

For a real deployment you must serve `dist/` from the backend or a static host
and configure CORS (see Backend Gaps). The SPA also accepts `VITE_API_BASE`
/ `VITE_WS_BASE` to point at an absolute backend URL.

### 4. Tests

```bash
npm test             # Vitest (components + SPA↔backend contract.test.tsx)
npm run test:e2e   # Playwright smoke (needs `npx playwright install` + running servers)
```

Backend contract suite (real parquet under `data/lake`):

```bash
.venv/bin/python -m pytest tests/integration/api/test_contract.py -q
```

## Project layout

```
web/
  src/
    types.ts            # TS domain types mirroring backend schemas
    api/
      config.ts         # env-based base URLs + API key
      client.ts         # ApiClient (typed, per-resource methods) + ApiError
      ws.ts             # WsClient (market feed, subscribe/unsubscribe/ping)
      ApiContext.tsx    # React context injecting the client
    hooks/
      useAsync.ts       # loading/error/data wrapper for fetches
      useMarketFeed.ts  # live quote subscription over WS
    components/
      Layout.tsx BrokerStatus.tsx MarketQuotes.tsx
      Positions.tsx Orders.tsx Diagnostics.tsx Performance.tsx
    test/               # fakeApi, render helper, component tests
  e2e/smoke.spec.ts  # Playwright stub
```

## Backend endpoints consumed

All under `http://127.0.0.1:8080/api/v1` (prefix `APIConfig.api_prefix`):

| Area            | Method + Path                              | Client method            |
|----------------|--------------------------------------------|-------------------------|
| Health         | `GET /health`                              | `health()`              |
| Health         | `GET /health/readyz`                      | `readiness()`           |
| Health         | `GET /health/metrics`                      | `metrics()`             |
| Market         | `GET /market/quote/{symbol}`               | `quote()`              |
| Market         | `GET /market/candles`                      | `candles()`            |
| Market         | `GET /live/depth/{symbol}`                  | `depth()`              |
| Options        | `GET /options/chain/{underlying}`          | `optionChain()`        |
| Options        | `GET /options/pcr/{underlying}`            | `pcr()`                |
| Options        | `GET /options/max-pain/{underlying}`        | `maxPain()`            |
| Options        | `GET /options/iv-surface/{underlying}`      | `ivSurface()`          |
| Options        | `GET /options/volume-profile/{underlying}` | `volumeProfile()`      |
| Portfolio      | `GET /portfolio/positions`                  | `positions()`           |
| Portfolio      | `GET /portfolio/holdings`                   | `holdings()`            |
| Portfolio      | `GET /portfolio/summary`                    | `portfolioSummary()`    |
| Orders         | `GET /orders`                              | `orders()`              |
| Orders         | `GET /orders/trades`                        | `trades()`              |
| Orders         | `POST /orders`                             | `placeOrder()`          |
| Orders         | `DELETE /orders/{id}`                       | `cancelOrder()`         |
| Scanner        | `GET /scanner/top-candidates`                | `topCandidates()`       |
| Scanner        | `POST /scanner/run`                         | `runScanner()`          |
| Backtest       | `POST /backtest/run`                        | `runBacktest()`         |
| Backtest       | `GET /backtest/results/{id}`                 | `backtestResult()`      |
| Live broker    | `GET /live/health`                          | `brokerHealth()`        |
| Live broker    | `GET /live/capabilities`                    | `brokerCapabilities()`   |

**WebSocket:** `ws://127.0.0.1:8080/ws/market`
(protocol in `src/interface/api/ws/market.py`): client sends
`{action:"subscribe",symbols:[...]}`, server streams
`{type:"quote",symbol,ltp,...}`.

## Remaining backend gaps (NOT patched — for team review)

1. **WebSocket auth via header** (`src/interface/api/ws/market.py` checks
   `websocket.headers.get("x-api-key")`; `auth.py` says "never query string").
   Browsers cannot set headers on a `WebSocket` handshake, so a browser WS
   is rejected even when a key would be valid. Worked around by running the
   backend with `AUTH_MODE=none` for local dev. Fix: accept the key as a
   query param (or cookie) for the WS upgrade, or disable WS auth in dev.

2. **No static-file serving for the SPA.** The backend does not serve the
   built `dist/` bundle. For production, either serve `dist/` from a static
   host/edge and set CORS, or add a `StaticFiles` mount in `main.py`.

### Fixed (contract audit)

- CORS `allow_headers` now includes `X-API-Key`.
- API bootstrap / gateway / options SQL point at `data/lake` (equity + index
  candles, options hive layout).
- Lake `/market/quote` documents bid/ask as live-only; `/live/quote` returns
  numeric floats; SPA coerces defensively.
