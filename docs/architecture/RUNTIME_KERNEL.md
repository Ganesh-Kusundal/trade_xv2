# Runtime Kernel — Composition Roots, Not a Monolith

The proposed Trading OS diagram shows a single **"Trading Runtime Kernel"**
box containing Bootstrap, DI, Plugin Registry, Clock, Config, Session Manager,
Event Bus, Command Dispatcher, and Query Dispatcher. In the implemented
`Trade_XV2` codebase there is **no single `Runtime` class** that owns all of
these. Instead, the kernel is a set of *composition-root modules* that wire
dependencies together at process start. This document maps the diagram's kernel
box to the real code.

## What the "kernel" actually is

| Diagram node | Real module(s) | Role |
|---|---|---|
| Bootstrap | `tradex/session.py` (`open_session`), `runtime/api_bootstrap.py` | Entry points that build a wired `Session` / API app |
| DI | `infrastructure/di.py` (`Container`) | Thread-safe singleton/transient/request container |
| Plugin Registry | `infrastructure/broker_plugin.py` (`BrokerPlugin`, `register_broker_plugin`) | Self-registering broker metadata |
| Clock / Virtual Clock | `infrastructure/time/clock.py`, `domain/runtime/virtual_clock.py` | Wall + replay clocks |
| Config | `runtime/production_config.py`, `infrastructure/config` | Env-driven production validation |
| Session Manager | `application/oms/context.py` (`TradingContext`), `tradex/session.py` | Owns OMS/position/risk managers + event bus |
| Event Bus | `infrastructure/event_bus/` (`EventBus`, `AsyncEventBus`) | Sync dispatch + async background fan-out |
| Command Dispatcher | `runtime/commands/` (`CommandDispatcher`) | Synchronous intent routing (ADR-012) |
| Query Dispatcher | `runtime/queries/` (`QueryDispatcher`) | Synchronous read-only routing (ADR-012) |
| Resilience | `runtime/resilience.py` (`ResilienceConfig`) | Visible kernel dependency aggregating idempotency/DLQ/event-log/parity |

## Wiring paths

There are two independent composition roots; both are legitimate and must not
be merged into a monolith:

1. **SDK / CLI / API (direct):** `tradex.open_session(...)` builds the
   `DomainSession`, wires the `CommandDispatcher` + `QueryDispatcher` onto it,
   and returns. This is the path `tradex.connect(...)` uses.

2. **Runtime (broker service):** `runtime.factory.build` (ADR-017) delegates to
   `TradingRuntimeFactory.build_from_broker_service`, which takes an
   already-built `BrokerService`, runs the parity gate, builds the
   `TradingOrchestrator` (injecting the CQRS `order_command_fn` closure), and
   returns a `Runtime` dataclass. The `Runtime` object is a *wiring result*,
   not a service locator.

**Ledger authority:** `runtime.ledger_policy.resolve_execution_ledger` wires
`SqliteExecutionLedger` only when `TRADEX_LEDGER_AUTHORITY=1` (default off,
ADR-015 shadow cutover).

## Layering rules (enforced by import-linter)

- `domain` must not import `runtime`, `infrastructure`, `application`, etc.
  ("Domain independence"). So `DomainSession` only *stores* the dispatchers; it
  never imports `runtime.commands`.
- `application` must not import `runtime` in a way that creates a reverse cycle.
  The orchestrator receives an injected `order_command_fn` closure built by the
  `runtime` layer, so `runtime.commands` knowledge stays in `runtime`.
- `runtime` may import `application` and `infrastructure` (it is the top of the
  composition stack).
- `runtime.commands` / `runtime.queries` must not import `brokers.*`
  ("Dispatcher broker isolation" contract).

## Why this shape

A single `Runtime` god-object would concentrate wiring logic and make the SDK
path and the broker-service path diverge. Keeping the kernel as composition
roots preserves:

- **Testability** — each root can be built in isolation with fakes.
- **Incremental delivery** — new dispatchers/handlers register at the root
  without touching domain or application code.
- **Architectural regression safety** — import-linter fails CI if any layer
  reaches across a forbidden boundary.
