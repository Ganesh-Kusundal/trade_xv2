# ADR-001: Event-Driven Cross-Context Communication

## Status

Proposed

## Date

2026-07-12

## Context

TradeXV2 currently uses a mix of direct method calls and an event bus for cross-module communication. The event bus (`infrastructure.event_bus.EventBus`) supports publish/subscribe with dead-letter queues and deduplication, but many components still call each other directly, creating tight coupling.

Key observations:
- `domain/events/types.py` (1,008 lines) contains all event types in a single monolithic file
- The event bus is well-implemented (DLQ, dedup, alerting) but underutilized
- Some application services import other application services directly (e.g., OMS → execution, streaming → market data)
- The `domain.events.bus.DomainEventBus` ABC exists but is not consistently used

## Decision

All cross-bounded-context communication will use domain events published through the event bus. Direct method calls are permitted only within a bounded context.

### Event Schema

Events are `dataclass` instances inheriting from `DomainEvent`:

```python
@dataclass
class DomainEvent:
    event_type: str
    event_id: str
    timestamp: datetime
    correlation_id: str
    payload: dict
```

### Event Splitting

The monolithic `domain/events/types.py` will be split into per-context event modules:
- `domain/instruments/events.py` — InstrumentLoaded, InstrumentRefreshed
- `domain/orders/events.py` — OrderRequested, OrderFilled, OrderCancelled
- `domain/positions/events.py` — PositionOpened, PositionClosed
- `domain/market_data/events.py` — QuoteUpdated, TickReceived
- `domain/accounts/events.py` — BalanceUpdated, HoldingChanged

Backward-compatibility aliases in `domain/events/types.py` will be maintained for 2 major versions.

### Event Versioning

Events include a `schema_version` field. New fields are always optional. Old fields are deprecated over 2 versions before removal.

## Consequences

### Positive
- Loose coupling between bounded contexts
- Better testability (mock the event bus, not the dependent service)
- Natural audit trail via event log
- Support for replay and recovery
- Clear producer/consumer relationships

### Negative
- Increased async complexity (events are fire-and-forget)
- Eventual consistency (state may be briefly inconsistent across contexts)
- Harder to trace causation chains (mitigated by correlation_id)
- Event schema evolution requires tooling

### Mitigations
- Correlation IDs on all events for tracing
- Event log with replay capability for debugging
- Schema versioning with backward compatibility
- Architecture fitness tests to prevent direct cross-context calls

## Alternatives Considered

1. **Direct method calls everywhere** — Simple but creates tight coupling. Rejected because it prevents independent deployment of bounded contexts.
2. **CQRS from the start** — Too complex for current scale. Can be introduced incrementally later.
3. **Message queue (RabbitMQ/Kafka)** — Over-engineering for a single-process trading system. The in-process event bus is sufficient.

## References

- `src/domain/events/types.py` — Current event types
- `src/domain/events/bus.py` — Domain event bus port
- `src/infrastructure/event_bus/event_bus.py` — Event bus implementation
- `tests/architecture/test_domain_isolation.py` — Domain isolation tests
