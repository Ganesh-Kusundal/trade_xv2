import { useMemo, useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { CandleStickChart } from "./charts/TradingCharts";
import type { CandlesResponse } from "../types";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d"] as const;

/**
 * Historical candles: lake `/market/candles` + TradingView Lightweight Charts.
 */
export function Candles() {
  const api = useApi();
  const [symbol, setSymbol] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>("1d");
  const [submitted, setSubmitted] = useState<{ symbol: string; timeframe: string }>({
    symbol: "NIFTY",
    timeframe: "1d",
  });

  const state = useAsync<CandlesResponse>(
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
          <CandleStickChart candles={candles} />
        </>
      )}
    </section>
  );
}
