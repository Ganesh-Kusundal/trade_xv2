# ADR-010: Split events/types.py by Bounded Context

## Status

Proposed

## Context

The current `domain/events/types.py` file contains the `EventType` enum and `DomainEvent` class with all event types defined in a single enum. As the platform grows, this becomes a coordination bottleneck: every new event type requires editing a shared enum, and unrelated event types (market data, order lifecycle, system events) are co-located.

The `test_domain_ports_forbid_tradex_imports.py` test verifies that `canonical_event_types()` includes all required event types (`QUOTE`, `DEPTH_20`, `DEPTH_200`, `TRADE_FILLED`), but the single-enum approach creates coupling.

## Decision

Split the monolithic `EventType` enum into **per-context event type registries**:

1. **Market data events:** `TICK`, `QUOTE`, `DEPTH_20`, `DEPTH_200`, `TRADE_FILLED`, `CANDLE`
2. **Order lifecycle events:** `ORDER_PLACED`, `ORDER_MODIFIED`, `ORDER_CANCELLED`, `ORDER_REJECTED`, `EXECUTION_RECEIVED`
3. **System events:** `SUBSCRIPTION_STARTED`, `SUBSCRIPTION_ENDED`, `HEALTH_CHECK`, `ERROR`
4. **Reconciliation events:** `POSITION_SNAPSHOT`, `EXECUTION_LEDGER_ENTRY`

Each context defines its own event types in a sub-module of `domain/events/`:

```
domain/events/
├── __init__.py          # Re-exports DomainEvent, canonical_event_types()
├── types.py             # DomainEvent base class (stays)
├── market_data.py       # MarketDataEventType enum
├── order.py             # OrderEventType enum
├── system.py            # SystemEventType enum
└── reconciliation.py    # ReconciliationEventType enum
```

The `canonical_event_types()` function continues to return a unified set for validation, but each context only imports its own enum.

## Consequences

**Positive:**
- Reduces merge conflicts when adding event types.
- Each context owns its events, enabling independent evolution.
- Smaller files are easier to review and test.

**Negative:**
- Event consumers that handle multiple contexts need multiple imports.
- `canonical_event_types()` must aggregate all registries (registration pattern).
- Migration period where both old and new paths exist.

## Enforcement

- `tests/architecture/test_domain_ports_forbid_tradex_imports.py` — `test_market_bridge_event_types_in_canonical_enum`
- **NEW:** `tests/architecture/test_event_type_context_isolation.py` (proposed)
