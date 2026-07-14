import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { fmtNum, fmtPct } from "../utils/format";
import { VolumeProfileLwChart } from "./charts/TradingCharts";
import type {
  IVSurfaceResponse,
  MaxPainResponse,
  OptionChainResponse,
  PCRResponse,
  VolumeProfileResponse,
} from "../types";

/**
 * Options analytics: chain, PCR, max pain, IV, CE/PE volume via Lightweight Charts.
 */
export function Options() {
  const api = useApi();
  const [underlying, setUnderlying] = useState("NIFTY");
  const [submitted, setSubmitted] = useState("NIFTY");
  const [strikeRange, setStrikeRange] = useState(10);

  const chain = useAsync<OptionChainResponse>(
    () => api.optionChain(submitted, { strike_range: strikeRange }),
    [submitted, strikeRange],
  );
  const pcr = useAsync<PCRResponse>(() => api.pcr(submitted), [submitted]);
  const maxPain = useAsync<MaxPainResponse>(() => api.maxPain(submitted), [submitted]);
  const iv = useAsync<IVSurfaceResponse>(() => api.ivSurface(submitted), [submitted]);
  const vol = useAsync<VolumeProfileResponse>(
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

      <div className="kv" data-testid="options-summary">
        <SummaryTile label="Spot" state={maxPain} render={(d) => fmtNum(d.spot)} />
        <SummaryTile label="Max Pain" state={maxPain} render={(d) => fmtNum(d.max_pain_strike)} />
        <SummaryTile label="PCR (OI)" state={pcr} render={(d) => fmtNum(d.pcr_oi, 3)} />
        <SummaryTile label="PCR (Vol)" state={pcr} render={(d) => fmtNum(d.pcr_volume, 3)} />
        <SummaryTile label="ATM IV" state={iv} render={(d) => fmtPct(d.atm_iv * 100)} />
        <SummaryTile label="IV Skew" state={iv} render={(d) => fmtNum(d.iv_skew, 3)} />
      </div>

      <h3>Volume Profile (CE vs PE)</h3>
      <VolumeProfileSection state={vol} />

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
            {chain.data.contracts.map((c, i) => {
              const isCall = c.option_type.toUpperCase().startsWith("C");
              return (
                <tr key={`${c.symbol}-${c.expiry}-${c.strike}-${c.option_type}-${i}`}>
                  <td>{fmtNum(c.strike, 1)}</td>
                  <td className={isCall ? "pnl-pos" : "pnl-neg"}>{isCall ? "CE" : "PE"}</td>
                  <td>{fmtNum(c.ltp)}</td>
                  <td>{fmtNum(c.volume, 0)}</td>
                  <td>{fmtNum(c.oi, 0)}</td>
                </tr>
              );
            })}
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
      <dd
        data-testid={`tile-${label
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/-+$/, "")}`}
      >
        {value}
      </dd>
    </div>
  );
}

function VolumeProfileSection({
  state,
}: {
  state: AsyncState<{
    profile: { strike: number; ce_volume: number; pe_volume: number; total_volume: number }[];
  }>;
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
  return <VolumeProfileLwChart profile={profile} />;
}
