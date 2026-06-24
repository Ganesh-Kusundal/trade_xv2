# Dhan API Coverage Checklist

Manual audit: compare Dhan v2 REST + WebSocket API against `brokers/dhan/` implementation.

**Status legend:** `implemented` | `adapter_only` | `gateway_exposed` | `not_implemented`

## Market Data

| Vendor endpoint | Adapter | Gateway | CLI | REST | Status |
|-----------------|---------|---------|-----|------|--------|
| LTP / Quote | `market_data.get_ltp`, `get_quote` | `ltp`, `quote` | `quote` | datalake quote | gateway_exposed |
| Market Depth | `market_data.get_depth` | `depth` | `depth` | — | partial |
| Historical candles | `historical.get_historical` | `history` | `historical` | datalake candles | partial |
| Option chain | `options.get_option_chain` | `option_chain` | `option-chain` | datalake chain | partial |
| Futures chain | `futures.get_contracts` | `future_chain` | `futures` | — | partial |

## Orders

| Vendor endpoint | Adapter | Gateway | CLI | REST | Status |
|-----------------|---------|---------|-----|------|--------|
| Place order | `orders.place_order` | `place_order` | `place-order` (OMS) | POST /orders | gateway_exposed |
| Modify order | `orders.modify_order` | `modify_order` | `modify-order` | PUT /orders | gateway_exposed |
| Cancel order | `orders.cancel_order` | `cancel_order` | `cancel-order` | DELETE /orders | gateway_exposed |
| Order book | `orders.get_orderbook` | `get_orderbook` | `orders` | GET /orders (OMS) | partial |
| Super orders | `super_orders.*` | `extended.*` | — | — | adapter_only |
| Forever orders | `forever_orders.*` | `extended.*` | — | — | adapter_only |
| Slice orders | `orders.place_slice_order` | — | — | — | adapter_only |

## Portfolio

| Vendor endpoint | Adapter | Gateway | CLI | REST | Status |
|-----------------|---------|---------|-----|------|--------|
| Positions | `portfolio.get_positions` | `positions` | `positions` | GET /portfolio/positions (OMS) | partial |
| Holdings | `portfolio.get_holdings` | `holdings` | `holdings` | GET /portfolio/holdings (OMS) | partial |
| Funds | `portfolio.get_balance` | `funds` | `account` | — | partial |

## WebSocket

| Feed | Adapter | Gateway | CLI | REST | Status |
|------|---------|---------|-----|------|--------|
| Market feed | `DhanMarketFeed` | `stream` | `stream`, `websocket` | WS /ws/market | gateway_exposed |
| Order stream | `DhanOrderStream` | — | `websocket --once` | — | adapter_only |
| Depth 20/200 | `depth_20/200 feeds` | `depth_20`, `depth_200` | — | — | adapter_only |

## Extended (Dhan-only)

| Feature | Adapter | Extended | CLI | REST | Status |
|---------|---------|----------|-----|------|--------|
| Margin calculator | `margin.calculate` | — | — | — | adapter_only |
| EDIS | `edis.*` | `extended.*` | — | — | adapter_only |
| IP management | `ip_management.*` | `extended.*` | — | — | adapter_only |
| Ledger | `ledger.get_ledger` | `extended.get_ledger` | — | — | adapter_only |
| Exit all | `exit_all.exit_all` | `extended.exit_all` | — | square-off (OMS) | partial |

Run automated audit: `python scripts/audit_broker_methods.py --broker dhan`
