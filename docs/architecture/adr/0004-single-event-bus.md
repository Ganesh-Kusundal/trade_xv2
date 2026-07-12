# ADR-004: Single event-bus stack

- **Status:** Proposed
- **Date:** 2026-07-12
- **Deciders:** Architecture review

## Context
Two event-bus implementations coexist: `event_bus.py` (sync) and `async_event_bus.py`
(`src/infrastructure/event_bus/`, 8 files), plus `ProcessedTradeRepository` overlapping
the idempotency service (`src/infrastructure/idempotency/`). Maintaining two stacks
doubles failure modes and dead-letter handling.

## Decision
One canonical `EventBus` core (sync, thread-safe, dead-letter by default). `AsyncEventBus`
becomes a thin facade over that core (queue adapter), not a parallel implementation.
`ProcessedTradeRepository` is merged into `IdempotencyService` (which already supports
Memory/File/Redis). Public `DomainEventBus` port is unchanged.

## Consequences
- Positive: one failure path; one dead-letter story; less code.
- Negative: async callers must route through the facade; mechanical change.
- Cost: removal of the parallel stack (Phase 5, P5-5).

## Validation
- Architecture test asserts only one `EventBus` implementation is importable as the
  canonical bus. Idempotency path count drops to one.

## Status (contract present 2026-07-12)
- **Status:** Accepted (contract); implementation deferred to G5 / P5-5.
- The canonical event-bus contract already exists as pure domain ports:
  `EventPublisher` and `EventBusPort` in `src/domain/ports/event_publisher.py`. The
  concrete `infrastructure.event_bus.EventBus` implements `EventBusPort`; the
  `AsyncEventBus` is a thin wrapper. `application` depends on the port, not the
  concrete class.
- The remaining work (P5-5) is collapsing the dual stacks (sync `event_bus.py` +
  `async_event_bus.py`) and the duplicate idempotency/`ProcessedTradeRepository`
  into one implementation each. No new port added — the contract is already present.
