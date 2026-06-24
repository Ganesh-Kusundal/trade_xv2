# Upstox API Coverage Checklist

Manual audit: compare Upstox v2/v3 API against `brokers/upstox/` implementation.

**Status legend:** `implemented` | `adapter_only` | `gateway_exposed` | `not_implemented` | `known_gap`

## Market Data

| Vendor endpoint | Adapter | Gateway | CLI | REST | Status |
|-----------------|---------|---------|-----|------|--------|
| Quote / LTP | `market_data.get_quote` | `quote`, `ltp` | `quote` | datalake quote | partial |
| Depth | `market_data.get_depth` | `depth` | `depth` | — | partial |
| Historical | `historical.fetch_candles` | `history` | `historical` | datalake candles | partial |
| Option chain | `options.get_option_chain` | `option_chain` | `option-chain` | datalake chain | partial |
| Futures chain | `futures.get_contracts` | `future_chain` | `futures` | instrument master + resolved key | **verified** (2026-06-24) |

## Orders

| Vendor endpoint | Adapter | Gateway | CLI | REST | Status |
|-----------------|---------|---------|-----|------|--------|
| Place order | `order_command.place_order` | `place_order` | `place-order` (OMS) | POST /orders | gateway_exposed |
| GTT / Forever | `gtt.*` | `extended.*` | — | — | adapter_only |
| Cover order | `cover.place_cover_order` | — | — | — | adapter_only |
| Slice order | `slice.place_slice_order` | — | — | — | adapter_only |
| Multi order | `order_client.place_multi_order` | — | `place-orders` | — | adapter_only |

## Portfolio & Account

| Vendor endpoint | Adapter | Gateway | CLI | REST | Status |
|-----------------|---------|---------|-----|------|--------|
| Positions | `portfolio.get_positions` | `positions` | `positions` | GET /portfolio/positions (OMS) | partial |
| Holdings | `portfolio.get_holdings` | `holdings` | `holdings` | GET /portfolio/holdings (OMS) | partial |
| Funds | `portfolio.get_balance` | `funds` | `account` | — | partial |
| Kill switch (broker) | `kill_switch.set_status` | — | `risk kill-switch` (OMS) | POST /risk/kill-switch (OMS) | adapter_only |

## Intelligence (Upstox-only)

| Feature | Adapter | Gateway | CLI | REST | Status |
|---------|---------|----------|-----|------|--------|
| PCR / Max pain | `intelligence.get_pcr` | — | — | GET /options/pcr, /max-pain | partial (datalake) |
| News | `news.get_news` | — | `news` | — | partial |
| FII/DII | `intelligence.get_fii_flow` | — | — | — | adapter_only |
| Smartlist | `intelligence.get_smartlist` | — | — | — | adapter_only |

## WebSocket

| Feed | Adapter | Gateway | CLI | REST | Status |
|------|---------|---------|-----|------|--------|
| Market data v3 | `market_data_websocket` | `stream` | `websocket` | WS /ws/market | gateway_exposed |
| Portfolio stream | `UpstoxPortfolioStream` | — | — | — | **known_gap** (unwired) |

## Extended

| Feature | Adapter | Extended | CLI | REST | Status |
|---------|---------|----------|-----|------|--------|
| IPO | `ipo.get_ipos` | `extended.get_ipos` | — | — | adapter_only |
| Mutual funds | `mutual_funds.*` | `extended.*` | — | — | adapter_only |
| Payments | `payments.*` | `extended.*` | — | — | adapter_only |
| Fundamentals | `fundamentals.*` | `extended.*` | — | — | adapter_only |

### Analytics-only mode

`UPSTOX_ANALYTICS_ONLY=true` switches token holder only; all adapters remain wired.
Trading guards use `UPSTOX_ALLOW_LIVE_ORDERS` separately.

Run automated audit: `python scripts/audit_broker_methods.py --broker upstox`
