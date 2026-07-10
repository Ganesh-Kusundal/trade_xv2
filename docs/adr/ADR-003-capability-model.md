# ADR-003: Capability Model — No Broker Conditionals

## Status
Superseded (2026-07-10 audit — see docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART6.md §4)

## Context
Optional, broker-specific features (market depth levels, bracket orders, live
greeks, baskets) were previously accessed via string-keyed `get_extension(...)`
calls that leaked broker names and made capability discovery ad hoc.

## Decision
Domain defines **capability ABCs** in `src/domain/capabilities/`
(e.g. `DepthCapability`, `BracketOrderCapability`, `OptionGreeksCapability`,
`BasketOrderCapability`, `StreamingCapability`, `OrderUpdateCapability`).

Plugins implement them (e.g. `DhanDepthCapability`, `UpstoxDepth30Capability`)
and register them in a `CapabilityRegistry`. An `Instrument` exposes
`instrument.capabilities.<capability>(...)` — typed, discoverable, and broker-free.

The legacy `domain/extensions/*` is moved + renamed to `domain/capabilities/*`;
the old `get_extension("depth_200")` string API is replaced by
`instrument.capabilities.depth(levels=200)`.

## Consequences
- Capability availability is discovered, not hard-coded per broker.
- Upstox (which previously had zero extensions) gains `depth_30` + `full` via the
  same mechanism as Dhan.
- No `if broker == "dhan"` anywhere in domain/app.

## Superseded note

Verified against source during the 2026-07-10 architecture audit: this
ADR's specific plan — moving `domain/extensions/*` into `domain/capabilities/*`
and replacing `get_extension("depth_200")` with a typed
`instrument.capabilities.depth(levels=200)` — was never built. Both
directories exist today, serving different purposes:

- `domain/extensions/` (10 files: `facade.py`, `broker_bundle.py`,
  `super_order.py`, `forever_order.py`, `news.py`, etc.) is the real,
  actively-developed broker-extension system. The real API is
  `instrument.broker.depth20()` / `instrument.get_extension(name)`.
- `domain/capabilities/` (3 files) holds a separate concept: the
  `BrokerCapabilities` / rate-limit / historical-window-constraint model.

Neither the "no broker conditionals" nor the "capability discovery, not
hard-coding" *intent* of this ADR was violated — it's the specific
mechanism (the rename, the typed accessor) that never landed. See
`docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART4.md` §1.2 for
what the current, working capability model actually looks like.
