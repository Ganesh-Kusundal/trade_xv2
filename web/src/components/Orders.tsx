import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";
import { fmtNum, pnlClass } from "../utils/format";
import type {
  Exchange,
  OrderRequest,
  OrderResponse,
  OrderType,
  ProductType,
  TransactionType,
} from "../types";

/**
 * Order book widget (mirrors the TUI `OmsConsoleWidget`): list orders,
 * place a test order, and cancel open orders via the OMS. Placement routes
 * through the same server-resolved broker as the CLI (paper by default).
 */
export function Orders() {
  const api = useApi();
  const state = useAsync<{ orders: OrderResponse[]; count: number }>(
    () => api.orders({ limit: 100 }),
    [],
  );

  const [form, setForm] = useState<Omit<OrderRequest, "exchange">>({
    symbol: "RELIANCE",
    transaction_type: "BUY",
    order_type: "LIMIT",
    quantity: 1,
    price: 2500,
    product_type: "INTRADAY",
  });
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  async function place() {
    setBusy(true);
    setStatus(null);
    try {
      const req: OrderRequest = { ...form, exchange: "NSE" as Exchange };
      const res = await api.placeOrder(req);
      setStatus(`Placed ${res.order_id} (${res.status})`);
      state.reload();
    } catch (e) {
      setStatus(`Failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function cancel(orderId: string) {
    try {
      await api.cancelOrder(orderId);
      state.reload();
    } catch (e) {
      setStatus(`Cancel failed: ${(e as Error).message}`);
    }
  }

  return (
    <section className="panel" aria-label="Orders">
      <h2>Orders (OMS)</h2>

      <form
        className="order-form"
        onSubmit={(e) => {
          e.preventDefault();
          void place();
        }}
      >
        <input
          aria-label="Order symbol"
          value={form.symbol}
          onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
        />
        <select
          aria-label="Side"
          value={form.transaction_type}
          onChange={(e) =>
            setForm({ ...form, transaction_type: e.target.value as TransactionType })
          }
        >
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
        <select
          aria-label="Order type"
          value={form.order_type}
          onChange={(e) => setForm({ ...form, order_type: e.target.value as OrderType })}
        >
          <option value="MARKET">MARKET</option>
          <option value="LIMIT">LIMIT</option>
          <option value="SL">SL</option>
          <option value="SL-M">SL-M</option>
        </select>
        <input
          aria-label="Quantity"
          type="number"
          min={1}
          value={form.quantity}
          onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
        />
        <input
          aria-label="Price"
          type="number"
          value={form.price ?? ""}
          onChange={(e) =>
            setForm({ ...form, price: e.target.value ? Number(e.target.value) : null })
          }
        />
        <select
          aria-label="Product type"
          value={form.product_type}
          onChange={(e) => setForm({ ...form, product_type: e.target.value as ProductType })}
        >
          <option value="INTRADAY">INTRADAY</option>
          <option value="DELIVERY">DELIVERY</option>
          <option value="MARGIN">MARGIN</option>
          <option value="CO">CO</option>
          <option value="BO">BO</option>
        </select>
        <button type="submit" disabled={busy} data-testid="place-order">
          Place Order
        </button>
      </form>
      {status && (
        <p className="muted" role="status" data-testid="order-status">
          {status}
        </p>
      )}

      {state.loading && <p className="muted">Loading orders…</p>}
      {state.error && (
        <p className="error" role="alert">
          Failed to load orders: {state.error.message}
        </p>
      )}

      {state.data && (
        <table data-testid="orders-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Filled</th>
              <th>Price</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {state.data.orders.map((o) => (
              <tr key={o.order_id}>
                <td>{o.order_id}</td>
                <td>{o.symbol}</td>
                <td className={o.transaction_type === "BUY" ? "pnl-pos" : "pnl-neg"}>
                  {o.transaction_type}
                </td>
                <td>{o.order_type}</td>
                <td>{o.quantity}</td>
                <td>{o.filled_quantity}</td>
                <td>{fmtNum(o.price)}</td>
                <td>
                  <span className={pnlClass(0)}>{o.status}</span>
                </td>
                <td>
                  <button
                    type="button"
                    onClick={() => void cancel(o.order_id)}
                    disabled={!["OPEN", "PARTIALLY_FILLED", "TRIGGER_PENDING"].includes(o.status)}
                  >
                    Cancel
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
