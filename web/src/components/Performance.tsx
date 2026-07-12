import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { fmtInt, fmtNum } from "../utils/format";
import type { BacktestResultResponse } from "../types";

/**
 * Performance widget (mirrors the TUI `PerformanceConsoleWidget`). The TUI
 * runs a local load-tester; the web surface instead exposes the backend
 * `/health/metrics` (HTTP throughput/latency, caches) plus an on-demand
 * backtest run to demonstrate strategy research performance.
 */
export function Performance() {
  const api = useApi();
  const metrics = useAsync<Record<string, unknown>>(() => api.metrics(), []);

  const [symbol, setSymbol] = useState("RELIANCE");
  const [strategy, setStrategy] = useState("momentum");
  const [years, setYears] = useState(1);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BacktestResultResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.runBacktest({
        symbol: symbol.toUpperCase(),
        strategy,
        years,
        timeframe: "1d",
        initial_capital: 100_000,
      });
      setResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const m = result?.metrics;

  return (
    <section className="panel" aria-label="Performance">
      <h2>Performance</h2>

      <h3>Backtest (research mode)</h3>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <input aria-label="Backtest symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        <select aria-label="Strategy" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
          <option value="momentum">momentum</option>
          <option value="breakout">breakout</option>
        </select>
        <input
          aria-label="Years"
          type="number"
          min={1}
          max={10}
          value={years}
          onChange={(e) => setYears(Number(e.target.value))}
        />
        <button type="submit" disabled={busy} data-testid="run-backtest">
          Run
        </button>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {m && (
        <dl className="kv" data-testid="backtest-metrics">
          <div>
            <dt>Total Return</dt>
            <dd>{fmtNum(m.total_return_pct)}%</dd>
          </div>
          <div>
            <dt>Sharpe</dt>
            <dd>{fmtNum(m.sharpe_ratio)}</dd>
          </div>
          <div>
            <dt>Max Drawdown</dt>
            <dd>{fmtNum(m.max_drawdown_pct)}%</dd>
          </div>
          <div>
            <dt>Win Rate</dt>
            <dd>{fmtNum(m.win_rate)}%</dd>
          </div>
          <div>
            <dt>Trades</dt>
            <dd>{fmtInt(m.total_trades)}</dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{result?.research_mode}</dd>
          </div>
        </dl>
      )}

      <h3>API Metrics</h3>
      {metrics.loading && <p className="muted">Loading metrics…</p>}
      {metrics.data && (
        <pre data-testid="api-metrics">{JSON.stringify(metrics.data, null, 2)}</pre>
      )}
    </section>
  );
}
