# ADR-002: EventBus with Dead Letter Queue — Never Swallow Failures

## Status

Accepted

## Context

Event-driven systems must guarantee that failed events are not silently dropped. In a trading platform, a lost `ORDER_PLACED` or `TRADE_FILLED` event can cause position drift, missed reconciliations, or silent capital exposure. The original implementation had no structured failure handling — handler exceptions could swallow events entirely.

## Decision

The `EventBus` (canonical home: `infrastructure/event_bus/event_bus.py`) implements:

1. **Dead Letter Queue (DLQ):** Any handler that raises an exception causes the event to be routed to a `DeadLetterQueue` with the original event, exception info, and timestamp. Events are never silently discarded.
2. **Managed service lifecycle:** EventBus exposes `as_managed_service()` / `EventBusAlertingService` so the `LifecycleManager` can track health, alert on DLQ backlog, and coordinate shutdown (TOS-P7-003).
3. **Event type enforcement:** When `enforce_event_types=True`, the bus warns on unknown `EventType` values (caught in `test_domain_ports_forbid_tradex_imports.py`).
4. **Crash-recovery persistence:** Event log persistence is configurable via `ResilienceConfig.event_log_enabled`.

### Capital-path guarantee

On money paths (order placement, fill processing), the OMS **must** attempt event publishing. The `test_fail_closed_capital_paths.py` guardrail verifies that `_publish`/`publish` is called in the order lifecycle and that the DLQ exists.

## Consequences

**Positive:**
- No silent event loss — every failure is visible, logged, and recoverable.
- DLQ provides a replay mechanism for debugging event processing failures.
- Managed service integration allows lifecycle-aware alerting.

**Negative:**
- DLQ consumers must be implemented and monitored (operational requirement).
- DLQ capacity planning is needed to avoid unbounded memory/disk growth.

## Enforcement

- `tests/architecture/test_fail_closed_capital_paths.py` — verifies `_publish`/`publish` exists in order lifecycle, DLQ exists, managed service pattern present
- `tests/architecture/test_import_direction_and_layering.py` — no imports from deprecated `brokers.common.event_bus` path
