# CLI Reference — `broker`

The Trading OS broker CLI is a Click-based developer tool for interacting with
the broker layer. It shares the same `brokers.services` core as the SDK and MCP
interfaces, ensuring identical behavior across all surfaces.

---

## Quick Start

```bash
# List registered brokers
python -m brokers.cli.broker discover

# Get a quote
python -m brokers.cli.broker quote RELIANCE

# JSON mode (for CI/scripts)
python -m brokers.cli.broker --json quote RELIANCE

# Start interactive shell
python -m brokers.cli.broker shell
```

---

## Table of Contents

1. [Global Options](#1-global-options)
2. [Interactive Shell](#2-interactive-shell)
3. [Connection & Discovery](#3-connection--discovery)
4. [Market Data](#4-market-data)
5. [Portfolio](#5-portfolio)
6. [Trading](#6-trading)
7. [Instrument Lookup](#7-instrument-lookup)
8. [Diagnostics](#8-diagnostics)
9. [Broker Extensions](#9-broker-extensions)
10. [JSON Mode](#10-json-mode)
11. [Interactive Shell Navigation](#11-interactive-shell-navigation)
12. [Recovery Menu](#12-recovery-menu)
13. [Context-Aware Remediation](#13-context-aware-remediation)

---

## 1. Global Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--broker` | `str` | `"paper"` | Broker id (`paper`, `dhan`, `upstox`) |
| `--json` | flag | `False` | Emit raw JSON instead of Rich tables |

```bash
broker --broker dhan --json quote RELIANCE
```

When stdout is not a TTY (piped), JSON is emitted automatically regardless of
the `--json` flag. This makes piped output always machine-parseable.

---

## 2. Interactive Shell

### `shell`

```
broker shell
broker --broker dhan shell
```

Opens a hierarchical numbered-menu REPL. The shell:

- Opens a `BrokerSession` for the shell lifetime (single connect, reused per command)
- Shows a **Main Menu** with sections: Session, Market, Portfolio, Trading, Diagnostics
- Supports numbered or named navigation
- Prompts for required arguments when not provided
- Shows a **Recovery Menu** when live broker connection fails

```
broker(dhan)> 2              # enter Market section
broker(dhan:Market)> quote   # run quote command
broker(dhan:Market)> back    # return to main menu
broker(dhan)> exit           # exit shell
```

See [Interactive Shell Navigation](#11-interactive-shell-navigation) for full details.

---

## 3. Connection & Discovery

### `connect`

```
broker connect
broker --broker dhan connect
```

Connect to a broker and report session status.

**Output:** Prints connection status including broker id, mode, and orders enabled status.

```
Connected to dhan: mode=live orders_enabled=True
```

**JSON output:**
```json
{
  "broker_id": "dhan",
  "connected": true,
  "mode": "live",
  "orders_enabled": true
}
```

---

### `discover`

```
broker discover
```

List all registered broker plugins.

**Output:** A table of available broker ids.

```json
["paper", "dhan", "upstox"]
```

**Example invocation:**
```bash
broker discover
```

**Output format:** Rich table with broker names, or JSON array when `--json`.

---

## 4. Market Data

### `quote`

```
broker quote SYMBOL
broker --broker dhan quote RELIANCE
```

| Argument | Required | Description |
|---|---|---|
| `SYMBOL` | Yes | Trading symbol (e.g. `RELIANCE`, `NIFTY`) |

Fetch a live quote for a symbol.

**Output fields:** `symbol`, `exchange`, `ltp`, `open`, `high`, `low`, `close`, `bid`, `ask`, `volume`, `change_pct`, `source`, `event_time`.

**Example:**
```bash
broker quote RELIANCE
```

**JSON output:**
```json
{
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
  "source": "dhan",
  "event_time": "2025-07-12T15:30:00"
}
```

---

### `history`

```
broker history SYMBOL
broker history SYMBOL --tf 5m --days 30
```

| Argument/Option | Type | Default | Description |
|---|---|---|---|
| `SYMBOL` | `str` | — | Trading symbol (required) |
| `--tf` | `str` | `"1D"` | Timeframe (`1m`, `5m`, `15m`, `1D`, etc.) |
| `--days` | `int` | `5` | Number of calendar days |

Fetch historical OHLCV bars for a symbol.

**Example:**
```bash
broker history NIFTY --tf 15m --days 10
```

**Output:** Rich table with OHLCV columns (last 10 bars shown) plus metadata
bar count, timeframe, and contributing brokers.

**JSON output:**
```json
{
  "symbol": "NIFTY",
  "broker": "paper",
  "timeframe": "15m",
  "bar_count": 48
}
```

---

### `subscribe`

```
broker subscribe SYMBOL
```

| Argument | Required | Description |
|---|---|---|
| `SYMBOL` | Yes | Trading symbol |

Subscribe to live data for a symbol (brief connection probe — connects,
receives a tick, then disconnects).

**Output:**
```json
{
  "symbol": "RELIANCE",
  "handle": "active",
  "subscribed": true
}
```

---

### `depth`

```
broker depth SYMBOL
```

| Argument | Required | Description |
|---|---|---|
| `SYMBOL` | Yes | Trading symbol |

Fetch market depth (order book) for a symbol.

**Output:** Rich table with Side, Level, Price, Qty, Orders columns for bids
and asks, plus spread and depth_type metadata.

---

### `option_chain`

```
broker option_chain UNDERLYING
```

| Argument | Required | Description |
|---|---|---|
| `UNDERLYING` | Yes | Underlying symbol (e.g. `NIFTY`) |

Fetch option chain for an underlying.

**Output:** ATM-centered window of strikes (±10) showing CE LTP, CE OI,
Strike, PE LTP, PE OI. Full chain metadata (underlying, exchange, expiry,
total strikes) printed above the table.

---

## 5. Portfolio

### `positions`

```
broker positions
```

Show open positions.

**Output:** Rich table of positions or `(no data)` if empty.

---

### `holdings`

```
broker holdings
```

Show portfolio holdings.

**Output:** Rich table of holdings or `(no data)` if empty.

---

### `funds`

```
broker funds
```

Show available funds/margin.

**Output:** Key-value display of fund details.

---

### `orders`

```
broker orders
```

List orders for the session.

**Output:** Rich table of orders or `(no data)` if empty.

---

## 6. Trading

### `order`

```
broker order SYMBOL QUANTITY
broker order RELIANCE 10 --side BUY --price 2450
broker order NIFTY 50 --side SELL --order-type MARKET --product-type MIS
```

| Argument/Option | Type | Default | Description |
|---|---|---|---|
| `SYMBOL` | `str` | — | Trading symbol (required) |
| `QUANTITY` | `int` | — | Order quantity (required) |
| `--side` | `str` | `"BUY"` | `BUY` or `SELL` |
| `--price` | `float` | `None` | Limit price (None for MARKET) |
| `--order-type` | `str` | `"LIMIT"` | `LIMIT` or `MARKET` |
| `--product-type` | `str` | `"INTRADAY"` | `INTRADAY`, `CNC`, `MIS`, etc. |

Place an order (paper-safe by default).

**Example:**
```bash
broker order RELIANCE 10 --side BUY --price 2450 --order-type LIMIT
```

---

### `cancel`

```
broker cancel ORDER_ID
```

| Argument | Required | Description |
|---|---|---|
| `ORDER_ID` | Yes | The order id to cancel |

Cancel an order by id.

**Example:**
```bash
broker cancel DHAN-12345
```

---

### `modify`

```
broker modify ORDER_ID
broker modify ORDER_ID --quantity 20 --price 2460
```

| Argument/Option | Type | Default | Description |
|---|---|---|---|
| `ORDER_ID` | `str` | — | Order id (required) |
| `--quantity` | `int` | `None` | New quantity |
| `--price` | `float` | `None` | New price |

Modify an open order.

**Example:**
```bash
broker modify DHAN-12345 --quantity 5 --price 2460.00
```

---

## 7. Instrument Lookup

### `symbols`

```
broker symbols SYMBOL
```

| Argument | Required | Description |
|---|---|---|---|
| `SYMBOL` | Yes | Trading symbol |

Resolve SYMBOL to canonical instrument id.

**Output:**
```json
{
  "symbol": "RELIANCE",
  "instrument_id": "NSE_EQ_RELIANCE"
}
```

---

### `instrument`

```
broker instrument SYMBOL
broker instrument SYMBOL --exchange BSE
```

| Argument/Option | Type | Default | Description |
|---|---|---|---|
| `SYMBOL` | `str` | — | Trading symbol (required) |
| `--exchange` | `str` | `"NSE"` | Exchange code |

Resolve SYMBOL to public instrument metadata (symbol, exchange, lot_size)
without exposing broker tokens.

---

### `security` (hidden)

```
broker security SYMBOL
```

Deprecated alias for `instrument`. Hidden from help output.

---

### `capability`

```
broker capability
```

List broker capabilities for an instrument — extensions and capability matrix.

**Output:** Broker id, extensions list, and enabled capability matrix.

---

### `mappings`

```
broker mappings
```

Run symbol mapping round-trip validation. Exits with code 1 if any mapping
fails.

**Output:** Per-asset pass/fail detail table.

---

## 8. Diagnostics

### `diagnose`

```
broker diagnose
```

Run diagnostics suite — connectivity, auth, data, orders (TOS-P4-002).

---

### `health`

```
broker health
```

Run broker health checks.

---

### `doctor`

```
broker doctor
```

Run full environment pre-flight validation (kubectl-style). Checks config,
auth, capabilities, mappings, connectivity, and data access.

---

### `benchmark`

```
broker benchmark
```

Run latency/throughput benchmark for the broker.

---

### `market_hours`

```
broker market_hours
```

Run market-hours behavior matrix for current phase.

---

### `certify`

```
broker certify
broker certify dhan --live
broker certify --json
```

| Argument/Option | Type | Default | Description |
|---|---|---|---|
| `BROKER_ID` | `str` | (current) | Broker to certify |
| `--live` | flag | `False` | Run live API tests (requires credentials) |
| `--json` | flag | `False` | Emit JSON output |

Run the full broker certification suite. Exits with code 1 if not certified.

---

### `verify`

```
broker verify
broker verify dhan
broker verify --json
```

| Argument/Option | Type | Default | Description |
|---|---|---|---|
| `BROKER_ID` | `str` | (current) | Broker to verify |
| `--json` | flag | `False` | Emit JSON output |

Startup self-test: config → auth → caps → mappings → quote → history →
websocket → PASS. Exits with code 1 on failure.

---

## 9. Broker Extensions

Broker-specific commands are available as extensions, filtered by the connected
broker's capability matrix.

### Dhan Extensions

| Command | Description |
|---|---|
| `depth20 SYMBOL` | Fetch 20-level WebSocket depth |
| `depth200 SYMBOL` | Fetch 200-level WebSocket depth |
| `super_orders` | List Dhan super/bracket orders |
| `forever_orders` | List Dhan forever orders |

### Upstox Extensions

| Command | Description |
|---|---|
| `depth30 SYMBOL` | Fetch 30-level depth |
| `news [SYMBOL]` | Fetch news (optional symbol filter) |

**Example:**
```bash
broker --broker dhan depth20 RELIANCE
broker --broker upstox news INFY
broker --broker dhan super_orders
```

---

## 10. JSON Mode

JSON is emitted when:
1. `--json` flag is passed
2. stdout is not a TTY (piped/redirected)

This ensures scripts, CI, and agents always get parseable output.

```bash
# Force JSON output
broker --json quote RELIANCE | jq .ltp

# Piped (auto-JSON)
broker quote RELIANCE | python -m json.tool

# In CI
broker --broker paper --json quote RELIANCE > quote.json
```

All commands produce valid JSON in this mode — the same data as Rich tables,
serialized via `safe_serialize()`.

---

## 11. Interactive Shell Navigation

### Menu Structure

The shell presents a hierarchical numbered menu:

```
Main Menu
  1  Session        — connect, discover, capability, symbols, instrument, mappings
  2  Market          — quote, history, subscribe, depth, option_chain
  3  Portfolio       — positions, holdings, funds, orders
  4  Trading         — order, cancel, modify
  5  Diagnostics     — diagnose, health, doctor, benchmark, market_hours, certify, verify
  6  Extensions      — (broker-specific: depth20, depth200, super_orders, etc.)
```

### Navigation Commands

| Input | Action |
|---|---|
| Number (`1`–`5`) | Enter that section |
| Section name (`market`) | Enter that section |
| `back` / `exit` | Return to parent menu |
| `help` | Show command reference for current menu |
| `quit` / `q` | Exit the shell |

### Running Commands

Within a section, commands can be invoked by number or name:

```
broker(dhan:Market)> 1           # run 'quote' (item #1)
broker(dhan:Market)> quote RELIANCE   # same, with args
broker(dhan:Market)> back        # return to Main
```

When a command requires arguments and none are provided, the shell prompts:

```
broker(dhan:Market)> quote
symbol [RELIANCE]:
```

Default values are suggested in brackets (e.g. `RELIANCE` for quote commands,
`NIFTY` for option_chain).

### Prompt Format

```
broker(paper)           — Main menu, paper broker
broker(dhan)            — Main menu, dhan broker
broker(dhan:Market)     — Market section, dhan broker
broker(dhan:recovery)   — Recovery menu, dhan broker
```

---

## 12. Recovery Menu

When a live broker connection fails, the shell enters the **Recovery Menu**:

```
Recovery
  1  retry    — Retry broker connect
  2  doctor   — Run environment pre-flight
  3  quit     — Leave shell

Fix: set DHAN_ACCESS_TOKEN or TOTP credentials in .env.local,
     then press 1 to retry.
```

| Input | Action |
|---|---|
| `1` / `retry` | Close and reopen the BrokerSession |
| `2` / `doctor` | Run `doctor` diagnostics without leaving recovery |
| `3` / `quit` | Exit the shell |

The recovery loop continues until either:
- Connection succeeds (enters main menu)
- User quits

---

## 13. Context-Aware Remediation

The shell provides specific remediation hints based on the actual connection
failure. These are displayed in the recovery menu header and footer.

### Dhan Broker

| Error Pattern | Remediation |
|---|---|
| Rate limit / "2 minutes" / cooldown | Wait 2 minutes, then press 1 to remint TOTP, or paste fresh token into `.env.local` |
| Token rejected / expired / DH-906 | Wait 2 min, press 1 to remint via TOTP, or update `DHAN_ACCESS_TOKEN` in `.env.local` |
| General failure | Set `DHAN_ACCESS_TOKEN` or TOTP credentials in `.env.local`, then press 1 |

### Upstox Broker

| Error Pattern | Remediation |
|---|---|
| Token rejected / expired | Refresh `UPSTOX_ACCESS_TOKEN` in `.env.local`, then press 1 |
| 423 / locked / maintenance | Upstox funds API overnight maintenance (12:00 AM–5:30 AM IST). Retry after 5:30 AM IST |
| General failure | Set `UPSTOX_ACCESS_TOKEN` / OAuth credentials in `.env.local`, then press 1 |

### Other Brokers

| Error Pattern | Remediation |
|---|---|
| Any failure | Check broker credentials in `.env.local`, then press 1 |

These hints are generated dynamically from the actual exception message and
`remediation` attribute, not from static strings — so they stay accurate as
broker APIs evolve.
