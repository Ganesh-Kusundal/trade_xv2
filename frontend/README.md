# TradeXV2 — Frontend (v3.0)

Bloomberg-style minimal frontend. Single page, canvas-rendered candlestick
chart, symbol search, replay controls. Backend optional — the UI is fully
functional in mock mode.

## Stack

- Vite 6 + React 18 + TypeScript
- Tailwind CSS 3 (custom Bloomberg-ish dark theme)
- Zustand (state) + Lucide icons
- **No** charting library — candles, MA lines, crosshair, volume pane are
  all drawn directly on a single HTML5 canvas.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build → dist/
npm run typecheck
```

## Layout

```
src/
├── main.tsx               # entry
├── App.tsx                # top-level layout
├── types/                 # domain types (matches BACKEND_API_SPEC.md)
├── data/                  # symbol universe + mock candle/quote generators
├── api/client.ts          # FastAPI client w/ transparent mock fallback
├── store/app.ts           # zustand store (active symbol, tf, watchlist, replay)
├── hooks/                 # useCandles, useQuote
├── lib/                   # cn, formatIN, formatCompact, pnlColor, ...
├── components/
│   ├── TopBar.tsx         # brand + symbol search + tf tabs + quote HUD + REPLAY
│   ├── Sidebar.tsx        # watchlist
│   ├── ChartPanel.tsx     # main chart container
│   ├── CandlestickChart.tsx
│   ├── ReplayPanel.tsx    # play / pause / step / seek / speed / scrub
│   └── SymbolSearch.tsx   # type-ahead dropdown (⌘K)
└── styles/globals.css     # tokens + tailwind layers
```

## Backend integration

The frontend expects a FastAPI server on `http://localhost:8000` matching
[`BACKEND_API_SPEC.md`](../BACKEND_API_SPEC.md). Vite is configured with a
proxy:

- `/api/*` → `http://localhost:8000`
- `/ws/*`  → `ws://localhost:8000`

If the backend is unreachable, all endpoints silently fall back to the
in-memory mock generators in `src/data/mockMarket.ts` so the UI is always
functional. A "LIVE" / "MOCK" badge in the top bar shows the current
state.

## Features in this build

1. **Symbol search** — type-ahead across 100+ NSE symbols. Keyboard:
   `↑↓` to navigate, `↵` to select, `Esc` to close. `⌘K` / `Ctrl+K` to open
   from anywhere.
2. **Timeframes** — `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1D`, `1W`.
3. **Candlestick chart** — 200 bars per fetch, EMA 9/20/50 overlays, volume
   sub-pane, crosshair with OHLC tooltip, last-price tag for live ticks.
4. **Live tick** — once a second, the last bar is updated with the latest
   LTP. Pauses automatically during replay.
5. **Watchlist** — persisted in `localStorage`. Click any row to switch
   the active symbol. The hover ✕ removes it.
6. **Replay** — date picker, transport (play / pause / step ±1m / seek),
   scrub bar, speed (1×/4×/16×/64×/128×). Drives a `ReplaySession` from
   the backend; falls back to a local timer-driven emitter using
   `generateCandles` over the trading day.
7. **Backend auto-detect** — `/api/v1/health` is probed on first request
   and re-probed every 30 s if previously down. UI shows MOCK or
   LIVE · `<latency>ms` accordingly.

## What is **not** in this build

Per the spec in `BACKEND_API_SPEC.md`, the following are deliberately
deferred: order placement, OMS, portfolio/positions/holdings, risk
dashboard, strategy runner, alerts feed, multi-pane workspace layouts.
Each can be added incrementally once the candlestick + symbol + replay
core is stable and tested.
