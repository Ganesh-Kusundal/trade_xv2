# Institutional Broker SDK — Object Model Design

**Scope:** `brokers/` module and the public object model only. Not the rest of the
trading platform (risk, backtest, analytics pipelines are out of scope except where
an instrument object must hand off to them).

**Status:** Proposal — standalone design, written fresh against the mission brief.

**Philosophy:** A financial instrument is a living object. Developers write

```python
nifty = Equity("NIFTY")
nifty.quote
nifty.history("5m")
nifty.subscribe()
nifty.buy(50)
```

and never construct, import, or reason about a broker client, a REST endpoint, a
WebSocket frame, or a JSON payload. The broker is an implementation detail wired in
once, at the edge of the process, and never referenced again.

---

## 1. Domain object hierarchy

```
Instrument (abstract)
│
├── Equity
│     └── ETF
├── Index
├── Spot
│     └── Currency
├── Commodity
├── Future
│     └── ContinuousFuture      (rolling synthetic series over a Future chain)
├── Option
├── Crypto
├── Bond
└── SyntheticInstrument          (user-defined combination: spreads, baskets, pairs)

Supporting composites (not Instrument subclasses — they *compose* instruments):
├── OptionChain        (composes Option[])
├── FutureChain         (composes Future[])
└── Portfolio            (composes Instrument[] the account currently holds)
```

**Why this shape.** `Instrument` carries everything every tradable thing needs:
identity, a live quote, history, a subscription, an order-entry surface. Subtypes
add only the state and behavior that make them *that* kind of thing — an `Option`
adds strike/expiry/greeks, a `Future` adds expiry/basis, a `Bond` adds
coupon/yield/duration. `SyntheticInstrument` is the escape hatch: it lets a
strategy define `nifty_atm_straddle = SyntheticInstrument([long_call, long_put])`
and get `.quote`, `.pnl()`, `.greeks` for free by aggregating its legs, without the
core hierarchy needing to know about straddles, baskets, or spreads.

`OptionChain` and `FutureChain` are deliberately **not** `Instrument` subclasses —
an option chain isn't a tradable instrument, it's a collection of them. Modeling it
as a separate composite keeps `Instrument` a clean Liskov-substitutable type: any
code that accepts an `Instrument` (a pricer, a risk check, a scanner) works
identically for every leaf type.

---

## 2. Responsibilities of each object

| Object | Responsibility | Explicitly NOT responsible for |
|---|---|---|
| `Instrument` | Identity, current quote/depth state, history access, subscription lifecycle, order entry, serialization | Talking to a broker SDK, transport, auth, retries |
| `Equity` / `ETF` | Cash-market specialization (product types, corporate actions hooks) | Derivatives math |
| `Index` | Non-tradable reference underlying; quote/history/subscribe only | Order entry (raises `NotTradableError`) |
| `Spot` / `Currency` | Spot-market pricing, FX pair semantics | Settlement/delivery logistics |
| `Commodity` | Physical-commodity metadata (unit, delivery center) | — |
| `Future` | Expiry, lot size, basis/cost-of-carry, rollover | Pricing options on itself |
| `ContinuousFuture` | Stitches a `FutureChain` into one continuous series (back-adjusted or ratio-adjusted) | Placing orders (delegates to the *active* leg) |
| `Option` | Strike/expiry/right, greeks, IV, payoff, moneyness | Fetching the whole chain (that's `OptionChain`'s job) |
| `Crypto` | 24×7 session calendar, fractional lot sizing | — |
| `Bond` | Coupon, face value, yield-to-maturity, duration/convexity | — |
| `SyntheticInstrument` | Aggregate quote/greeks/pnl across constituent legs | Placing a single atomic broker order (places N leg orders, or one combo order where the broker supports it) |
| `OptionChain` | Own a set of `Option` objects for an underlying + expiry; chain-level analytics | Owning per-option state (delegates to each `Option`) |
| `FutureChain` | Own a set of `Future` objects for an underlying; calendar-spread helpers | — |
| `Portfolio` | Snapshot of instruments currently held, aggregated P&L | Order placement (delegates to each instrument) |

Every object owns exactly the state that is *intrinsically its own*. Nothing owns a
connection, a token, or a socket — that's infrastructure, and infrastructure is
injected, never constructed by the domain object.

---

## 3. Complete public API

### 3.1 `Instrument` base surface

```python
class Instrument(ABC):
    # identity
    id: InstrumentId
    symbol: str
    exchange: str
    canonical_symbol: str
    asset_kind: AssetKind

    # exchange metadata
    tick_size: Decimal
    lot_size: int
    freeze_quantity: int | None
    circuit_limits: tuple[Decimal, Decimal] | None
    trading_session: TradingSession

    # market information (properties — read current state, no I/O)
    quote: Quote | None
    ltp: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    spread: Decimal | None
    ohlc: OHLC | None
    vwap: Decimal | None
    previous_close: Decimal | None
    average_price: Decimal | None

    # market activity
    volume: int
    trades: int
    open_interest: int | None
    market_depth: MarketDepth | None
    order_book: MarketDepth | None          # alias of market_depth

    # behaviors
    def refresh(self) -> Instrument: ...             # pull fresh quote+depth, mutate self, return self
    def snapshot(self) -> InstrumentSnapshot: ...     # immutable point-in-time copy of all state
    def statistics(self) -> Statistics: ...
    def serialize(self) -> dict: ...
    def clone(self) -> Instrument: ...

    # history — see §8
    history: HistoricalSeries                        # callable-property, see below

    # live data — see §9
    def subscribe(self, mode: SubscribeMode = "quote") -> Subscription: ...
    def unsubscribe(self) -> None: ...
    is_live: bool
    last_tick: Tick | None
    tick_stream: Iterator[Tick]
    candle_stream: Iterator[Candle]
    def on_tick(self, fn: Callable[[Tick], None]) -> Unsubscribe: ...
    def on_quote(self, fn: Callable[[Quote], None]) -> Unsubscribe: ...
    def on_depth(self, fn: Callable[[MarketDepth], None]) -> Unsubscribe: ...
    def on_disconnect(self, fn: Callable[[DisconnectReason], None]) -> Unsubscribe: ...
    def on_reconnect(self, fn: Callable[[], None]) -> Unsubscribe: ...

    # orders — broker-agnostic
    def buy(self, qty: int, **kw) -> Order: ...
    def sell(self, qty: int, **kw) -> Order: ...
    def market(self, qty: int, side: Side, **kw) -> Order: ...
    def limit(self, qty: int, price: Decimal, side: Side, **kw) -> Order: ...
    def stop_loss(self, qty: int, trigger: Decimal, side: Side, **kw) -> Order: ...
    def cover(self, qty: int, price: Decimal, trigger: Decimal, side: Side) -> Order: ...
    def bracket(self, qty: int, price: Decimal, target: Decimal, stop_loss: Decimal, side: Side) -> Order: ...
    order: OrderDesk                                  # stock.order.buy(...) alternate spelling

    # analytics
    indicators: IndicatorSet
    signals: SignalSet
    tags: set[str]
    metadata: dict[str, Any]

    # broker capability escape hatch — see §6
    broker: BrokerCapabilities
```

### 3.2 `Option` additions

```python
class Option(Instrument):
    strike: Decimal
    expiry: date
    option_type: Literal["CE", "PE"]
    underlying: Instrument
    greeks: Greeks                     # .delta .gamma .theta .vega .rho
    iv: Decimal
    intrinsic_value: Decimal
    extrinsic_value: Decimal
    moneyness: Literal["ITM", "ATM", "OTM"]

    def delta(self) -> Decimal: ...
    def gamma(self) -> Decimal: ...
    def theta(self) -> Decimal: ...
    def vega(self) -> Decimal: ...
    def black_scholes(self, **overrides) -> Decimal: ...
    def payoff(self, spot: Decimal) -> Decimal: ...
    def pnl(self, entry_price: Decimal, qty: int) -> Decimal: ...
    def implied_volatility(self, market_price: Decimal) -> Decimal: ...
```

### 3.3 `Future` additions

```python
class Future(Instrument):
    expiry: date
    underlying: Instrument
    basis: Decimal
    cost_of_carry: Decimal
    roll_yield: Decimal

    def rollover(self) -> Future: ...          # next-expiry Future, same underlying
    def continuous(self) -> ContinuousFuture: ...
```

### 3.4 `OptionChain`

```python
class OptionChain:
    underlying: Instrument
    expiries: list[date]
    calls: list[Option]
    puts: list[Option]
    atm: Option
    itm: list[Option]
    otm: list[Option]

    def expiry(self, offset_or_date: int | date) -> OptionChain: ...  # re-slice to one expiry
    def strike(self, k: Decimal, right: Literal["CE","PE"]) -> Option: ...
    def greeks(self) -> pd.DataFrame: ...
    def iv_surface(self) -> pd.DataFrame: ...
    def max_pain(self) -> Decimal: ...
    def pcr(self) -> Decimal: ...            # put-call ratio (OI-weighted)
    def subscribe(self) -> Subscription: ...  # one multiplexed handle for every leg
```

### 3.5 Entry point — no gateway anywhere

```python
import brokersdk

brokersdk.connect("dhan", **credentials)     # composition root, called once
# or, scoped:
with brokersdk.session("upstox", **credentials) as market:
    nifty = market.equity("NIFTY 50")

nifty = Equity("RELIANCE")          # resolves against the last/active session
```

`connect()`/`session()` are the *only* place a broker name is typed. Everything
downstream is a domain object.

---

## 4. State owned by each object

State ownership is single-writer: exactly one object is the source of truth for
each fact, everything else reads through it.

| State | Owner | Notes |
|---|---|---|
| Identity (symbol, exchange, token) | `Instrument` | immutable value object, set at construction |
| Current quote / OHLC / VWAP | `Instrument` | replaced atomically on `refresh()` or tick |
| Market depth | `Instrument` | replaced atomically on `depth()` or depth tick |
| Subscription lifecycle | `Subscription` (owned *by* the instrument, 1:1) | instrument holds the handle; no global subscription registry |
| Historical bars | `HistoricalSeries` (owned *by* the instrument) | lazily populated, self-caching |
| Greeks / IV | `Option` | derived from its own quote + chain snapshot, not fetched separately |
| Strike/expiry/right | `Option` | immutable |
| Basis / cost of carry | `Future` | derived on read from its own `ltp` + underlying `ltp` |
| Chain membership (`calls`, `puts`, `atm`) | `OptionChain` | recomputed from its owned `Option` list, never duplicated on the underlying |
| Broker capability set | `BrokerCapabilities` (owned by the session, exposed per-instrument) | never mutates the base `Instrument` |
| Auth/session/token | Infrastructure (composition root) | **never** touches a domain object |

No global mutable dictionaries, no module-level caches keyed by symbol. If two
`Equity("RELIANCE")` objects exist, they are independent snapshots unless the
factory that produced them explicitly interns instruments (recommended for
subscription de-duplication — see §9.3).

---

## 5. Composition relationships

```
OptionChain ── composes ──▶ Option (1..N)
Option ── composes (back-reference) ──▶ underlying Instrument
Future ── composes (back-reference) ──▶ underlying Instrument
ContinuousFuture ── composes ──▶ FutureChain
SyntheticInstrument ── composes ──▶ Instrument (2..N legs) + weights
Portfolio ── composes ──▶ Instrument (N, currently held)
Instrument ── composes ──▶ HistoricalSeries (1:1, owned)
Instrument ── composes ──▶ Subscription (0..1, owned, created on subscribe())
Instrument ── composes ──▶ BrokerCapabilities (1:1, injected, read-only view)
```

Composition, not inheritance, is used everywhere a "has-a" relationship exists.
The only inheritance in the system is the `Instrument` hierarchy itself (an `is-a`
relationship: an `Option` genuinely *is* an `Instrument`). Chains, portfolios, and
synthetics are compositions over instruments, never subclasses of them — this is
what lets `chain.calls[0].subscribe()` and `nifty.subscribe()` share one identical
implementation.

Bidirectional navigation is supported explicitly rather than via shared mutable
state: `option.underlying` returns the same interned `Instrument` the chain was
built from; `underlying.option_chain(expiry)` builds (or returns a cached)
`OptionChain` — the link is a value reference, not a live callback wired into the
underlying.

---

## 6. Broker capability extension architecture

The core `Instrument` API is 100% broker-agnostic. Broker-specific power features
are reached through exactly one seam: `instrument.broker`.

```python
class BrokerCapabilities:
    """Returned by `instrument.broker`. Only exposes what the active broker supports."""

    def __getattr__(self, name: str) -> Callable:
        if name not in self._supported:
            raise CapabilityNotSupportedError(
                f"{self._broker_name} does not support '{name}'. "
                f"Supported: {sorted(self._supported)}"
            )
        return self._bound(name)

    def supports(self, name: str) -> bool: ...
    def list(self) -> list[str]: ...
```

Usage:

```python
nifty.broker.depth20()                 # Dhan
nifty.broker.market_feed()             # Dhan
nifty.broker.order_update_stream()     # Dhan

reliance.broker.depth30()              # Upstox
reliance.broker.option_greeks_stream() # Upstox
reliance.broker.full_market_quote()    # Upstox

tcs.broker.depth5()                    # Zerodha
```

**Capability Pattern, not decorator-stacked subclasses.** A broker registers a set
of named capabilities against a small `Capability` interface:

```python
class Capability(Protocol):
    name: str
    def bind(self, instrument: Instrument) -> Callable: ...

class DhanDepth20(Capability):
    name = "depth20"
    def bind(self, instrument):
        return lambda: self._transport.depth20(instrument.id)
```

At session construction the broker adapter declares `capabilities() -> list[Capability]`;
`instrument.broker` is a thin, stateless view that looks up the session's registered
capabilities and binds them to `self` on access. Adding a new broker feature means
registering one new `Capability` — **zero changes** to `Instrument`, `Equity`,
`Option`, or any other domain class. This satisfies Open/Closed directly: the base
hierarchy is closed for modification, capabilities are open for extension.

Why not the decorator pattern (`DhanDepth20(Instrument)` wrapping a base
instrument)? Because decorator-stacking forks object identity — `isinstance` checks,
equality, and `__hash__` all become ambiguous once an instrument might or might not
be wrapped, and every new capability combination multiplies the number of concrete
types in play. A flat capability registry keyed by name avoids that combinatorial
blowup and keeps every `Instrument` the same concrete class regardless of which
broker produced it.

---

## 7. OptionChain design

`OptionChain` is a first-class composite object, not a DataFrame of raw rows.

```python
chain = nifty.option_chain(expiry="2026-07-31")

chain.calls            # list[Option], each a full Instrument
chain.puts
chain.atm               # Option nearest to spot
chain.itm                # list[Option]
chain.otm                # list[Option]
chain.expiries           # list[date] available for this underlying
chain.greeks()            # pd.DataFrame indexed by strike
chain.iv_surface()         # pd.DataFrame: strike × expiry → IV
chain.max_pain()
chain.pcr()
chain.subscribe()          # one Subscription multiplexing every leg's ticks
```

**Construction.** `OptionChain.build(underlying, expiry, capabilities)` fetches the
strike ladder once from the broker's option-chain endpoint, then constructs one
`Option` per strike/right via the same instrument factory used everywhere else —
there is no separate "chain row" type that later needs converting into an
`Option`. Each `Option` is fully live: `chain.calls[3].subscribe()` behaves
identically to subscribing to a standalone `Option`.

**Refresh semantics.** `chain.refresh()` re-fetches the strike ladder and
greeks/IV in one batched call, then updates each owned `Option` in place (same
object identity, new state) — code holding a reference to `chain.atm` before and
after `refresh()` sees the same object with updated numbers, not a stale copy.

**ATM/ITM/OTM are computed properties**, not cached fields: they re-derive from
`underlying.ltp` and each `Option.strike` on every access, so they're always
consistent with the latest known spot even between explicit `refresh()` calls.

**Subscription fan-out.** `chain.subscribe()` opens (or reuses) one shared
market-data stream and multiplexes ticks to each leg's own `Subscription` —
subscribing to a 40-leg chain does not open 40 sockets; see §9.3.

---

## 8. Historical and live data lifecycle

### 8.1 Historical (`instrument.history`)

`history` is a callable property — accessing it returns a `HistoricalSeries` bound
to the instrument; calling it fetches/filters:

```python
series = nifty.history(timeframe="5m", days=20)   # pandas-like frame, indexed by time
series = nifty.history.cached()                     # whatever is already in memory, no I/O
series = nifty.history.download(timeframe="1D", days=365)  # forces a broker fetch
series = nifty.history.refresh()                    # extend the cached range to "now"
series = nifty.history.resample("15m")               # derive a new timeframe from cached ticks/1m bars
series = nifty.history.indicators(["ema20", "rsi14"]) # attach computed columns
```

**Lifecycle.**

1. First call with a given `timeframe` triggers a broker fetch through the
   session's historical provider; the resulting bars are cached **on the
   instrument's owned `HistoricalSeries`**, not in a module-level cache.
2. Subsequent calls with an overlapping or narrower range are served from cache
   with no I/O.
3. `refresh()` fetches only the delta since the last cached bar and appends —
   never re-downloads the full range.
4. `resample()` and `indicators()` operate purely on the cached frame; they never
   trigger I/O.
5. Cache eviction is time-bounded (configurable TTL per timeframe) and instrument
   scoped — destroying the instrument releases its history.

### 8.2 Live (`instrument.subscribe()`)

```python
sub = nifty.subscribe(mode="quote")   # or mode="depth", mode="full"
nifty.is_live            # True
nifty.last_tick           # most recent Tick
for tick in nifty.tick_stream:        # blocking iterator, for scripts/notebooks
    ...
nifty.on_tick(lambda t: ...)          # callback, for event-driven code
nifty.unsubscribe()
```

**Lifecycle.**

1. `subscribe()` asks the session's `StreamRegistry` (§9) for a socket that already
   carries this instrument's symbol on this account, or opens one.
2. Every tick/quote/depth frame that arrives for this instrument's identity is
   routed to **this instrument only** — `Instrument.refresh()`'s in-memory state
   is updated in place, callbacks fire, `tick_stream`/`candle_stream` iterators
   yield.
3. `on_disconnect()`/`on_reconnect()` fire from the shared connection's state
   machine (§9.2), not from the instrument — the instrument only cares that its
   own subscription paused/resumed.
4. `unsubscribe()` removes this instrument's interest from the shared socket; the
   socket itself is torn down only when its last interested instrument
   unsubscribes.

---

## 9. Subscription architecture

### 9.1 `Subscription` as a first-class object

```python
class Subscription:
    instrument_id: InstrumentId
    mode: SubscribeMode
    started_at: datetime
    is_active: bool
    tick_count: int
    def unsubscribe(self) -> None: ...
```

Returned by `instrument.subscribe()` and owned 1:1 by the instrument that created
it. It is a handle, not a socket — sockets are shared infrastructure below it.

### 9.2 Connection sharing — `StreamRegistry` + `ConnectionPool`

Users never construct a WebSocket. Internally:

```
StreamRegistry (per session)
  ├── owns N ConnectionPool entries, one per (broker, feed-type, account)
  ├── multiplexes many Instrument subscriptions onto few physical sockets
  └── exposes a State machine per connection: CONNECTING → LIVE → DEGRADED → RECONNECTING → CLOSED
```

- A single WebSocket per broker feed-type carries every subscribed instrument's
  symbol, up to the broker's per-socket symbol limit; the registry opens
  additional sockets only when that limit is hit.
- Reconnection is handled once, centrally, with backoff — every instrument
  subscribed on that socket receives `on_disconnect()`/`on_reconnect()` without
  re-subscribing manually; the registry re-sends the symbol list on reconnect.
- The registry deduplicates: two different `Instrument` objects (or two calls to
  `subscribe()` on the same instrument) for the same `(symbol, exchange, mode)`
  share one upstream subscription and are fanned out locally — this is what makes
  `chain.subscribe()` for 40 legs cheap.

### 9.3 State machine

```
CONNECTING → LIVE → DEGRADED (missed heartbeat) → RECONNECTING → LIVE
                                                  ↘ CLOSED (explicit unsubscribe / fatal auth error)
```

Represented explicitly (State pattern) so `instrument.is_live` and
`on_disconnect`/`on_reconnect` are simple projections of one authoritative state
machine per connection, not ad hoc booleans scattered across instruments.

---

## 10. Internal package organization

```
brokersdk/
  __init__.py                 # connect(), session() — the ONLY broker-name surface
  instruments/
    base.py                    # Instrument ABC + shared state (Quote, MarketDepth, ...)
    equity.py  index.py  spot.py  currency.py  commodity.py  crypto.py  bond.py
    future.py  continuous_future.py
    option.py
    synthetic.py                # SyntheticInstrument
    factory.py                   # InstrumentFactory — the only place concrete types are constructed
  chains/
    option_chain.py
    future_chain.py
  portfolio/
    portfolio.py
  history/
    series.py                    # HistoricalSeries — cache, resample, indicators
    provider.py                   # HistoricalDataProvider protocol (strategy)
  streaming/
    subscription.py                # Subscription (per-instrument handle)
    stream_registry.py              # multiplexing, dedup
    connection_pool.py               # socket lifecycle
    connection_state.py               # State pattern
  capabilities/
    protocol.py                        # Capability Protocol
    registry.py                         # per-session capability catalog
    facade.py                            # BrokerCapabilities (instrument.broker)
  orders/
    order_desk.py                         # stock.order.*, stock.buy()/sell()/...
  analytics/
    greeks.py  black_scholes.py  indicators.py  statistics.py
  value_objects/
    quote.py  depth.py  candle.py  instrument_id.py  trading_session.py
  _internal/                               # transport, invisible to users
    broker_adapters/
      dhan/  upstox/  zerodha/  paper/
        adapter.py                          # implements DataProvider + ExecutionProvider + Capability[]
        auth.py  transport.py  mappers.py
    session.py                                # composition root: builds adapters, wires factory
    provider_protocols.py                       # DataProvider / ExecutionProvider / HistoricalDataProvider
  serialization/
    codec.py
  cache/
    lru_time_bounded.py
```

**Rule enforced by this layout:** anything under `_internal/` may import broker
SDKs, `requests`/`aiohttp`, and websocket libraries. Nothing outside `_internal/`
is allowed to. A lint rule (import-linter contract) makes this structural, not
just conventional.

---

## 11. Design pattern justification

| Pattern | Where | Why here specifically |
|---|---|---|
| **Composition over inheritance** | `OptionChain` composes `Option[]`; `Instrument` composes `HistoricalSeries`/`Subscription` | Keeps the `Instrument` hierarchy shallow and Liskov-clean; avoids a combinatorial subclass explosion for chain × broker × capability |
| **Strategy** | `HistoricalDataProvider`, `Capability`, pricing engines (`black_scholes` vs future pricing models) | Lets a new broker or a new pricing model be swapped in without touching `Instrument` |
| **Adapter** | `_internal/broker_adapters/*` | Normalizes each broker's REST/WS payloads into the shared value objects (`Quote`, `MarketDepth`, `Candle`) before anything domain-level sees them |
| **Abstract Factory** | `InstrumentFactory` | Single choke point that decides *which* concrete `Instrument` subclass to build from raw instrument-master metadata; brokers never construct domain objects directly |
| **Capability / plugin registry** (not GoF Decorator) | `capabilities/registry.py` | Broker superpowers are additive facts looked up by name, not wrapper classes — see §6 for why decorator-stacking was rejected here |
| **Observer** | `on_tick`/`on_quote`/`on_depth`/`on_disconnect`/`on_reconnect`, `StreamRegistry` fan-out | Ticks are pushed, not polled; one upstream event fans out to N interested instruments |
| **State** | `ConnectionState` machine (§9.3) | Connection status and reconnection are inherently stateful; making it explicit avoids scattered boolean flags |
| **Flyweight** | Exchange metadata, trading-calendar, symbol-master lookups | Tick size, lot size, and holiday calendars are identical across every instance of a symbol — shared, not duplicated per `Instrument` |
| **Repository** | `HistoricalSeries` cache + symbol-master lookup | Isolates "where did this bar/metadata come from and is it still fresh" from the domain object's public API |
| **Facade** | `OptionChain.subscribe()`, `instrument.broker` | Hides N sockets behind one call; hides "does this broker even support this" behind one attribute |
| **Value Object** | `Quote`, `MarketDepth`, `Candle`, `InstrumentId`, `Greeks` | Immutable, replaced-not-mutated snapshots — makes "state lives on the object, replaced atomically" (mission §Instrument State) implementable without locking games |

---

## 12. Extension guidelines

**Adding a new broker.**
1. Implement `DataProvider`, `ExecutionProvider`, and (optionally) `HistoricalDataProvider`
   under `_internal/broker_adapters/<broker>/adapter.py`.
2. Declare `capabilities() -> list[Capability]` for anything beyond the base
   `Instrument` surface (custom depth levels, broker-specific streams).
3. Register the adapter with `brokersdk.connect("<broker>", ...)`.
4. **Zero changes** to `instruments/`, `chains/`, or `history/`.

**Adding a new instrument type** (e.g. a new derivative class).
1. Subclass `Instrument` under `instruments/`, adding only the state/behavior
   unique to that type.
2. Register it in `InstrumentFactory` against the `AssetKind`/metadata pattern
   that identifies it from the symbol master.
3. If it needs a chain concept, add a composite under `chains/` following the
   `OptionChain` shape (owns a list of the new type, exposes chain-level analytics).

**Adding a new exchange.**
1. Add exchange metadata (calendar, tick/lot rules) to the Flyweight registry.
2. No instrument or broker-adapter code changes — exchange is a property on
   `InstrumentId`, resolved through the shared metadata registry.

**Adding a new analytics capability** (e.g. a new indicator, a new pricing model).
1. Add it under `analytics/` as a pure function or `Strategy` implementation.
2. Expose it via `instrument.indicators`/`instrument.history.indicators()` or, for
   pricing, as an optional override argument to the relevant method (e.g.
   `option.black_scholes(model=...)`).
3. Never touch `instruments/base.py` — analytics are consumers of instrument state,
   not owners of it.

**Adding a new broker-specific power feature to an existing broker.**
1. Add one `Capability` implementation.
2. Register it in that broker's `capabilities()` list.
3. Available immediately as `instrument.broker.<name>()` for every instrument that
   broker's session produces — no other file changes.

**Hard rule for every extension path above:** if a change requires touching
`instruments/base.py` or any concrete `Instrument` subclass to support one new
broker, one new exchange, or one new capability, the extension point is wrong and
should route through `capabilities/`, `InstrumentFactory`, or the Flyweight
metadata registry instead. This is the Open/Closed boundary the whole design is
built to protect.
