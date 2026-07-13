import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { fmtNum, fmtPct } from "../utils/format";

/**
 * Options analytics widget: option chain, PCR, max pain, IV surface, and a
 * CE/PE volume-profile bar chart for an underlying. Mirrors the backend
 * `/options/*` endpoints (data is sourced from historical OHLCV parquet, so
 * bid/ask are not available here — see backend note on the chain endpoint).
 */
export function Options() {
  const api = useApi();
  const [underlying, setUnderlying] = useState("NIFTY");
  const [submitted, setSubmitted] = useState("NIFTY");
  const [strikeRange, setStrikeRange] = useState(10);

  const chain = useAsync<ReturnType<typeof api.optionChain>>(
    () => api.optionChain(submitted, { strike_range: strikeRange }),
    [submitted, strikeRange],
  );
  const pcr = useAsync<ReturnType<typeof api.pcr>>(() => api.pcr(submitted), [submitted]);
  const maxPain = useAsync<ReturnType<typeof api.maxPain>>(() => api.maxPain(submitted), [submitted]);
  const iv = useAsync<ReturnType<typeof api.ivSurface>>(() => api.ivSurface(submitted), [submitted]);
  const vol = useAsync<ReturnType<typeof api.volumeProfile>>(
    () => api.volumeProfile(submitted),
    [submitted],
  );

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(underlying.trim().toUpperCase());
  }

  return (
    <section className="panel" aria-label="Options analytics">
      <h2>Options Analytics</h2>

      <form className="row" onSubmit={handleSubmit}>
        <input
          aria-label="Underlying"
          value={underlying}
          onChange={(e) => setUnderlying(e.target.value)}
          placeholder="e.g. NIFTY"
          data-testid="options-underlying"
        />
        <label className="muted">
          Strikes
          <input
            type="number"
            min={1}
            max={50}
            value={strikeRange}
            aria-label="Strike range"
            onChange={(e) => setStrikeRange(Number(e.target.value))}
            style={{ width: "5rem", marginLeft: "0.4rem" }}
          />
        </label>
        <button type="submit">Analyze</button>
      </form>

      {/* Summary tiles */}
      <div className="kv" data-testid="options-summary">
        <SummaryTile
          label="Spot"
          state={maxPain}
          render={(d) => fmtNum(d.spot)}
        />
        <SummaryTile
          label="Max Pain"
          state={maxPain}
          render={(d) => fmtNum(d.max_pain_strike)}
        />
        <SummaryTile
          label="PCR (OI)"
          state={pcr}
          render={(d) => fmtNum(d.pcr_oi, 3)}
        />
        <SummaryTile
          label="PCR (Vol)"
          state={pcr}
          render={(d) => fmtNum(d.pcr_volume, 3)}
        />
        <SummaryTile
          label="ATM IV"
          state={iv}
          render={(d) => fmtPct(d.atm_iv * 100)}
        />
        <SummaryTile
          label="IV Skew"
          state={iv}
          render={(d) => fmtNum(d.iv_skew, 3)}
        />
      </div>

      {/* Volume profile bar chart */}
      <h3>Volume Profile (CE vs PE)</h3>
      <VolumeProfileChart
        state={vol}
        spot={maxPain.data?.spot}
      />

      {/* Option chain table */}
      <h3>Option Chain</h3>
      {chain.loading && <p className="muted">Loading chain…</p>}
      {chain.error && (
        <p className="error" role="alert">
          Chain failed: {chain.error.message}
        </p>
      )}
      {chain.data && (
        <table data-testid="options-chain">
          <thead>
            <tr>
              <th>Strike</th>
              <th>Type</th>
              <th>LTP</th>
              <th>Volume</th>
              <th>OI</th>
            </tr>
          </thead>
          <tbody>
            {chain.data.contracts.map((c) => (
              <tr key={`${c.symbol}-${c.option_type}`}>
                <td>{fmtNum(c.strike, 1)}</td>
                <td className={c.option_type === "CE" ? "pnl-pos" : "pnl-neg"}>{c.option_type}</td>
                <td>{fmtNum(c.ltp)}</td>
                <td>{fmtNum(c.volume, 0)}</td>
                <td>{fmtNum(c.oi, 0)}</td>
              </tr>
            ))}
            {chain.data.contracts.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No contracts found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </section>
  );
}

type AsyncState<T> = { data?: T; error?: Error; loading: boolean };

function SummaryTile<T>({
  label,
  state,
  render,
}: {
  label: string;
  state: AsyncState<T>;
  render: (d: T) => string;
}) {
  let value = "—";
  if (state.error) value = "err";
  else if (state.data !== undefined) value = render(state.data);
  return (
    <div>
      <dt>{label}</dt>
      <dd data-testid={`tile-${label.replace(/\s+/g, "-").toLowerCase()}`}>{value}</dd>
    </div>
  );
}

function VolumeProfileChart({
  state,
  spot,
}: {
  state: AsyncState<{ profile: { strike: number; ce_volume: number; pe_volume: number; total_volume: number }[] }>;
  spot?: number;
}) {
  if (state.loading) return <p className="muted">Loading volume profile…</p>;
  if (state.error)
    return (
      <p className="error" role="alert">
        Volume profile failed: {state.error.message}
      </p>
    );
  const profile = state.data?.profile ?? [];
  if (profile.length === 0) return <p className="muted">No volume data</p>;

  // ponytail: fixed viewBox, simple stacked horizontal bars. No chart lib.
  const W = 100;
  const maxTotal = Math.max(...profile.map((p) => p.total_volume), 1);
  const rowH = 3.2;
  const H = profile.length * rowH + 4;
  const spotY =
    spot !== undefined
      ? (() => {
          const strikes = profile.map((p) => p.strike);
          const lo = Math.min(...strikes);
          const hi = Math.max(...strikes);
          if (hi === lo) return null;
          const idx = (spot - lo) / (hi - lo);
          return `${Math.max(2, Math.min(H - 2, idx * H))}`;
        })()
      : null;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      role="img"
      aria-label="CE/PE volume profile by strike"
      data-testid="volume-profile-chart"
      preserveAspectRatio="none"
      style={{ display: "block", maxHeight: "320px" }}
    >
      {profile.map((p, i) => {
        const y = i * rowH + 2;
        const ceW = (p.ce_volume / maxTotal) * (W / 2);
        const peW = (p.pe_volume / maxTotal) * (W / 2);
        return (
          <g key={p.strike}>
            <rect x={0} y={y} width={ceW} height={rowH - 0.4} fill="#3fb950" />
            <rect x={W / 2} y={y} width={peW} height={rowH - 0.4} fill="#f85149" />
            <text x={W / 2 + 1} y={y + rowH - 1} fill="#8b949e" fontSize={2.2}>
              {p.strike}
            </text>
          </g>
        );
      })}
      {spotY !== null && (
        <line x1={0} y1={spotY} x2={W} y2={spotY} stroke="#58a6ff" strokeWidth={0.5} strokeDasharray="2 1" />
      )}
    </svg>
  );
}
