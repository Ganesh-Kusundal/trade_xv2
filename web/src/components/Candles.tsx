import { useMemo, useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { fmtNum } from "../utils/format";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d"] as const;

/**
 * Historical candles widget: fetch OHLCV from the data lake (`/market/candles`)
 * and render a candlestick chart as inline SVG. No chart library — keeps the
 * dependency surface to React only (per web/ conventions).
 */
export function Candles() {
  const api = useApi();
  const [symbol, setSymbol] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>("1d");
  const [submitted, setSubmitted] = useState<{ symbol: string; timeframe: string }>({
    symbol: "NIFTY",
    timeframe: "1d",
  });

  const state = useAsync<ReturnType<typeof api.candles>>(
    () => api.candles({ symbol: submitted.symbol, timeframe: submitted.timeframe, limit: 200 }),
    [submitted.symbol, submitted.timeframe],
  );

  const candles = useMemo(() => state.data?.candles ?? [], [state.data]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted({ symbol: symbol.trim().toUpperCase(), timeframe });
  }

  return (
    <section className="panel" aria-label="Historical candles">
      <h2>Historical Candles</h2>

      <form className="row" onSubmit={handleSubmit}>
        <input
          aria-label="Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="e.g. NIFTY"
          data-testid="candles-symbol"
        />
        <select
          aria-label="Timeframe"
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value as (typeof TIMEFRAMES)[number])}
        >
          {TIMEFRAMES.map((tf) => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </select>
        <button type="submit">Load</button>
      </form>

      {state.loading && <p className="muted">Loading candles…</p>}
      {state.error && (
        <p className="error" role="alert">
          Candle fetch failed: {state.error.message}
        </p>
      )}

      {candles.length > 0 && (
        <>
          <p className="muted" data-testid="candles-count">
            {candles.length} candles · {submitted.timeframe}
          </p>
          <CandleChart candles={candles} />
        </>
      )}
    </section>
  );
}

function CandleChart({ candles }: { candles: { t: number; o: number; h: number; l: number; c: number; v: number }[] }) {
  // ponytail: fixed viewBox; simplistic linear scaling. Suitable for a few
  // hundred candles; for very large series, downsample before passing in.
  const W = 100;
  const H = 100;
  const pad = 4;
  const lows = candles.map((c) => c.l);
  const highs = candles.map((c) => c.h);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const range = max - min || 1;

  const step = (W - pad * 2) / candles.length;
  const bodyW = Math.max(0.6, step * 0.6);

  const y = (price: number) => pad + (1 - (price - min) / range) * (H - pad * 2);
  const x = (i: number) => pad + i * step + step / 2;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      role="img"
      aria-label="Candlestick chart"
      data-testid="candles-chart"
      preserveAspectRatio="none"
      style={{ display: "block", maxHeight: "360px" }}
    >
      {candles.map((c, i) => {
        const up = c.c >= c.o;
        const color = up ? "#3fb950" : "#f85149";
        const cx = x(i);
        return (
          <g key={c.t}>
            <line x1={cx} y1={y(c.h)} x2={cx} y2={y(c.l)} stroke={color} strokeWidth={0.4} />
            <rect
              x={cx - bodyW / 2}
              y={y(Math.max(c.o, c.c))}
              width={bodyW}
              height={Math.max(0.4, Math.abs(y(c.o) - y(c.c)))}
              fill={color}
            />
          </g>
        );
      })}
    </svg>
  );
}
