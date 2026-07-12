# MCP Tool Reference — `brokers`

The Trading OS MCP server exposes broker capabilities as MCP tools for LLM
consumption. Built on FastMCP, the server registers tools that map 1:1 to the
`brokers.services` core — the same implementation shared by the SDK and CLI.

---

## Quick Start

```bash
# Run the MCP server (stdio transport)
python -m brokers.mcp.server

# Or via pip
pip install -e '.[mcp]'
```

All tools default to the paper broker (`broker: "paper"`) for safe-by-default
operation. Pass `broker: "dhan"` or `broker: "upstox"` for live brokers.

---

## Table of Contents

1. [Connection](#1-connection)
2. [Market Data](#2-market-data)
3. [Trading](#3-trading)
4. [Portfolio](#4-portfolio)
5. [Analytics](#5-analytics)
6. [Operations](#6-operations)
7. [News](#7-news)

---

## 1. Connection

### `broker_connect`

Connect to a broker and return session status + startup checkpoints.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** Session status dictionary with `broker_id`, `connected`, `mode`, `orders_enabled`, `error`, and `remediation` fields.

**Example request:**
```json
{
  "broker": "dhan"
}
```

**Example response:**
```json
{
  "broker_id": "dhan",
  "connected": true,
  "mode": "live",
  "orders_enabled": true,
  "extensions": ["depth_20", "depth_200", "super_order"],
  "error": null,
  "remediation": ""
}
```

**Error handling:** Returns `connected: false` with `error` and `remediation`
strings containing the failure reason and fix guidance.

---

## 2. Market Data

### `broker_quote`

Fetch a live quote for a symbol.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `symbol` | `string` | — | Trading symbol (e.g. `"RELIANCE"`) |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** `{ symbol, broker, quote: { ltp, open, high, low, close, bid, ask, volume, change_pct, event_time, ... } }`

**Example request:**
```json
{
  "symbol": "RELIANCE",
  "broker": "paper"
}
```

**Example response:**
```json
{
  "symbol": "RELIANCE",
  "broker": "paper",
  "quote": {
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "ltp": "2456.30",
    "open": "2440.00",
    "high": "2462.50",
    "low": "2435.10",
    "close": "2448.00",
    "bid": "2456.00",
    "ask": "2456.50",
    "volume": 1234567,
    "change_pct": "+0.34%",
    "event_time": "2025-07-12T15:30:00"
  }
}
```

**Error handling:** Network/lookup errors return serialized exception info.

---

### `broker_history`

Fetch historical OHLCV bars for a symbol.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `symbol` | `string` | — | Trading symbol |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `timeframe` | `string` | `"1D"` | Candle timeframe (`"1m"`, `"5m"`, `"15m"`, `"1D"`, etc.) |
| `days` | `integer` | `5` | Number of calendar days |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** `{ symbol, broker, timeframe, bar_count }`

**Example request:**
```json
{
  "symbol": "NIFTY",
  "broker": "paper",
  "timeframe": "15m",
  "days": 5
}
```

**Example response:**
```json
{
  "symbol": "NIFTY",
  "broker": "paper",
  "timeframe": "15m",
  "bar_count": 48
}
```

**Error handling:** Timeframe not supported → error response. Rate limit hits
→ error with remediation.

---

### `broker_subscribe`

Probe live subscription for a symbol (brief connect/disconnect).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `symbol` | `string` | — | Trading symbol |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** `{ symbol, broker, subscribed: bool }`

**Example response:**
```json
{
  "symbol": "RELIANCE",
  "broker": "paper",
  "subscribed": true
}
```

**Error handling:** WebSocket failure → `subscribed: false`.

---

### `broker_market_depth`

Fetch market depth for a symbol.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `symbol` | `string` | — | Trading symbol |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** `{ symbol, broker, depth: { bids: [...], asks: [...], spread, depth_type } }`

**Example response:**
```json
{
  "symbol": "RELIANCE",
  "broker": "dhan",
  "depth": {
    "bids": [
      { "price": 2456.00, "quantity": 100, "orders": 3 },
      { "price": 2455.90, "quantity": 250, "orders": 5 }
    ],
    "asks": [
      { "price": 2456.50, "quantity": 150, "orders": 2 },
      { "price": 2457.00, "quantity": 80, "orders": 1 }
    ],
    "spread": 0.50,
    "depth_type": "20-level"
  }
}
```

**Error handling:** Depth not supported for symbol → error. Broker-specific
depth levels (Dhan: 20/200, Upstox: 30).

---

## 3. Trading

### `broker_place_order`

Place an order via the OMS spine (paper-safe by default).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `symbol` | `string` | — | Trading symbol |
| `quantity` | `integer` | — | Order quantity |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `side` | `string` | `"BUY"` | `"BUY"` or `"SELL"` |
| `price` | `float \| null` | `null` | Limit price (null for MARKET) |
| `order_type` | `string` | `"LIMIT"` | `"LIMIT"` or `"MARKET"` |
| `product_type` | `string` | `"INTRADAY"` | `"INTRADAY"`, `"CNC"`, `"MIS"`, etc. |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** `{ broker, symbol, result: { order_id, status, ... } }`

**Example request:**
```json
{
  "symbol": "RELIANCE",
  "quantity": 10,
  "broker": "paper",
  "side": "BUY",
  "price": 2450.0,
  "order_type": "LIMIT"
}
```

**Example response:**
```json
{
  "broker": "paper",
  "symbol": "RELIANCE",
  "result": {
    "order_id": "PAPER-00001",
    "status": "PLACED",
    "symbol": "RELIANCE",
    "side": "BUY",
    "quantity": 10,
    "price": "2450.00"
  }
}
```

**Error handling:** Insufficient funds → rejection. Invalid quantity/symbol →
validation error. Paper broker always succeeds.

---

### `broker_modify_order`

Modify an open order.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `order_id` | `string` | — | Order id to modify |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `quantity` | `integer \| null` | `null` | New quantity |
| `price` | `float \| null` | `null` | New price |

**Output:** `{ broker, order_id, result: { ... } }`

**Example request:**
```json
{
  "order_id": "DHAN-12345",
  "broker": "dhan",
  "quantity": 20,
  "price": 2460.0
}
```

**Error handling:** Order not found → error. Order already executed/cancelled →
rejection.

---

### `broker_cancel_order`

Cancel an open order.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `order_id` | `string` | — | Order id to cancel |
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, order_id, result: { ... } }`

**Example response:**
```json
{
  "broker": "paper",
  "order_id": "PAPER-00001",
  "result": {
    "order_id": "PAPER-00001",
    "status": "CANCELLED"
  }
}
```

**Error handling:** Order not found → error. Already cancelled → informational
response.

---

## 4. Portfolio

### `broker_positions`

Return open positions.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, positions: [...] }`

**Example response:**
```json
{
  "broker": "dhan",
  "positions": [
    {
      "symbol": "RELIANCE",
      "quantity": 10,
      "average_price": "2450.00",
      "pnl": "+63.00",
      "product": "INTRADAY"
    }
  ]
}
```

---

### `broker_holdings`

Return portfolio holdings.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, holdings: [...] }`

---

### `broker_funds`

Return available funds/margin.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, funds: { ... } }`

---

### `broker_orders`

List orders for the session.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, orders: [...] }`

**Example response:**
```json
{
  "broker": "paper",
  "orders": [
    {
      "order_id": "PAPER-00001",
      "symbol": "RELIANCE",
      "side": "BUY",
      "quantity": 10,
      "price": "2450.00",
      "status": "PLACED"
    }
  ]
}
```

---

## 5. Analytics

### `broker_option_chain`

Fetch option chain for an underlying.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `underlying` | `string` | — | Underlying symbol (e.g. `"NIFTY"`) |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** `{ underlying, broker, strikes: int }` (strike count)

**Example response:**
```json
{
  "underlying": "NIFTY",
  "broker": "paper",
  "strikes": 42
}
```

**Error handling:** No chain data available → `strikes: 0`.

---

### `broker_symbol_lookup`

Resolve symbol to canonical instrument id.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `symbol` | `string` | — | Trading symbol |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** `{ symbol, broker, instrument_id: string }`

**Example response:**
```json
{
  "symbol": "RELIANCE",
  "broker": "dhan",
  "instrument_id": "NSE_EQ_RELIANCE"
}
```

**Error handling:** Unknown symbol → error with suggestion.

---

### `broker_instrument_lookup`

Resolve symbol to public instrument metadata (symbol, exchange, lot_size).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `symbol` | `string` | — | Trading symbol |
| `broker` | `string` | `"paper"` | Broker plugin id |
| `exchange` | `string` | `"NSE"` | Exchange code |

**Output:** Instrument metadata dict with `symbol`, `exchange`, `lot_size` and
other public fields. No broker tokens exposed.

**Example response:**
```json
{
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "lot_size": 1,
  "isin": "INE002A01018",
  "series": "EQ"
}
```

---

## 6. Operations

### `broker_health`

Run broker health checks.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, checks: [...] }` — each check is a dict with check name, status, and detail.

---

### `broker_capabilities`

List broker capabilities for an instrument.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |
| `symbol` | `string` | `"RELIANCE"` | Symbol to check capabilities for |

**Output:** `{ broker, capabilities: { broker_id, extensions, matrix } }`

**Example response:**
```json
{
  "broker": "dhan",
  "capabilities": {
    "broker_id": "dhan",
    "extensions": ["depth_20", "depth_200", "super_order", "forever_order"],
    "matrix": {
      "quote": true,
      "history": true,
      "depth": true,
      "subscribe": true,
      "order": true
    }
  }
}
```

---

### `broker_verify`

Run startup self-test: config → auth → caps → mappings → quote → history → websocket → PASS.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** VerifyReport as dict with `passed`, `steps`, and per-step detail.

**Example response:**
```json
{
  "passed": true,
  "steps": [
    { "name": "config", "status": "PASS", "detail": "..." },
    { "name": "auth", "status": "PASS", "detail": "..." },
    { "name": "capabilities", "status": "PASS", "detail": "..." },
    { "name": "mappings", "status": "PASS", "detail": "..." },
    { "name": "quote", "status": "PASS", "detail": "..." },
    { "name": "history", "status": "PASS", "detail": "..." },
    { "name": "websocket", "status": "PASS", "detail": "..." }
  ]
}
```

---

### `broker_doctor`

Run full environment pre-flight validation.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** Doctor report as dict with checks for config, auth, credentials,
env vars, network, and broker-specific requirements.

---

### `broker_diagnose`

Run diagnostics suite — connectivity, auth, data, orders (TOS-P4-002).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, diagnostics: { ... } }` — serialized diagnostic results.

---

### `broker_benchmark`

Run broker performance benchmark — TOS-P4-002 platform_ops parity.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, benchmark: { ... } }` — latency/throughput metrics.

---

### `broker_certify`

Run full broker certification suite.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** Certification report as dict with `is_certified`, `checks`, and per-check detail.

---

### `broker_mappings`

Run symbol mapping round-trip validation.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |

**Output:** `{ broker, all_passed: bool, results: [...] }`

Each result contains: `asset`, `exchange`, `symbol`, `passed`, `detail`.

**Example response:**
```json
{
  "broker": "dhan",
  "all_passed": true,
  "results": [
    { "asset": "RELIANCE", "exchange": "NSE", "symbol": "RELIANCE", "passed": true, "detail": "..." },
    { "asset": "NIFTY", "exchange": "NFO", "symbol": "NIFTY", "passed": true, "detail": "..." }
  ]
}
```

---

## 7. News

### `broker_news`

Fetch broker news feed (Upstox when configured).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `broker` | `string` | `"paper"` | Broker plugin id |
| `symbol` | `string \| null` | `null` | Optional symbol filter |
| `category` | `string` | `"holdings"` | News category (`"holdings"`, `"market"`, etc.) |

**Output:** `{ broker, news: [...] }`

**Example request:**
```json
{
  "broker": "upstox",
  "symbol": "RELIANCE",
  "category": "holdings"
}
```

**Example response:**
```json
{
  "broker": "upstox",
  "news": [
    {
      "headline": "Reliance Industries Q1 results beat estimates",
      "source": "Economic Times",
      "time": "2025-07-12T10:30:00",
      "url": "https://..."
    }
  ]
}
```

**Error handling:** News not supported for broker → empty array.

---

## Tool Summary

| Category | Tool | Description |
|---|---|---|
| Connection | `broker_connect` | Connect and get session status |
| Market Data | `broker_quote` | Live quote for a symbol |
| Market Data | `broker_history` | Historical OHLCV bars |
| Market Data | `broker_subscribe` | Probe live subscription |
| Market Data | `broker_market_depth` | Order book depth |
| Trading | `broker_place_order` | Place an order |
| Trading | `broker_modify_order` | Modify an open order |
| Trading | `broker_cancel_order` | Cancel an open order |
| Portfolio | `broker_positions` | Open positions |
| Portfolio | `broker_holdings` | Portfolio holdings |
| Portfolio | `broker_funds` | Available funds/margin |
| Portfolio | `broker_orders` | List orders |
| Analytics | `broker_option_chain` | Option chain for underlying |
| Analytics | `broker_symbol_lookup` | Resolve symbol to instrument id |
| Analytics | `broker_instrument_lookup` | Resolve symbol to instrument metadata |
| Operations | `broker_health` | Health checks |
| Operations | `broker_capabilities` | Broker capability matrix |
| Operations | `broker_verify` | Startup self-test |
| Operations | `broker_doctor` | Environment pre-flight |
| Operations | `broker_diagnose` | Diagnostics suite |
| Operations | `broker_benchmark` | Performance benchmark |
| Operations | `broker_certify` | Full certification suite |
| Operations | `broker_mappings` | Symbol mapping validation |
| News | `broker_news` | News feed |

---

## Common Error Patterns

All tools follow a consistent error response pattern. Errors are returned as
serialized dictionaries (never raised as exceptions to the MCP caller):

```json
{
  "error": "ConnectionRefused: broker plugin 'xyz' not found",
  "remediation": "Run 'broker discover' to see available plugins"
}
```

Common error categories:

| Error | Typical Cause | Resolution |
|---|---|---|
| `ConnectionRefused` | Broker plugin not installed | `pip install -e '.[dhan]'` |
| `AuthError` | Missing/expired credentials | Update `.env.local` |
| `SymbolNotFound` | Unknown trading symbol | Check symbol master |
| `CapabilityError` | Feature not supported by broker | Check `broker_capabilities` |
| `RateLimitError` | API rate limit hit | Wait and retry |
| `OrderRejected` | Invalid order parameters | Check quantity/price/symbol |
