# ADR-011: Domain Event Canonical Import Paths

**Status**: Accepted  
**Date**: 2026-07-02  
**Authors**: Chief Quant Architect  
**Labels**: architecture, domain, events

## Context

`DomainEvent` and `EventType` were defined in `domain/events/types.py` but were commonly imported from `infrastructure/event_bus/__init__.py`, which re-exported them for convenience. This created a systematic architectural violation: the application layer (35+ files) imported domain types from the infrastructure layer, inverting the dependency direction.

The confusion arose because `infrastructure.event_bus` re-exported `DomainEvent` alongside `EventBus`, making it a convenient single import point. However, this convenience came at the cost of architectural clarity — consumers couldn't distinguish domain types from infrastructure types.

## Decision

Establish `domain.events.types` as the **canonical import path** for all domain-level event types:

```python
# Canonical (correct)
from domain.events.types import DomainEvent, EventType
from infrastructure.event_bus import EventBus  # Infrastructure stays separate
```

The `infrastructure.event_bus` package continues to re-export `DomainEvent` for backward compatibility, but all production code and tests should use the canonical domain path.

**Rule of thumb:** Domain types (events, entities, value objects, ports) are always imported from `domain.*`. Infrastructure services (event bus, persistence, logging) are imported from `infrastructure.*`.

## Consequences

### Positive
- Clear separation between domain types and infrastructure services
- Application layer imports follow correct dependency direction
- New developers can easily identify the owning layer of any type

### Negative
- Split imports require two lines instead of one in some cases
- Existing code using the convenience path needs gradual migration

### Risks
- Re-export path remains functional — linter enforcement needed to prevent regression

## Alternatives Considered

### Alternative 1: Move DomainEvent to infrastructure.event_bus
**Why Rejected**: Domain events are domain concepts, not infrastructure. The event bus is infrastructure; the event type definitions belong in the domain.

### Alternative 2: Create a shared types package
**Why Rejected**: Unnecessary abstraction. The domain layer already serves as the shared kernel.

## Implementation Notes

- [x] Update all application layer production imports
- [x] Update all test file imports
- [x] Update API and script imports
- [ ] Add import-linter rule to enforce canonical domain event paths
- [ ] Deprecate re-export from infrastructure.event_bus

## Related ADRs

- [ADR-001](./ADR-001-domain-single-source.md) — Domain as single source of truth
- [ADR-010](./ADR-010-exception-hierarchy-domain.md) — Exception hierarchy in domain

---
