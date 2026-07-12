# SDK Reference — `BrokerSession`

The Trading OS SDK exposes a single entry point: `BrokerSession`. Every
broker-specific detail (auth, websocket, symbol master, order routing) is
hidden behind this broker-agnostic facade. Market behavior lives on the
returned `Instrument` objects; broker-specific superpowers live behind
`instrument.broker.*`.

---

## Quick Start

```python
from brokers.session import BrokerSession

session = BrokerSession("paper")              # 1. connect
quote = session.quote(session.stock("RELIANCE"))  # 2. build instrument + quote
print(quote.ltp)                              # 3. use the data
```

Three lines. Any broker. Same code.

---

## Table of Contents

1. [Connection](#1-connection)
2. [Instrument Builders](#2-instrument-builders)
3. [Market Data](#3-market-data)
4. [Streaming](#4-streaming)
5. [Trading](#5-trading)
6. [Properties & Utilities](#6-properties--utilities)
7. [Connection Modes](#7-connection-modes)
8. [Paper Broker Usage](#8-paper-broker-usage)
9. [Error Handling Patterns](#9-error-handling-patterns)

---

## 1. Connection

### `BrokerSession.connect()` (classmethod)

```python
BrokerSession.connect(broker: str = "paper", **kwargs) -> BrokerSession
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `broker` | `str` | `"paper"` | Broker plugin id (`"paper"`, `"dhan"`, `"upstox"`) |
| `mode` | `str \| None` | `None` | Connection mode override (`"live"`, `"paper"`, `"replay"`) |
| `event_bus` | `Any \| None` | `None` | Optional event bus for pub/sub |
| `env_path` | `str \| None` | `None` | Custom path to `.env.local` |
| `load_instruments` | `bool` | `True` | Load symbol master on connect |
| `run_selftest` | `bool` | `False` | Run startup self-test after connect |
| `**kwargs` | `Any` | — | Forwarded to the broker plugin |

**Returns:** `BrokerSession`

Equivalent to `BrokerSession(broker, ...)`; named `connect` to match the
documented startup flow and `tradex.connect` mental model.

```python
# Paper (instant, no credentials)
session = BrokerSession.connect("paper")

# Live Dhan with TOTP
session = BrokerSession.connect("dhan", mode="live")

# With self-test
session = BrokerSession.connect("paper", run_selftest=True)
```

**Error cases:**
- Unknown broker id → plugin-not-found error
- Missing credentials (live mode) → auth failure with remediation hint
- `load_instruments=True` and symbol master unreachable → connection error

**Broker compatibility:** All brokers. Each broker plugin self-registers via
the broker discovery system; no central switch statement is touched here.

### `BrokerSession.__init__()`

```python
BrokerSession(
    broker: str = "paper",
    *,
    mode: str | None = None,
    event_bus: Any | None = None,
    env_path: str | None = None,
    load_instruments: bool = True,
    run_selftest: bool = False,
    **kwargs: Any,
) -> None
```

Identical to `.connect()` — `connect()` is a classmethod alias.

---

## 2. Instrument Builders

All builder methods return rich domain objects (`Equity`, `ETF`, `Index`,
`Future`, `Option`, `OptionChain`, `Commodity`, `Currency`, `Spot`). These
objects carry market data methods (`refresh()`, `.quote`) and broker-specific
extensions (`instrument.broker.*`).

### `stock()` / `equity()`

```python
session.stock(symbol: str, exchange: str = "NSE") -> Equity
session.equity(symbol: str, exchange: str = "NSE") -> Equity  # alias
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `symbol` | `str` | — | Trading symbol (e.g. `"RELIANCE"`) |
| `exchange` | `str` | `"NSE"` | Exchange code |

```python
reliance = session.stock("RELIANCE")
infosys = session.equity("INFY", exchange="BSE")
```

**Error cases:** Unknown symbol raises a domain-level lookup error.

**Broker compatibility:** All brokers.

### `etf()`

```python
session.etf(symbol: str, exchange: str = "NSE") -> ETF
```

```python
nifty_etf = session.etf("NIFTYBEES")
```

**Broker compatibility:** All brokers.

### `index()`

```python
session.index(name: str, exchange: str = "NSE") -> Index
```

```python
nifty = session.index("NIFTY 50")
sensex = session.index("SENSEX", exchange="BSE")
```

**Broker compatibility:** All brokers.

### `future()`

```python
session.future(symbol: str, *, expiry: date, exchange: str = "NFO") -> Future
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `symbol` | `str` | — | Underlying symbol |
| `expiry` | `date` | — | Contract expiry date (keyword-only) |
| `exchange` | `str` | `"NFO"` | Exchange code |

```python
from datetime import date
nifty_fut = session.future("NIFTY", expiry=date(2025, 7, 31))
```

**Error cases:** Invalid expiry or missing contract → lookup error.

**Broker compatibility:** All brokers (exchange-specific contracts vary).

### `option()`

```python
session.option(
    underlying: str,
    strike: Any,
    right: str,
    *,
    expiry: date,
    exchange: str = "NFO",
    leg: Any | None = None,
) -> Option
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `underlying` | `str` | — | Underlying symbol (e.g. `"NIFTY"`) |
| `strike` | `Any` | — | Strike price |
| `right` | `str` | — | `"CE"` or `"PE"` |
| `expiry` | `date` | — | Contract expiry date (keyword-only) |
| `exchange` | `str` | `"NFO"` | Exchange code |
| `leg` | `Any \| None` | `None` | Optional leg metadata |

```python
nifty_ce = session.option("NIFTY", 24500, "CE", expiry=date(2025, 7, 31))
nifty_pe = session.option("NIFTY", 24200, "PE", expiry=date(2025, 7, 31))
```

**Broker compatibility:** All brokers.

### `option_chain()`

```python
session.option_chain(
    underlying: str,
    *,
    expiry: date | int | str | None = None,
    exchange: str = "NSE",
) -> OptionChain
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `underlying` | `str` | — | Underlying symbol (e.g. `"NIFTY"`) |
| `expiry` | `date \| int \| str \| None` | `None` | Filter by expiry (None = nearest) |
| `exchange` | `str` | `"NSE"` | Exchange code |

Returns an `OptionChain` — a rich aggregate composed of `Option` instruments.
Access strikes via `chain.strikes`, ATM via `chain.atm`.

```python
chain = session.option_chain("NIFTY")
atm_ce = chain.atm  # -> Option at ATM strike
for strike_row in chain.strikes:
    print(strike_row.strike, strike_row.call.ltp, strike_row.put.ltp)
```

**Broker compatibility:** All brokers.

### `commodity()`

```python
session.commodity(symbol: str, *, expiry: date, exchange: str = "MCX") -> Commodity
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `symbol` | `str` | — | Commodity symbol (e.g. `"CRUDEOIL"`) |
| `expiry` | `date` | — | Contract expiry date (keyword-only) |
| `exchange` | `str` | `"MCX"` | Exchange code |

```python
crude = session.commodity("CRUDEOIL", expiry=date(2025, 8, 19))
```

**Broker compatibility:** Dhan (MCX), Upstox.

### `currency()`

```python
session.currency(symbol: str, exchange: str = "NSE") -> Currency
```

```python
usd_inr = session.currency("USDINR")
```

**Broker compatibility:** All brokers.

### `spot()`

```python
session.spot(symbol: str, exchange: str = "CDS") -> Spot
```

```python
gold_spot = session.spot("GOLD")
```

**Broker compatibility:** Dhan, Upstox.

---

## 3. Market Data

### `quote()`

```python
session.quote(instrument: Instrument) -> QuoteSnapshot
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `instrument` | `Instrument` | — | Any instrument object from a builder method |

Refreshes and returns the instrument's latest quote.

```python
stock = session.stock("RELIANCE")
q = session.quote(stock)
print(q.ltp, q.volume, q.change_pct)
```

**Error cases:** Network failure → raises transport error. Stale data possible
during market close.

**Broker compatibility:** All brokers.

### `history()`

```python
session.history(
    instrument: Instrument,
    timeframe: str = "1D",
    days: int = 120,
) -> HistoricalSeries
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `instrument` | `Instrument` | — | Any instrument object |
| `timeframe` | `str` | `"1D"` | Candle timeframe (`"1m"`, `"5m"`, `"15m"`, `"1D"`, etc.) |
| `days` | `int` | `120` | Number of calendar days of history |

Returns a `HistoricalSeries` containing OHLCV bars.

```python
stock = session.stock("RELIANCE")
bars = session.history(stock, timeframe="5m", days=5)
for bar in bars.bars:
    print(bar.event_time, bar.open, bar.high, bar.low, bar.close, bar.volume)
```

**Error cases:** Timeframe not supported by broker → raises error. Large
`days` values may hit broker rate limits.

**Broker compatibility:** All brokers. Available timeframes vary by broker.

---

## 4. Streaming

### `subscribe()`

```python
session.subscribe(
    instrument: Instrument,
    callback: Callable | None = None,
    *,
    depth: bool = False,
) -> SubscriptionHandle
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `instrument` | `Instrument` | — | Any instrument object |
| `callback` | `Callable \| None` | `None` | Callback for live ticks |
| `depth` | `bool` | `False` | Include market depth data |

Returns a subscription handle.

```python
stock = session.stock("RELIANCE")
handle = session.subscribe(stock, lambda tick: print(tick))

# With market depth
handle = session.subscribe(stock, depth=True)
```

**Error cases:** Broker doesn't support streaming → raises capability error.
WebSocket connection failure → raises transport error.

**Broker compatibility:** All brokers. Depth levels vary (Dhan: 20/200,
Upstox: 30).

### `unsubscribe()`

```python
session.unsubscribe(instrument: Instrument) -> None
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `instrument` | `Instrument` | — | The instrument to unsubscribe |

```python
session.unsubscribe(stock)
```

**Broker compatibility:** All brokers.

---

## 5. Trading

### `buy()`

```python
session.buy(
    instrument: Instrument,
    quantity: int,
    price: Decimal | None = None,
    order_type: str = "LIMIT",
    product_type: str = "INTRADAY",
) -> OrderResult
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `instrument` | `Instrument` | — | Any instrument object |
| `quantity` | `int` | — | Order quantity |
| `price` | `Decimal \| None` | `None` | Limit price (None for MARKET) |
| `order_type` | `str` | `"LIMIT"` | `"LIMIT"` or `"MARKET"` |
| `product_type` | `str` | `"INTRADAY"` | `"INTRADAY"`, `"CNC"`, `"MIS"`, etc. |

```python
from decimal import Decimal
stock = session.stock("RELIANCE")
result = session.buy(stock, 10, price=Decimal("2450.00"), order_type="LIMIT")
print(result.order_id)
```

**Error cases:** Insufficient funds → rejection. Invalid quantity → validation
error. Paper broker always succeeds.

**Broker compatibility:** All brokers. `product_type` values vary by broker.

### `sell()`

```python
session.sell(
    instrument: Instrument,
    quantity: int,
    price: Decimal | None = None,
    order_type: str = "LIMIT",
    product_type: str = "INTRADAY",
) -> OrderResult
```

Same parameters as `buy()`. Mirrors buy for sell-side orders.

```python
result = session.sell(stock, 10, price=Decimal("2480.00"))
```

### `orders()`

```python
session.orders() -> list[Any]
```

Returns open and recent orders from the session OMS spine.

```python
for order in session.orders():
    print(order.order_id, order.status, order.symbol)
```

### `cancel()`

```python
session.cancel(order_id: str) -> Any
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `order_id` | `str` | — | The order id to cancel |

```python
session.cancel("DHAN-12345")
```

### `modify()`

```python
session.modify(order_id: str, **changes: Any) -> Any
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `order_id` | `str` | — | The order id to modify |
| `**changes` | `Any` | — | Key-value pairs of fields to change |

```python
session.modify("DHAN-12345", price=Decimal("2460.00"), quantity=5)
```

---

## 6. Properties & Utilities

### `session`

```python
session.session -> DomainSession
```

Underlying composition-root session (escape hatch; prefer the object-level API).

### `broker_id`

```python
session.broker_id -> str
```

The broker plugin id string (e.g. `"paper"`, `"dhan"`, `"upstox"`).

### `account`

```python
session.account -> Any
```

Portfolio account — positions, holdings, funds.

### `runtime`

```python
session.runtime -> RuntimeBundle
```

Session-scoped runtime coordinators (subscribe/history/quote/execute).

### `universe`

```python
session.universe -> Universe
```

The instrument universe (symbol master).

### `provider`

```python
session.provider -> Any
```

The data provider for the session.

### `status`

```python
session.status -> Any | None
```

Current session status.

### `broker_capabilities()`

```python
session.broker_capabilities(symbol: str = "RELIANCE") -> dict[str, Any]
```

Full broker capability matrix + extension names.

### `instrument_id()`

```python
session.instrument_id(symbol: str, exchange: str = "NSE") -> str
```

Resolve symbol to canonical instrument id string.

### `close()`

```python
session.close() -> None
```

Close the session and release resources.

```python
session = BrokerSession("paper")
try:
    q = session.quote(session.stock("RELIANCE"))
finally:
    session.close()
```

---

## 7. Connection Modes

| Mode | Description | Credentials Required |
|---|---|---|
| `paper` | Simulated broker. Instant connect. Synthetic data. Paper orders. | No |
| `live` | Real broker. Full API access. Real orders. | Yes |
| `replay` | Replays historical data through the same pipeline. | No |

```python
# Paper mode (default)
session = BrokerSession("paper")

# Live mode with explicit credential loading
session = BrokerSession("dhan", mode="live")

# Replay mode
session = BrokerSession("paper", mode="replay")
```

---

## 8. Paper Broker Usage

The paper broker (`"paper"`) is a full-fidelity simulated broker that requires
no credentials, connects instantly, and generates synthetic market data.

```python
from brokers.session import BrokerSession

# 1. Connect — instant, no auth
session = BrokerSession("paper")

# 2. Build instruments
stock = session.stock("RELIANCE")

# 3. Get quotes (synthetic)
quote = session.quote(stock)
print(f"RELIANCE @ {quote.ltp}")

# 4. Trade (paper orders)
from decimal import Decimal
result = session.buy(stock, 10, price=Decimal("2450.00"))
print(f"Order placed: {result.order_id}")

# 5. Check orders
for o in session.orders():
    print(o.order_id, o.status)

# 6. Cleanup
session.close()
```

The paper broker is ideal for:
- Development and testing
- CI/CD pipelines
- Learning the SDK API
- Prototyping strategies before connecting a live broker

---

## 9. Error Handling Patterns

### Basic pattern

```python
from brokers.session import BrokerSession

try:
    session = BrokerSession("dhan", mode="live")
    q = session.quote(session.stock("RELIANCE"))
except ConnectionError as e:
    print(f"Connection failed: {e}")
    if hasattr(e, "remediation"):
        print(f"Hint: {e.remediation}")
except Exception as e:
    print(f"Unexpected error: {e}")
finally:
    session.close()
```

### Session status check

```python
session = BrokerSession("paper")
status = session.status
if status and not status.get("connected"):
    print(f"Not connected: {status.get('error')}")
    print(f"Fix: {status.get('remediation')}")
```

### Graceful degradation

```python
session = BrokerSession("paper")

# Quote may fail for some instruments
try:
    q = session.quote(session.stock("RELIANCE"))
except Exception:
    q = None

# History may be empty outside market hours
bars = session.history(session.stock("RELIANCE"), days=5)
if bars.bar_count == 0:
    print("No historical data available")
```

---

## Appendix: Complete API Surface

| Category | Method | Returns |
|---|---|---|
| Connection | `BrokerSession.connect(broker, **kw)` | `BrokerSession` |
| Builder | `session.stock(symbol, exchange)` | `Equity` |
| Builder | `session.equity(symbol, exchange)` | `Equity` |
| Builder | `session.etf(symbol, exchange)` | `ETF` |
| Builder | `session.index(name, exchange)` | `Index` |
| Builder | `session.future(symbol, *, expiry, exchange)` | `Future` |
| Builder | `session.option(underlying, strike, right, *, expiry, exchange, leg)` | `Option` |
| Builder | `session.option_chain(underlying, *, expiry, exchange)` | `OptionChain` |
| Builder | `session.commodity(symbol, *, expiry, exchange)` | `Commodity` |
| Builder | `session.currency(symbol, exchange)` | `Currency` |
| Builder | `session.spot(symbol, exchange)` | `Spot` |
| Data | `session.quote(instrument)` | `QuoteSnapshot` |
| Data | `session.history(instrument, timeframe, days)` | `HistoricalSeries` |
| Streaming | `session.subscribe(instrument, callback, *, depth)` | `SubscriptionHandle` |
| Streaming | `session.unsubscribe(instrument)` | `None` |
| Trading | `session.buy(instrument, quantity, price, order_type, product_type)` | `OrderResult` |
| Trading | `session.sell(instrument, quantity, price, order_type, product_type)` | `OrderResult` |
| Trading | `session.orders()` | `list[Any]` |
| Trading | `session.cancel(order_id)` | `Any` |
| Trading | `session.modify(order_id, **changes)` | `Any` |
| Property | `session.session` | `DomainSession` |
| Property | `session.broker_id` | `str` |
| Property | `session.account` | `Any` |
| Property | `session.runtime` | `RuntimeBundle` |
| Utility | `session.instrument_id(symbol, exchange)` | `str` |
| Utility | `session.broker_capabilities(symbol)` | `dict[str, Any]` |
| Utility | `session.close()` | `None` |
