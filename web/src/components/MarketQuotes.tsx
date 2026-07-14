import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { useMarketFeed } from "../hooks/useMarketFeed";
import { fmtInt, fmtNum, pnlClass } from "../utils/format";
import type { DepthResponse, QuoteResponse } from "../types";

/** Coerce lake/live quote numbers (floats or numeric strings) to number|null. */
function asNum(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * Market quotes widget (mirrors the TUI `MarketConsoleWidget`): query a
 * symbol for its snapshot quote + L2 depth, then stream live LTP updates
 * over the market WebSocket when available.
 *
 * Note: lake-backed `/market/quote` does not populate bid/ask (live-only via
 * `/live/depth`). Missing bid/ask render as "—".
 */
export function MarketQuotes() {
  const api = useApi();
  const [symbol, setSymbol] = useState("RELIANCE");
  const [submitted, setSubmitted] = useState("RELIANCE");

  const quoteState = useAsync<QuoteResponse | null>(
    () => api.quote(submitted),
    [submitted],
  );
  const depthState = useAsync<DepthResponse>(
    () => api.depth(submitted).catch(() => ({ symbol: submitted, bids: [], asks: [] })),
    [submitted],
  );

  const feed = useMarketFeed(submitted ? [submitted] : []);
  const restLtp = asNum(quoteState.data?.ltp);
  const liveLtp = asNum(feed.quotes[submitted]?.ltp) ?? restLtp;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(symbol.trim().toUpperCase());
  }

  return (
    <section className="panel" aria-label="Market quotes">
      <h2>Market Quotes</h2>

      <form className="row" onSubmit={handleSubmit}>
        <input
          aria-label="Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="e.g. RELIANCE"
          data-testid="symbol-input"
        />
        <button type="submit">Query</button>
      </form>

      <p className="muted" data-testid="ws-status">
        Live feed: {feed.status}
      </p>

      {quoteState.loading && <p className="muted">Loading quote…</p>}
      {quoteState.error && (
        <p className="error" role="alert">
          {quoteState.error.message}
        </p>
      )}

      {quoteState.data && (
        <dl className="kv">
          <div>
            <dt>Symbol</dt>
            <dd>
              {quoteState.data.symbol} ({quoteState.data.exchange})
            </dd>
          </div>
          <div>
            <dt>LTP</dt>
            <dd className={pnlClass(liveLtp)} data-testid="quote-ltp">
              {fmtNum(liveLtp)}
            </dd>
          </div>
          <div>
            <dt>Bid</dt>
            <dd data-testid="quote-bid">{fmtNum(asNum(quoteState.data.bid))}</dd>
          </div>
          <div>
            <dt>Ask</dt>
            <dd data-testid="quote-ask">{fmtNum(asNum(quoteState.data.ask))}</dd>
          </div>
          <div>
            <dt>Volume</dt>
            <dd>{fmtInt(asNum(quoteState.data.volume))}</dd>
          </div>
          <div>
            <dt>Open Int.</dt>
            <dd>{fmtInt(asNum(quoteState.data.oi))}</dd>
          </div>
        </dl>
      )}

      <h3>Market Depth (L2)</h3>
      {depthState.loading && <p className="muted">Loading depth…</p>}
      <table>
        <thead>
          <tr>
            <th>Bid Qty</th>
            <th>Bid</th>
            <th>Ask</th>
            <th>Ask Qty</th>
          </tr>
        </thead>
        <tbody>
          {depthState.data?.bids.length === 0 &&
            depthState.data?.asks.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No depth available
                </td>
              </tr>
            )}
          {Array.from({
            length: Math.max(
              depthState.data?.bids.length ?? 0,
              depthState.data?.asks.length ?? 0,
            ),
          }).map((_, i) => (
            <tr key={i}>
              <td>{fmtInt(asNum(depthState.data?.bids[i]?.qty))}</td>
              <td>{fmtNum(asNum(depthState.data?.bids[i]?.price))}</td>
              <td>{fmtNum(asNum(depthState.data?.asks[i]?.price))}</td>
              <td>{fmtInt(asNum(depthState.data?.asks[i]?.qty))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
