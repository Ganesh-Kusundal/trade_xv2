import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { useMarketFeed } from "../hooks/useMarketFeed";
import { fmtInt, fmtNum, pnlClass } from "../utils/format";
import type { DepthResponse, QuoteResponse } from "../types";

/**
 * Market quotes widget (mirrors the TUI `MarketConsoleWidget`): query a
 * symbol for its snapshot quote + L2 depth, then stream live LTP updates
 * over the market WebSocket when available.
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
  const liveLtp =
    feed.quotes[submitted]?.ltp ??
    (quoteState.data?.ltp as number | undefined);

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
            <dd className={pnlClass(liveLtp as number)} data-testid="quote-ltp">
              {fmtNum(liveLtp as number)}
            </dd>
          </div>
          <div>
            <dt>Bid</dt>
            <dd>{fmtNum(quoteState.data.bid ?? null)}</dd>
          </div>
          <div>
            <dt>Ask</dt>
            <dd>{fmtNum(quoteState.data.ask ?? null)}</dd>
          </div>
          <div>
            <dt>Volume</dt>
            <dd>{fmtInt(quoteState.data.volume ?? null)}</dd>
          </div>
          <div>
            <dt>Open Int.</dt>
            <dd>{fmtInt(quoteState.data.oi ?? null)}</dd>
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
              <td>{fmtInt(depthState.data?.bids[i]?.qty as number | undefined)}</td>
              <td>{fmtNum(depthState.data?.bids[i]?.price as number | undefined)}</td>
              <td>{fmtNum(depthState.data?.asks[i]?.price as number | undefined)}</td>
              <td>{fmtInt(depthState.data?.asks[i]?.qty as number | undefined)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
