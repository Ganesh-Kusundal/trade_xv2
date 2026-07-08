# ADR-004: Event-Driven Domain

## Status
Accepted (Phase 0)

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
