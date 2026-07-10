# ADR-004: Event-Driven Domain

## Status
Superseded (2026-07-10 audit — see docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART6.md §4)

## Context
Domain transitions (quote updates, fills, subscription start/stop, order state
changes, market open/close) were observed through polling or direct coupling,
which made UI/analytics/telemetry hard to wire without entangling them with the
domain.

## Decision
Expand `domain/events/` into a full, **immutable** event catalog:
`QuoteChanged`, `TickReceived`, `DepthChanged`, `TradeExecuted`, `OrderPlaced`,
`OrderFilled`, `OrderRejected`, `OrderCancelled`, `PositionOpened`,
`PositionClosed`, `MarketOpened`, `MarketClosed`, `SubscriptionStarted`,
`SubscriptionStopped`, `HistoricalLoaded`, `ReplayStarted`, `ReplayFinished`.

Objects emit via a `DomainEventBus`; subscribers (UI, analytics, telemetry) attach
with no reverse dependency on the domain internals.

## Consequences
- Collaboration via events, not direct calls — supports UI/telemetry without
  coupling.
- Event payloads are frozen value objects.

## Superseded note

Verified against source during the 2026-07-10 architecture audit: none of
this ADR's prescribed event class names (`QuoteChanged`, `TickReceived`,
`OrderFilled`, `MarketOpened`, `MarketClosed`, `ReplayStarted`,
`ReplayFinished`, etc.) exist in the real event catalog. The actual
`EventType` enum in `domain/events/types.py` has 50+ members with different
names (`TICK`, `QUOTE`, `ORDER_PLACED`, `TRADE_FILLED`,
`POSITION_OPENED`/`POSITION_CLOSED`, and many more) that grew organically
rather than following this static list.

The *policy* this ADR states — event-driven collaboration, no reverse
dependency on domain internals, frozen event payloads — is correct and is
followed (newer events use frozen `TypedDomainEvent` subclasses). Treat
`domain/events/types.py` itself as the living source of truth for the
catalog going forward, not a list in this document, which will only drift
again. See `docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART3.md`
§2 for the verified, current catalog and a precise dead-member cleanup.
