# Plan: Object‑Centric Broker Model (no gateway)

**Status:** SUPERSEDED (2026-07-09) · Keep for historical context only.

**Replaced by (2026-07-10):** the `brokers/session` + `brokers/runtime` +
`brokers/extensions` layout described in `README.md`. The decorator-stacked
instrument approach was dropped in favor of capability query +
`DataProvider`/`ExecutionProvider` ports (ENG-041), and the public surface is
now `BrokerSession` over the existing rich `domain` objects.

> **Architecture board decision (ENG-041):** Do **not** implement decorator-stacked
> instruments (`DhanDepth20(Instrument)` wrappers). Use capability query +
> `DataProvider`/`ExecutionProvider` ports. Prefer `tradex.connect` + domain
> `Instrument` / `Session` (already implemented). See
> `reports/ENGINEERING_BACKLOG.md` and `reports/ARCHITECTURE_REVIEW_BOARD_2026-07-09.md`.

**Original status was:** Proposal · **Scope:** `brokers/` + `domain/` · **Depends on:** existing
`brokers/*` adapters are demoted to *transports* (non‑breaking).

> The current system is gateway‑centric: one `MarketDataGateway` (and per‑broker
> subclasses) exposes `history()`, `quote()`, `depth()`, `option_chain()` as
> free methods on a fat facade. This plan replaces the *gateway* with **objects**:
> a `Stock`/`Equity`/`Option`/`Future`/`Spot` is a first‑class citizen that owns
> its own state and data methods, a `BrokerSession` is just the authenticated
> *transport*, and broker‑specific superpowers (Dhan depth‑20/200, Upstox
> depth‑30/"new") are layered with the **decorator** pattern. Chains are built by
> **composition**.

---

## 1. Guiding principles

1. **API → Objects, not API → Gateway.** A broker connection is a transport; the
   value objects the user touches are instruments.
2. **State lives on the object.** An `Equity` remembers its last quote, last
   depth, subscription handle, and dirty flags — no external caching dict.
3. **Broker differences are additive.** Base instrument = vanilla
   quote/history/LTP. Broker extras = decorators that *wrap* the same object and
   add `depth_20()`, `depth_200()`, `depth_30()`, `greeks_live()`, etc.
4. **Chains are composites.** `OptionChain` *composes* an underlying `Stock` and a
   collection of `Option` objects; `FutureChain` composes `Future` objects.
5. **Non‑breaking.** Existing gateway/adapter code becomes the `Transport`
   layer. We add objects on top; we do not delete the gateway in v1.

---

## 2. Layered architecture

```
┌──────────────────────────────────────────────────────────────┐
│  USER / STRATEGY CODE                                          │
│     nifty = dhan.stock("NIFTY 50")                             │
│     chain = nifty.option_chain("2026-07-31")                   │
│     nifty.subscribe(on_tick=...)                               │
└───────────────┬──────────────────────────────────────────────┘
                │  builds / decorates
┌───────────────▼──────────────────────────────────────────────┐
│  OBJECT LAYER  (new)                                           │
│     Instrument (ABC)                                           │
│       ├─ Equity, Spot, Future, Option                          │
│       ├─ Depth20Instrument, Depth200Instrument  (decorators)   │
│       └─ Depth30Instrument, UpstoxFullInstrument (decorators)  │
│     OptionChain, FutureChain  (composites)                     │
│     InstrumentFactory / Broker.universe                        │
└───────────────┬──────────────────────────────────────────────┘
                │  delegates to
┌───────────────▼──────────────────────────────────────────────┐
│  TRANSPORT LAYER  (reuses existing code, no gateway API)       │
│     BrokerSession  → holds auth + http/ws clients              │
│     DhanTransport / UpstoxTransport  → thin wrappers over      │
│       existing adapter.py / gateway.py internals               │
└───────────────────────────────────────────────────────────────┘
```

The word "gateway" disappears from the public surface. `BrokerSession` is what
you construct once (replacing `UpstoxBrokerGateway(...)`); from it you get
objects.

---

## 3. Core object model

### 3.1 `Instrument` — the universal base

```python
class Instrument(ABC):
    # ── identity / state (owned by the object) ──
    id: InstrumentId                 # exchange, symbol, token, instrument_key
    broker: BrokerSession
    _last_quote: Quote | None = None
    _last_depth: MarketDepth | None = None
    _subscriptions: dict[str, SubHandle] = field(default_factory=dict)

    # ── data methods (sync + async variants) ──
    def history(self, timeframe="1D", lookback_days=...) -> pd.DataFrame: ...
    def quote(self) -> Quote: ...
    def ltp(self) -> Decimal: ...
    def ohlc(self, date) -> Candle: ...

    # ── live subscriptions (return handles, store on self) ──
    def subscribe(self, mode="LTP", on_tick=None) -> SubHandle: ...
    def subscribe_depth(self, levels=5, on_depth=None) -> SubHandle: ...
    def unsubscribe(self, handle) -> None: ...

    # ── lifecycle ──
    def refresh(self) -> "Instrument": ...     # pull quote+depth now
    def as_decorated(self, *ext): "Instrument": ...  # apply broker decorators
```

Every subtype *is* an `Instrument`, so anything that accepts an `Instrument`
(option pricer, risk engine, scanner) works for equities, futures, options.

### 3.2 Subtypes — `Equity`, `Spot`, `Future`, `Option`

```python
class Equity(Instrument):            # cash equity, e.g. RELIANCE
    product_type = "CNC"/"MIS"
    def holdings(self): ...          # composes broker.portfolio

class Spot(Instrument):              # spot commodity / currency
    ...

class Future(Instrument):            # single futures contract
    expiry: date; lot_size: int; underlying: Instrument
    def rollover(self) -> "Future": ...   # returns next expiry Future
    def basis(self) -> Decimal: ...       # spot−future

class Option(Instrument):            # single option contract
    strike: Decimal; right: "CE"|"PE"; expiry: date
    underlying: Instrument            # composition link back to Stock
    def greeks(self) -> Greeks: ...
    def intrinsic(self) -> Decimal: ...
    def iv(self) -> Decimal: ...
```

`Option` and `Future` **compose** their `underlying` so chains can navigate both
ways (option → underlying spot/future; underlying → its chain).

---

## 4. Broker extension via **Decorator**

The decorator wraps an `Instrument` and adds broker‑specific methods while
remaining an `Instrument` (Liskov‑safe). This is the key answer to *"depth 20/200
for dhan, depth 30 and new for upstox"*.

```python
class DepthCapableInstrument(Instrument):       # abstract decorator base
    def __init__(self, wrapped: Instrument):
        self._w = wrapped
    # forward identity + base methods to self._w
    def quote(self): return self._w.quote()
    # new capability:
    @abstractmethod
    def depth(self, levels: int) -> MarketDepth: ...
```

Concrete Dhan decorators (reuse existing `brokers/dhan/depth_20.py`,
`depth_200.py`, `depth_feed_base.BinaryDepthFeed`):

```python
class DhanDepth20(DepthCapableInstrument):
    name = "dhan.depth_20"
    def depth(self, levels=20): return self._w.broker.transport.depth20(self._w.id)
    def subscribe_depth(self, levels=20, on_depth=None):
        return self._w.broker.transport.stream_depth20(self._w.id, on_depth)

class DhanDepth200(DepthCapableInstrument):
    name = "dhan.depth_200"
    def depth(self, levels=200): return self._w.broker.transport.depth200(self._w.id)
    def subscribe_depth(self, levels=200, on_depth=None): ...
```

Concrete Upstox decorators (reuse `brokers/upstox/websocket/market_data_v3.py`):

```python
class UpstoxDepth30(DepthCapableInstrument):
    name = "upstox.depth_30"
    def depth(self, levels=30): ...          # full market quote (30 levels)
    def subscribe_depth(self, levels=30, on_depth=None): ...

class UpstoxFull(DepthCapableInstrument):     # the "new" feed
    name = "upstox.full"
    def depth_full(self): ...                 # enriched quote + full depth
    def greeks_live(self): ...                # live option greeks stream
```

**Why decorator and not subclass?** A `RELIANCE` equity is the *same object*
regardless of which capability bundle is layered. The factory decides at
runtime which decorators to apply based on `broker.capabilities()` — you never
fork the class hierarchy per broker. Multiple decorators stack:

```python
reliance = dhan.stock("RELIANCE").as_decorated(DhanDepth200, DhanSuperOrder)
# relyance is still an Instrument, now with .depth(levels=200) and super orders
```

This generalizes the existing `brokers/common/extensions` registry into a
first‑class object layer.

---

## 5. Composition — `OptionChain` and `FutureChain`

```python
class OptionChain:
    underlying: Stock                 # COMPOSITION: the chain owns the stock
    expiry: date
    options: list[Option]             # each Option composes the same underlying
    _fetched_at: datetime

    # build / refresh
    @classmethod
    def fetch(cls, underlying: Stock, expiry: str, broker) -> "OptionChain": ...
    def refresh(self) -> "OptionChain": ...

    # navigation (composition gives O(1) views)
    def call_at(self, strike) -> Option | None: ...
    def put_at(self, strike) -> Option | None: ...
    def nearest_otm(self, right) -> Option: ...
    def strikes(self) -> list[Decimal]: ...
    def expiries(self) -> list[date]: ...

    # analytics assembled from composed Options
    def pcr(self) -> Decimal: ...
    def max_pain(self) -> Decimal: ...
    def max_oi_strike(self, right) -> Decimal: ...
    def total_oi(self, right) -> int: ...
    def greeks_surface(self) -> pd.DataFrame: ...
    def subscribe(self, on_tick=None) -> SubHandle:   # multi-leg subscription
```

```python
class FutureChain:
    underlying: Stock
    futures: list[Future]
    def nearest(self) -> Future: ...
    def calendar_spread(self, near, far) -> Spread: ...
```

The **underlying `Stock`** is a real `Equity`/`Spot` object reused everywhere —
the chain does not re‑fetch identity; it *composes* the instrument. An `Option`
knows its `underlying`, so `option.underlying.option_chain(expiry)` round‑trips.

---

## 6. Factory / entry point (`BrokerSession`)

Replaces gateway construction. Builds objects and applies broker decorators.

```python
class BrokerSession:
    def __init__(self, broker: str, **auth):
        self.transport = _build_transport(broker, **auth)   # old gateway internals
        self._caps = self.transport.capabilities()

    def stock(self, symbol, exch=DEFAULT_EXCHANGE) -> Equity:
        base = Equity(id=resolve(symbol), broker=self)
        return self._decorate(base)

    def option(self, symbol, expiry, strike, right) -> Option: ...
    def future(self, symbol, expiry) -> Future: ...
    def option_chain(self, underlying, expiry) -> OptionChain:
        return OptionChain.fetch(self.stock(underlying), expiry, self)

    def _decorate(self, inst: Instrument) -> Instrument:
        # apply only decorators the broker supports
        if "depth_200" in self._caps: return DhanDepth200(inst)
        if "depth_30"  in self._caps: return UpstoxDepth30(inst)
        return inst
```

Usage:

```python
dhan = BrokerSession("dhan", **creds)
nifty = dhan.stock("NIFTY 50")
chain = nifty.option_chain("2026-07-31")     # composite
ce_25000 = chain.call_at(25000)              # Option (composes nifty)
ce_25000.subscribe(on_tick=print)            # live, handle stored on object
hist = ce_25000.history("5m", lookback_days=5)
print(chain.pcr(), chain.max_pain())
```

---

## 7. Patterns summary

| Concern | Pattern | Where |
|---|---|---|
| Instrument + broker capability | **Decorator** | `DhanDepth200`, `UpstoxDepth30` wrap `Instrument` |
| Chain built from instruments | **Composition** | `OptionChain(underlying, options)` |
| Underlying ↔ derivative link | **Composition / bidirectional ref** | `Option.underlying`, `Stock.chain()` |
| Capability bundle selection | **Factory + Strategy** | `BrokerSession._decorate` by `caps` |
| Object keeps its own data | **Stateful object** (no anemic model) | `_last_quote`, `_subscriptions` |
| Transport reuse (non‑breaking) | **Adapter** | old gateway → `Transport` |
| Multi‑leg live feed | **Facade** | `OptionChain.subscribe` hides N streams |

---

## 8. Proposed file layout (new, additive)

```
brokers/
  common/
    objects/
      instrument.py        # Instrument ABC + state + base methods
      equity.py  spot.py  future.py  option.py
      decorators/
        depth_capable.py   # abstract decorator base
        dhan_depth20.py  dhan_depth200.py
        upstox_depth30.py upstox_full.py
      chains/
        option_chain.py  future_chain.py
      session.py          # BrokerSession factory
      transports/
        base.py           # BrokerTransport ABC (old gateway internals)
        dhan_transport.py upstox_transport.py
  dhan/  upstox/  paper/   # unchanged; only wrapped by transports
```

---

## 9. Migration strategy (non‑breaking)

1. Add `brokers/common/objects/*` (no imports of it yet elsewhere).
2. Wrap existing `gateway.py`/`adapter.py` internals behind `BrokerTransport`.
3. `BrokerSession` uses the *already‑written* `brokers/dhan/depth_20.py`,
   `depth_200.py`, `depth_feed_base.py` and `brokers/upstox/websocket/*`.
4. Keep `MarketDataGateway` working; mark `BrokerSession` as the preferred
   public API. Deprecate gateway over 1–2 releases (mirrors existing
   `gateway.extended` deprecation approach).
5. Port `OptionChain`/`FutureChain` analytics from `domain/aggregates/option_chain.py`
   to *use* composed `Option` objects instead of raw `OptionContract` rows.

---

## 10. Open extensions (deliberately left for later — YAGNI now)

- `Strategy`/scan objects that consume `Instrument` collections.
- Caching decorator (`CachedInstrument`) as yet another decorator.
- Cross‑broker arbitrage object composing two `BrokerSession`s.
- Paper‑broker `Instrument` backed by `brokers/paper/*` transport.
