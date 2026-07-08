# ADR-003: Capability Model — No Broker Conditionals

## Status
Accepted (Phase 0)

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
