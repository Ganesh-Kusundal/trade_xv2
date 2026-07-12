# ADR-012: CQRS Command & Query Dispatchers

- **Status:** Accepted
- **Date:** 2026-07-10
- **Deciders:** Chief Quant Architect, Head of Trading Systems, Platform Engineering Director

## Context

The proposed Trading OS diagram shows `CMD` and `QUERY` as first-class Runtime
Kernel components feeding the Event Bus and the SDK/CLI/API. The existing
`Trade_XV2` codebase had no formal dispatchers: "commands" were in-process
domain objects (`OmsOrderCommand`) passed directly to `OrderManager.place_order`,
and "queries" were ad-hoc (`QueryExecutor`, manager getters). There was no
router by type, and no single seam enforcing "strategies never call brokers
directly."

We needed a thin, explicit CQRS layer that:
1. routes intent by type,
2. keeps the critical trading path synchronous and deterministic,
3. keeps the read path strictly side-effect free,
4. delegates all real work to existing domain services (no logic duplication).

## Decision

Introduce two synchronous dispatchers in `src/runtime/commands` and
`src/runtime/queries`:

- **`CommandDispatcher`** — routes a `Command` to a handler by `command_type`,
  returns a `CommandResult` synchronously. After a successful handler result, it
  publishes the command's optional `to_event()` on the bus. The bus is the async
  fan-out; it is never the return path.
- **`QueryDispatcher`** — routes a `Query` to a read-only handler by `query_type`,
  returns a `QueryResult`. Handlers MUST NOT mutate state or publish events.

Handlers are thin adapters over existing services: `OrderCommandHandler` ->
`OrderManager.place_order`, `PortfolioQueryHandler` -> `PositionManager`,
`CandleQueryHandler` -> `QueryExecutor`. No business logic moves into the
dispatcher.

### Critical-path rule

`CommandDispatcher.dispatch` is synchronous. `OrderManager.place_order` already
holds its lock only for idempotency + order-book mutation and runs risk check +
broker I/O + event publishing outside the lock. The dispatcher wraps this
without adding async — determinism and latency are preserved.

### Contract enforcement

A new import-linter contract forbids `runtime.commands` and `runtime.queries`
from importing `brokers.*`. This hardens the "brokers never called directly by
strategies/application code" rule at the CI level.

### Composition-root wiring (P2 / P3)

- `tradex.session.open_session` builds the dispatchers and attaches them to
  `DomainSession` via `attach_command_dispatcher` / `attach_query_dispatcher`.
  The `domain` layer stays independent (no `domain -> runtime` import); the
  composition root (`tradex`, which is allowed to import both `domain` and
  `runtime`) owns the wiring. `Session.place()` routes an `OrderIntent` through
  an injected `order_command_fn` closure (built by the composition root), and
  subscribe/history commands route through the session `DataProvider`.

### ResilienceConfig application (P4 follow-up)

`runtime.resilience.ResilienceConfig` is the single visible knob for the
resilience subsystem. `infrastructure.bootstrap.build_event_bus` /
`build_async_event_bus` / `build_production_event_bus` accept it and apply:
- `event_log_enabled` -> `EventBus.logging_enabled` (crash-recovery persistence),
- `idempotency_ttl_seconds` -> `EventBus` duplicate-suppression cache size,
- `max_async_bus_queue` -> `AsyncEventBus` bounded queue (backpressure).

The composition roots (`interface/ui/services/broker_service.py`,
`runtime/composition.py`) build the bus via `ResilienceConfig.from_env()`, so the
resilience knobs are no longer scattered env-var reads. The `idempotency_backend`
field is reserved for when the `IdempotencyService` (Redis/file) is wired into
the OMS path (currently the OMS uses its in-process `IdempotencyGuard`).
- `TradingOrchestrator` receives an injected `order_command_fn` **closure**
  built by `TradingRuntimeFactory` from a `CommandDispatcher`. The orchestrator
  does NOT import `runtime.commands` — this avoids an `application -> runtime`
  cycle (since `runtime` already imports `application`). The closure keeps all
  `runtime.commands` knowledge in the `runtime` layer while still enforcing
  "strategies never call the OMS/broker directly."

## Consequences

**Positive**
- Explicit routing seam; SDK/CLI/API/UI all dispatch through one path.
- Read path is provably side-effect free (asserted in tests).
- No duplication of domain logic; existing managers remain owners of behavior.
- Broker isolation enforced by CI, not convention.

**Negative / trade-offs**
- One more indirection layer for command/query entry points.
- Handlers must be registered at the composition root (`tradex.session`).

## Alternatives considered

- **Async command bus:** rejected — would break the deterministic critical path.
- **Separate event-sourced projection store for queries:** rejected — reuse
  `PositionManager` / `QueryExecutor` as read models (ponytail: no gold-plating).
