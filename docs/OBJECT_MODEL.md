# TradeX object model (product API)

**Status:** Complete — including ConnectError, BrokerPlugin, paper LIMIT OPEN lifecycle, resolver/doctor · 2026-07-09  
**Prefer this path over gateways.** Transport lives under `brokers/`; strategies and notebooks should not import it.  
**Operating model:** [`docs/OPERATING_MODEL.md`](./OPERATING_MODEL.md) · **Epic 1 plan:** [`reports/EPIC_01_MARKET_ACCESS_PLAN.md`](../reports/EPIC_01_MARKET_ACCESS_PLAN.md)

Design detail: [`reports/OBJECT_MODEL_COMPLETION_DESIGN.md`](../reports/OBJECT_MODEL_COMPLETION_DESIGN.md)  
Safe-to-trade gate: [`reports/SAFE_TO_TRADE_GATE.md`](../reports/SAFE_TO_TRADE_GATE.md)  
Broker UX / naming / flows: [`reports/BROKER_UX_STANDARDIZATION_DESIGN.md`](../reports/BROKER_UX_STANDARDIZATION_DESIGN.md)

---

## Market Access (Epic 1)

Primary data path — no gateway imports, no OMS required for `mode="market"`:

```python
import tradex

session = tradex.connect("paper")  # or: tradex.connect("dhan", mode="market")
stock = session.universe.equity("RELIANCE")
stock.refresh()                                      # → QuoteSnapshot on instrument
print(stock.ltp, stock.bid, stock.ask, stock.spread())

series = stock.history(timeframe="1D", days=20)      # → HistoricalSeries
print(series.bar_count)

handle = stock.subscribe()                           # live updates into instrument state
# ...
if handle is not None:
    handle.unsubscribe()
session.close()
```

| Mode | Data | Orders |
|------|------|--------|
| `sim` (paper) | paper quotes / history / subscribe | OMS in-process |
| `market` (dhan/upstox) | live | **disabled** (`ORDERS_DISABLED`) |
| `trade` (dhan/upstox) | live / sandbox | process OMS **required** + allow-orders flag |

### Derivatives Greeks (DV-013)

```python
session = tradex.connect("paper")
chain = session.universe.index("NIFTY").option_chain()
print(chain.atm.greeks.delta, chain.atm.iv)   # ATM call greeks
print(chain.pcr(), chain.max_pain())
surface = chain.greeks()                      # GreeksSurface across strikes
session.close()
```

CI: `tests/e2e/test_derivatives_greeks.py`

### Automation (Epic 5 — product path)

```python
from decimal import Decimal
from domain.models.trading import SignalDTO
import tradex

session = tradex.connect("paper")
signal = SignalDTO(
    symbol="RELIANCE", exchange="NSE", side="BUY", signal_type="BUY",
    confidence=Decimal("0.9"), quantity=1, price=Decimal("1"),
)
stock = session.universe.equity(signal.symbol)
result = stock.buy(signal.quantity, price=signal.price, correlation_id="auto:1")

# Kill switch (OMS risk manager on paper spine)
rm = session.order_service.order_manager._risk_manager
rm.set_kill_switch(True)   # further buys rejected
rm.set_kill_switch(False)

session.close()
```

CI: `tests/e2e/test_automation_w3.py` · research: `tests/e2e/test_backtest_session_history.py`

### Sandbox order placement (product gate — not production money)

Dhan/Upstox **sandbox** is the deliberate environment for end-to-end order tests
(place / modify / cancel) without production capital risk.

| Requirement | Value |
|-------------|--------|
| Environment | `DHAN_ENVIRONMENT=SANDBOX` (use a dedicated env file, e.g. `.env.dhan.sandbox`) |
| Credentials | `DHAN_SANDBOX_CLIENT_ID` / `DHAN_SANDBOX_ACCESS_TOKEN` |
| Allow orders | `DHAN_ALLOW_LIVE_ORDERS=1` (name is historical — required for sandbox writes too) |
| OMS | Process OMS registered (CLI/API), or tests register via `register_oms_context` |
| Safety | Prefer far-from-market **LIMIT** + cancel; never enable allow-orders on LIVE casually |

```python
# Tests: tests/e2e/test_sandbox_product_orders.py  (-m sandbox)
session = tradex.connect("dhan", mode="trade", env_path=".env.dhan.sandbox")
stock = session.universe.equity("RELIANCE")
result = stock.buy(1, price=Decimal("1000"), correlation_id="sandbox:demo:1")
session.cancel(result.order.order_id)
```

Default CI does **not** place sandbox orders. Production LIVE should keep
`DHAN_ALLOW_LIVE_ORDERS=0` unless explicitly operating a live desk.

CI gate: `tests/e2e/test_market_access.py`. Live (opt-in): `tests/scenarios/test_live_l3_optional.py`.

---

## Quick start

```python
import tradex
from decimal import Decimal
from domain.instruments.display_names import parse_display_name, format_display_name

session = tradex.connect("paper")                    # mode=sim (default)
# session = tradex.connect("dhan", mode="market")    # live quotes; orders disabled
# session = tradex.connect("dhan", mode="trade")     # needs process OMS (CLI/API)

stock = session.universe.equity("RELIANCE")
stock.refresh()
print(stock.ltp, stock.bid, stock.ask, stock.spread())

# History facade (callable)
series = stock.history(timeframe="1D", days=20)
print(series.bar_count)

handle = stock.subscribe()
if handle is not None:
    handle.unsubscribe()

# Orders — sim/trade only (OMS); market mode raises ORDERS_DISABLED
result = stock.buy(1, price=Decimal("2500"), correlation_id="demo:1")

# TradeHull-style names ↔ canonical InstrumentId
iid = parse_display_name("NIFTY 21 NOV 24400 CALL", default_year=2026)
print(format_display_name(iid))  # NIFTY 21 NOV 24400 CALL

# Options
idx = session.universe.index("NIFTY")
chain = idx.option_chain()
if chain.atm:
    print(chain.atm.strike, chain.atm.moneyness(chain.spot or Decimal("0")))

print(session.status.mode, session.status.orders_enabled, session.status.trace_id)

# Batch quotes (still instrument-backed under the hood)
print(session.ltp_many(["RELIANCE", "NIFTY"]))
inst = session.resolve("NIFTY 21 NOV 24400 CALL")  # → stamped Option instrument

# Option chain helpers (Option objects, not dicts)
chain = session.option_chain("NIFTY", expiry=0)   # offset 0 = nearest
atm = chain.select_strikes("ATM")                 # atm.ce / atm.pe are Options
otm = chain.select_strikes("OTM", steps=5)

# Optional TradeHull-shaped aliases (thin; prefer Instrument API above)
ce, pe, k = session.dx.atm_strikes("NIFTY", expiry=0)

session.close()
```

Runnable smoke: `examples/object_model_quickstart.py`

---

## Mental model

```text
tradex.connect(broker, mode=sim|market|trade)
  → Session  (composition root: data + optional OMS + status)
       → Universe.equity / index / future / option
            → Instrument  (quote, history, subscribe, buy/sell)
                 → DataProvider / OrderServicePort (OMS)
                      → gateways (hidden)
```

| You write | You do **not** write |
|-----------|----------------------|
| `tradex.connect` | `DhanBrokerGateway` / `UpstoxBrokerGateway` |
| `session.universe.equity(...)` | raw REST / WebSocket clients |
| `instrument.buy(...)` | `gateway.place_order` without OMS |
| `instrument.history(...)` | broker historical JSON parsers |

### Connect modes

| Mode | Brokers | Data | Orders | OMS |
|------|---------|------|--------|-----|
| **`sim`** | paper (default) | paper | paper | in-memory |
| **`market`** | dhan / upstox (default) | live | **disabled** | not required |
| **`trade`** | dhan / upstox | live | live | **process OMS required** |

`connect("dhan")` works like paper for **reads** (auth + instruments + quotes).  
`mode="trade"` raises structured **`ConnectError(code="OMS_REQUIRED")`** unless CLI/API registered a process OMS.

Paper: **LIMIT** orders rest **OPEN** (cancel/modify work); **MARKET** fills immediately.

```python
from domain.connect_errors import ConnectError
try:
    tradex.connect("dhan", mode="trade")
except ConnectError as e:
    print(e.code, e.remediation, e.to_dict())

s = tradex.connect("paper")
print(s.doctor("RELINCE"))  # fuzzy → RELIANCE
```

---

## Session & Universe

| API | Role |
|-----|------|
| `tradex.connect("paper"\|"dhan"\|"upstox", mode=…)` | Build gateway, adapters, optional OMS; return domain `Session` |
| `session.status` | `mode`, `phase`, `orders_enabled`, `trace_id` |
| `session.universe.equity / etf / spot / currency` | Cash-like instruments (AssetKind) |
| `session.universe.index / future / commodity / option / get` | F&O + typed dispatch on `get(id)` |
| `session.orders()` | OMS book / EP order book list |
| `session.buy / sell / market / limit` | OrderIntent → OMS (blocked in market mode) |
| `parse_display_name` / `format_display_name` | TradeHull-style names ↔ `InstrumentId` |
| `session.resolve` / `instrument` | Display name → stamped `Instrument` |
| `session.ltp_many` / `quote_many` | Batch quotes via instruments / provider batch |
| `session.option_chain(name, expiry=0)` | Index → `OptionChain` (expiry offset OK) |
| `chain.select_strikes("ATM"\|"OTM"\|"ITM")` | Returns `StrikeSelection` with `Option` CE/PE |
| `session.dx.*` | Optional thin TradeHull aliases (not a god-object) |
| `session.cancel` / `session.modify` | OMS lifecycle (blocked in market mode) |
| `instrument.cancel` / `instrument.modify` | Same OMS path as place |
| `session.account` | `AccountView` — positions / holdings / funds / `Portfolio` |
| `instrument.broker.depth20/200/30` | Broker extensions (no gateway) |
| `session.activate()` | Nested ambient context for bare instruments |
| `session.close()` | Clears **this** session’s default provider only |

**Architecture rule:** DX helpers always resolve to **Instrument / OptionChain / OMS**.  
There is no parallel order path and no god-object broker SDK on the product surface.

### Broker extensions (no gateway in strategy code)

```python
session = tradex.connect("dhan", mode="market")
eq = session.universe.equity("RELIANCE")
eq.capabilities()          # ['depth_20', 'depth_200']
eq.broker.depth20()        # instrument-bound 20-level depth
eq.broker.depth200()       # instrument-bound 200-level depth
# Upstox: eq.broker.depth30()
```

Extensions are composition plugins stamped at connect; `instrument.broker` is a bound facade, not a gateway.

### Account & order lifecycle

```python
s = tradex.connect("paper")
eq = s.universe.equity("RELIANCE")
r = eq.buy(1, price=Decimal("100"), correlation_id="demo:1")
# Open orders (live limit): eq.modify(r.order.order_id, price=...); eq.cancel(...)
# Paper often fills immediately → cancel returns "Order already final"

acc = s.account.refresh()
print(acc.portfolio.total_pnl, acc.positions, acc.funds)
```

### Test pyramid

Scenario pack: `tests/scenarios/test_object_model_pyramid.py`  
Design: [`reports/OBJECT_MODEL_CAPABILITY_COMPLETION_DESIGN.md`](../reports/OBJECT_MODEL_CAPABILITY_COMPLETION_DESIGN.md)

| Layer | Marker / file | Scope |
|-------|---------------|--------|
| L0 | unit in scenario pack | Portfolio, names, TF |
| L1 | integration | OMS cancel/modify, AccountView, market block, Upstox adapter |
| L2 | e2e paper | connect, quote, place cycle, account |
| L3 | `@pytest.mark.live_readonly` | `tests/scenarios/test_live_l3_optional.py` (skip without env) |

### Asset kinds (PR-5)

```python
from domain.instruments.asset_kind import AssetKind

s.universe.etf("NIFTYBEES")
s.universe.commodity("CRUDEOIL", expiry=date(2026, 11, 19))  # MCX
s.universe.spot("USDINR")
s.universe.currency("USDINR")  # register_exchange("CDS") if needed
```

### Bare instruments (after connect)

```python
from domain.instruments.instrument import Equity

session = tradex.connect("paper")
# default provider + ambient set on construct
eq = Equity("RELIANCE")
eq.refresh()  # resolves default/ambient DataProvider

with session.activate():
    Equity("INFY").refresh()
```

Without a provider: `NotConfiguredError` (strict — no silent empty history).

---

## Instrument surface

### Market data

- `refresh()`, `quote` / `ltp` / `bid` / `ask` / `volume`
- `depth()` (also stores `market_depth` / `order_book`)
- `subscribe` / `unsubscribe` / `on_tick` / …
- `statistics()`, `snapshot()`, `serialize()`, `clone()`

### History facade

```python
inst.history(timeframe="5m", days=5)   # __call__ → download
inst.history.download(...)
inst.history.refresh()
inst.history.series / .downloaded
inst.history.resample("W")             # view cache only
inst.history.to_dataframe()
```

### Orders (OMS-only on instrument)

```python
inst.buy(qty, price=..., correlation_id=...)
inst.sell(...)
inst.market(qty, side="BUY")
inst.limit(qty, price, side="BUY")
inst.stop_loss(qty, trigger_price, side="SELL")
```

**Never** falls back to `ExecutionProvider`. Missing OMS → `NotConfiguredError`.

Live brokers: `use_oms=False` is rejected in `tradex.connect` (ENG-011).

### Broker extensions

```python
# capability-named methods when stamped by composition root
# inst.broker.depth20()   # example — only if extension registered
```

---

## OptionChain & derivatives

```python
# DV-010 / DV-011 product path (paper + live)
idx = session.universe.index("NIFTY")
chain = idx.option_chain()                 # or session.option_chain("NIFTY", expiry=0)
assert len(chain.strikes) >= 1
chain.atm / chain.calls / chain.puts
chain.pcr() / chain.max_pain() / chain.itm() / chain.otm()
atm = chain.select_strikes("ATM")          # StrikeSelection: .ce / .pe are Option
otm = chain.select_strikes("OTM", steps=2)
chain.atm.buy(...)   # OMS stamped (PR-3b)
```

Option / Future math (pure domain, no `analytics` import):

- `option.payoff`, `intrinsic_value`, `extrinsic_value`, `moneyness`
- `option.black_scholes`, `implied_volatility`
- `future.basis`, `cost_of_carry`, `rollover`, `continuous` (empty v1)

Implementation: `src/domain/instruments/derivatives_math.py`  
E2E gate: `tests/e2e/test_derivatives_object_model.py`

---

## Safe-to-trade (orders)

Every money path should hit:

1. Idempotency (`correlation_id`)
2. Risk / kill-switch
3. OMS book
4. Audit

Parity tests: `application/oms/tests/test_order_path_parity.py`  
Recon heal (opt-in): `TRADEX_RECONCILIATION_AUTO_REPAIR=1` — see safe-to-trade gate doc.

---

## Layers cheat sheet

| Package | Role |
|---------|------|
| `tradex` | Public connect + re-exports |
| `domain` | Instruments, ports, OMS intents |
| `application.oms` | OrderManager, risk, recon |
| `tradex.runtime` | Kernel (factory, quota, resilience) |
| `brokers.*` | Transport only |

---

## Deferred

- **PR-5+** ETF/Currency/Crypto/… factories — need explicit `AssetKind` + exchange masters  
- Instrument `event_bus` wiring on every refresh (platform test still xfail)  
- HTTP-level FastAPI order parity fixture (spine covered via `OmsOrderService`)
