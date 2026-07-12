import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { fmtInt, fmtNum, fmtPct, pnlClass } from "../utils/format";
import type { PositionsResponse } from "../types";

/**
 * Open positions widget (mirrors the TUI `BrokerConsoleWidget` active
 * positions table). Reads from the OMS-backed `/portfolio/positions`.
 */
export function Positions() {
  const api = useApi();
  const state = useAsync<PositionsResponse>(() => api.positions(), []);

  return (
    <section className="panel" aria-label="Positions">
      <h2>Positions</h2>

      {state.loading && <p className="muted">Loading positions…</p>}
      {state.error && (
        <p className="error" role="alert">
          Failed to load positions: {state.error.message}
        </p>
      )}

      {state.data && (
        <>
          <p className="muted" data-testid="positions-total">
            Total P&L:{" "}
            <span className={pnlClass(state.data.total_pnl)}>
              {fmtNum(state.data.total_pnl)} ({fmtPct(state.data.total_pnl_percent)})
            </span>
          </p>

          {state.data.positions.length === 0 ? (
            <p className="muted" data-testid="positions-empty">
              No open positions
            </p>
          ) : (
            <table data-testid="positions-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg</th>
                  <th>LTP</th>
                  <th>uPnL</th>
                  <th>rPnL</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {state.data.positions.map((p) => (
                  <tr key={`${p.symbol}-${p.exchange}`}>
                    <td>{p.symbol}</td>
                    <td>{fmtInt(p.quantity)}</td>
                    <td>{fmtNum(p.average_price)}</td>
                    <td>{fmtNum(p.current_price)}</td>
                    <td className={pnlClass(p.unrealized_pnl)}>
                      {fmtNum(p.unrealized_pnl)}
                    </td>
                    <td className={pnlClass(p.realized_pnl)}>
                      {fmtNum(p.realized_pnl)}
                    </td>
                    <td className={pnlClass(p.pnl_pct)}>{fmtPct(p.pnl_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
