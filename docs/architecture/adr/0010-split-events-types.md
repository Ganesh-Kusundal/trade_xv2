# ADR-0010: Split the `domain/events/types.py` monolith

- **Status:** Accepted
- **Date:** 2026-07-12
- **Deciders:** Architecture review
- **Supersedes:** implicit monolith in `src/domain/events/types.py`

## Context
`src/domain/events/types.py` had grown to **1008 LOC** and mixed three concerns in one
file: the `DomainEvent` base + `EventType` enum, the concrete event payload dataclasses,
and the typed-event subclasses. A 1008-LOC module is hard to review, raises the
architecture-test LOC flag, and couples event *definitions* to event *payloads*.

## Decision
Decompose `types.py` into focused, single-responsibility modules under `src/domain/events/`:

| Module | LOC | Responsibility |
|---|---|---|
| `types.py` | 200 | `DomainEvent` (frozen dataclass) + `EventType` enum — the stable contract |
| `payloads.py` | 330 | Event payload dataclasses (order/trade/position/quote/etc.) |
| `typed_events.py` | 274 | Typed `DomainEvent` subclasses wired to payloads + event type |
| `trade_id.py` | 75 | `TradeId` value object (extracted from inline id handling) |
| `bus.py` / `null_bus.py` | 27 / 20 | `DomainEventBus` impl + null object (bus, not part of the split but co-located) |

The public surface (`DomainEvent`, `EventType`, the typed-event classes, `DomainEventBus`
port) is unchanged — this was a pure internal move, no caller edits required.

## Consequences
- Positive: each module is reviewable; only `types.py` is the stability boundary;
  LOC gate no longer trips on this file.
- Negative: imports that did `from domain.events.types import X` for a payload/typed event
  now reference the correct submodule. Mechanical, covered by tests.
- Cost: none (deferred-refactor style; shipped directly).

## Validation
- `tests/architecture/test_file_size_limit.py` now passes for `events/types.py` (200 LOC).
- Full `tests/architecture` + `pytest tests/domain` green.
- Grep confirms no new cross-module import regressions.

## Status
- **Accepted and implemented** (commit `d944328d refactor(domain): split events/types.py
  (1008→200 LOC) per ADR-010`). This ADR document was written retroactively to record the
  decision that the commit referenced.
