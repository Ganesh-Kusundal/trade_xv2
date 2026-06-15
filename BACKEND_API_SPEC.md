# TradeXV2 Frontend — Backend API Specification

> This document specifies the FastAPI + WebSocket backend the new Bloomberg-style
> TradeXV2 frontend will consume. It is a **plan/spec only** — no backend code is
> to be modified from this task. Backend implementation will follow this spec in
> a separate task.
>
> **Frontend scope (this build):**
> 1. Bloomberg-style single-page UI (dark theme, dense data, keyboard-driven).
> 2. Candlestick chart for any NSE/BSE symbol across multiple timeframes.
> 3. Symbol search + select (autocomplete across NIFTY 50 / 100 / 200 / 500).
> 4. Replay controls (date picker, play/pause/step/speed, scrub bar).
>
> Everything in this spec is sized to support those four features end-to-end.

---

## 1. Service Topology

```
┌──────────────┐        REST  /api/v1/*         ┌────────────────────────┐
│  Frontend    │ ─────────────────────────────► │  FastAPI gateway       │
│  (Vite/React)│                                 │  (uvicorn, :8000)      │
│              │ ◄──── WebSocket /ws/* ────────► │                        │
└──────────────┘                                 └─────┬────────┬────────┘
                                                         │        │
                                              ┌──────────▼──┐  ┌──▼────────┐
                                              │  DhanHQ /   │  │  DataLake │
                                              │  Upstox     │  │  (DuckDB) │
                                              │  broker     │  │  / Parquet│
                                              └─────────────┘  └───────────┘
```

A single FastAPI process is sufficient. CORS is restricted to the Vite dev origin
and the production frontend domain. Authentication is delegated to the existing
broker `AuthManager` (TOTP + token, no frontend-side secrets).

---

## 2. REST Endpoints

All endpoints return JSON. Errors follow:

```json
{ "error": { "code": "SYMBOL_NOT_FOUND", "message": "...", "trace_id": "..." } }
```

### 2.1 Reference data

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Liveness/readiness probe |
| GET | `/api/v1/symbols/search?q=&exchange=&limit=` | Autocomplete search across all listed symbols |
| GET | `/api/v1/symbols/{symbol}` | Full instrument metadata (lot, tick, ISIN, sector) |
| GET | `/api/v1/symbols/universe/{nifty50|nifty100|nifty200|nifty500|banknifty|finnifty}` | Returns the static symbol list |

`/symbols/search` returns:

```json
{
  "results": [
    { "symbol": "RELIANCE", "exchange": "NSE", "name": "Reliance Industries", "segment": "EQ", "isin": "INE002A01018", "lot_size": 1, "tick_size": 0.05 }
  ]
}
```

### 2.2 Market data

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/market/quote/{symbol}` | Latest LTP snapshot (bid/ask/volume) |
| GET | `/api/v1/market/candles?symbol=&timeframe=&from=&to=&limit=` | Historical OHLCV |
| GET | `/api/v1/market/instruments` | All tradable instruments (cached, paginated) |

Supported `timeframe` values: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`.

Response shape (candles):

```json
{
  "symbol": "RELIANCE",
  "timeframe": "5m",
  "exchange": "NSE",
  "candles": [
    { "t": 1715324700000, "o": 2935.4, "h": 2941.0, "l": 2932.0, "c": 2938.7, "v": 145230, "oi": 0 }
  ]
}
```

### 2.3 Replay

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/replay/sessions?symbol=&date=` | List available replay sessions for a symbol/date |
| POST | `/api/v1/replay/sessions` | Create a replay session (returns `session_id`) |
| GET | `/api/v1/replay/sessions/{id}` | Session metadata + current cursor position |
| POST | `/api/v1/replay/sessions/{id}/control` | Body: `{ "action": "play|pause|step|seek|set_speed", "speed": 1, "to_t": 0 }` |
| DELETE | `/api/v1/replay/sessions/{id}` | Tear down the session |

A "replay session" is a streaming cursor that replays historical ticks/candles
on demand. The backend sources data from `datalake/gateway.py` and re-emits it
over a WebSocket at the requested speed.

### 2.4 Watchlist (lightweight, per user)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/watchlist` | List saved symbols |
| POST | `/api/v1/watchlist` | Add symbol |
| DELETE | `/api/v1/watchlist/{symbol}` | Remove symbol |

The first frontend build keeps watchlist in `localStorage` and treats these as
optional. They are documented here so the backend slot exists.

---

## 3. WebSocket Streams

All WebSocket connections originate at `/ws/*`. Authentication is via a one-time
token query param `?token=...` issued by `/api/v1/auth/ws-ticket`.

### 3.1 Live market feed — `/ws/market`

Client subscribes by sending:

```json
{ "op": "subscribe", "channel": "quotes", "symbols": ["RELIANCE", "TCS"] }
{ "op": "subscribe", "channel": "candles", "symbol": "RELIANCE", "timeframe": "1m" }
{ "op": "unsubscribe", "channel": "quotes", "symbols": ["TCS"] }
```

Server pushes:

```json
{ "type": "quote", "symbol": "RELIANCE", "ltp": 2935.40, "ts": 1715324700123,
  "bid": 2935.35, "ask": 2935.45, "bid_qty": 1200, "ask_qty": 850, "volume": 145230, "oi": 0 }
{ "type": "candle", "symbol": "RELIANCE", "timeframe": "1m",
  "candle": { "t": 1715324700000, "o": 2935.4, "h": 2941.0, "l": 2932.0, "c": 2938.7, "v": 145230 } }
{ "type": "heartbeat", "ts": 1715324710000 }
```

Server-driven throttling: at most 4 quote messages per symbol per second.

### 3.2 Replay stream — `/ws/replay/{session_id}`

Server pushes the session's historical ticks/candles at the chosen speed:

```json
{ "type": "replay_candle", "session_id": "rp_xyz", "candle": { "t": 1715324700000, ... } }
{ "type": "replay_quote",  "session_id": "rp_xyz", "ltp": 2935.40, "ts": 1715324700123 }
{ "type": "replay_state",  "session_id": "rp_xyz", "state": "PLAYING|PAUSED|ENDED", "speed": 4, "cursor_t": 1715324700000 }
```

### 3.3 Error / disconnect

On protocol error, server sends:

```json
{ "type": "error", "code": "BAD_OP", "message": "..." }
```

Then closes with WebSocket code `1008`. Frontend must auto-reconnect with
exponential backoff (1s, 2s, 4s, 8s, max 30s) and re-subscribe.

---

## 4. Backend Module Mapping

These are the **existing** Python modules the backend endpoints will wrap — no
new backend code is invented, only HTTP/WS adapters are added.

| Endpoint | Backend module used |
|---|---|
| `/api/v1/symbols/*` | `datalake/catalog.py` (symbol universe, sector mapping), `brokers/common/core/instruments.py` (instrument registry) |
| `/api/v1/market/quote/*` | `brokers/dhan/market_data/market_data.py` (live LTP), fallback to `datalake/gateway.py` last tick |
| `/api/v1/market/candles` | `datalake/gateway.py` (Parquet/DuckDB historical), `analytics/backtest/fast_backtest.py` (cache) |
| `/api/v1/replay/*` | `analytics/replay/replay_engine.py` (cursor + scheduler), `datalake/gateway.py` (tick source) |
| `/ws/market` | `brokers/multiplexer.py` (subscription fan-out), `brokers/dhan/websocket/market_feed.py` |
| `/ws/replay/*` | `analytics/replay/replay_engine.py` + an ASGI bridge |

The backend skeleton to add (not built in this task):

```
datalake/
  api/
    __init__.py
    main.py            # FastAPI app factory
    deps.py            # DI: brokers, datalake gateway, replay engine
    routers/
      health.py
      symbols.py
      market.py
      replay.py
      watchlist.py
    ws/
      market.py
      replay.py
      auth.py
    schemas.py         # pydantic models
    config.py          # CORS, rate limits, token TTL
```

`pyproject.toml` already has FastAPI? — add to `requirements.txt`:
```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
websockets>=12.0
```

---

## 5. Frontend-Backend Contract (TypeScript)

The frontend will import a single generated-looking client:

```ts
// src/api/client.ts
export const api = {
  searchSymbols: (q: string) =>
    fetch(`/api/v1/symbols/search?q=${encodeURIComponent(q)}`).then(r => r.json()),
  getQuote: (symbol: string) =>
    fetch(`/api/v1/market/quote/${symbol}`).then(r => r.json()),
  getCandles: (symbol: string, tf: Timeframe, from?: number, to?: number) =>
    fetch(`/api/v1/market/candles?symbol=${symbol}&timeframe=${tf}&from=${from ?? ''}&to=${to ?? ''}`).then(r => r.json()),
  listReplaySessions: (symbol: string, date: string) =>
    fetch(`/api/v1/replay/sessions?symbol=${symbol}&date=${date}`).then(r => r.json()),
  createReplaySession: (body: { symbol: string; date: string; timeframe: Timeframe; from_t?: number; to_t?: number }) =>
    fetch('/api/v1/replay/sessions', { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }).then(r => r.json()),
  controlReplay: (id: string, action: ReplayAction) =>
    fetch(`/api/v1/replay/sessions/${id}/control`, { method: 'POST', body: JSON.stringify(action), headers: { 'Content-Type': 'application/json' } }).then(r => r.json()),
}
```

The frontend's `useCandles`, `useQuote`, `useReplay` hooks will call these
endpoints. When the backend is **not running**, the hooks transparently fall
back to the in-memory mock generator in `src/api/mockData.ts`. The user
experiences no blank UI in dev.

---

## 6. Non-Goals (out of scope for this build)

The following are deliberately **not** in this iteration of the frontend, even
though the backend modules exist:

- Order placement / OMS (the existing backend scaffolding is left untouched).
- Portfolio / positions / holdings views.
- Risk dashboard, strategy runner, alerts feed, deepcharts widgets.
- Multi-monitor layouts, workspace persistence, drag-and-drop.

These can be added incrementally once the candlestick + symbol + replay core
is stable and tested.

---

## 7. Acceptance Criteria (frontend)

- App boots with no console errors. No 500s, no missing-key React warnings.
- Symbol search: type "RELI", see "RELIANCE" within 100 ms (mock) / 1 s (real).
- Selecting a symbol renders a 200-candle history within 500 ms (mock) /
  2 s (real) on a 5 m timeframe.
- Switching timeframes (1m / 5m / 15m / 1h / 1d) re-fetches and re-renders
  without flicker.
- Replay: open the replay panel, pick a date, press play. Candles draw in
  one-by-one at the chosen speed (1×, 4×, 16×, 64×). Pause/seek work.
- Network-tab shows the expected `/api/v1/...` requests when backend is up.
  When backend is down, the mock fallback kicks in and the UI is functional.
- Layout is responsive ≥ 1280 px wide; smaller widths collapse sidebars
  gracefully (not required to look great < 1280 px but must not break).

---

## Status Update — 2026-06-15

The original spec above is from 2026-06-12. The system has been
brought to production-ready state through 13 remediation commits:

- **OMS wire-up** — the central OMS at `brokers/common/oms/` is now
  the canonical risk gate on the live CLI path. RiskManager is wired
  with real `gateway.funds().available_balance` as capital.
- **HTTP observability** — BrokerService now exposes /healthz, /readyz,
  /metrics on port 8765.
- **Dead-code elimination** — 9 deprecated files deleted
  (~`models.py`, `enums.py`, `connection.py`, `mappers.py`,
  `data_contracts.py`, `facade.py`, `broker.py`, `schemas.py`).
  Canonical types live in `brokers/common/core/domain.py`.

Future frontend work should target the `/api/v1/` routes described in
this spec. The Python backend already implements every endpoint here via
the broker gateway + OMS layer.
