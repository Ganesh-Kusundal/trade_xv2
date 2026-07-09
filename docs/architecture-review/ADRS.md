# Architecture Decision Records — TradeXV2

Status legend: **Proposed** (awaiting approval) · Accepted · Deprecated.

---

## ADR-001 — Make architecture guardrails truthful (enable internal-import analysis)
- **Status:** Proposed
- **Context:** `lint-imports` exits 0 while `tests/test_architecture.py` fails on
  `brokers.common → brokers.dhan/upstox`. The violations are lazy (in-function) imports,
  invisible to import-linter's default top-level analysis. The guardrail is currently
  unreliable, so refactors cannot be verified.
- **Decision:** (a) Either enable import-linter analysis of in-function imports, or
  (b) convert the lazy imports into a registry/plugin lookup (preferred — also fixes the
  architectural root cause). Make the fitness test green first (P0).
- **Consequences:** Future refactors become measurable; adding a broker will no longer
  require editing `brokers.common`.
- **Alternatives rejected:** Ignore the red test — rejects the "guardrails first" principle.

## ADR-002 — Single source of truth for domain objects
- **Status:** Proposed
- **Context:** `OptionChain`, `Instrument`, `Order`, `Position` are each defined in both
  `domain.aggregates` (deprecated) and `domain.entities/instruments/options`.
- **Decision:** Canonical home = `domain.entities` + `domain.instruments` + `domain.options`.
  Delete `domain.aggregates`. Events move to `domain`.
- **Consequences:** Removes drift risk; simplifies imports. One-time migration cost.

## ADR-003 — Broker selection by capability registry, not hardcoded imports
- **Status:** Proposed
- **Context:** `brokers.common.adapter_factory` lazily imports `brokers.dhan`/`upstox`.
- **Decision:** Brokers self-register via `capabilities.py` + `registry`/`broker_port`;
  `common` resolves by capability only.
- **Consequences:** True broker-agnosticism; new broker = new package, no `common` edits.

## ADR-004 — Reorganise `brokers` and promote `market_data`
- **Status:** Proposed
- **Context:** `brokers` is 86k LOC; `common` absorbs orchestration; `market_data` package
  was dismantled into a data directory.
- **Decision:** `brokers.common` = broker-agnostic core only. Move `router`,
  `stream_orchestrator`, `historical_coordinator`, `provenance`, `intelligent_market_gateway`
  to `application` / promoted `market_data` / `infrastructure`. Promote `market_data/` to a
  real package owning live+historical feeds, normalization, replay source.
- **Consequences:** Cleaner bounded contexts; `brokers` becomes a thin adapter layer.

## ADR-005 — OMS & Analytics depend on ports, not infrastructure
- **Status:** Proposed
- **Context:** `application.oms.*` imports `infrastructure.*` (30+ carve-outs); `analytics`
  imports concrete `datalake`.
- **Decision:** Extract `event_publisher`, `persistence`, `metrics`, `state_machine` ports
  into `domain/ports`; inject implementations; route `analytics → datalake` via a port.
- **Consequences:** OMS/analytics become unit-testable without infra; layering contract
  becomes real, not cosmetic.

## ADR-006 — One composition root + one public SDK facade
- **Status:** Proposed
- **Context:** `infrastructure.di.Container`, `runtime.composition.create_api_event_bus`, and
  `brokers/common/registry` coexist; no top-level `tradexv2` facade; `cli.services` imported
  by the runtime factory.
- **Decision:** `runtime` is the sole composition root (decoupled from `cli`); add a
  `tradexv2` OO facade over `Instrument`/ports; consolidate gateway port naming.
- **Consequences:** Single wiring story; better developer discovery.

---

## ADR-007 — Broker self-registration / capability registry (fixes D1)
- **Status:** Implemented (Phase D, slice 1)
- **Context:** `brokers.common.adapter_factory` hard-coded lazy imports of
  `brokers.dhan`/`brokers.upstox` to seed the data/execution/broker-adapter registries
  (the D1 hidden layer violation). `brokers.common` must stay broker-agnostic.
- **Decision:** Brokers register their own adapter classes into `brokers.common.adapter_factory`
  on package import (`brokers/dhan/__init__.py`, `brokers/upstox/__init__.py` call the
  `register_*` functions). `adapter_factory` keeps only the registry + `create_*` resolvers and
  never imports a concrete broker. The app/CLI/tests trigger registration simply by importing the
  broker packages (already required to build gateways); `tests/conftest.py` imports them for the
  session. This realises the registry/plugin lookup-by-capability from the original ADR-007 without
  touching any consumer.
- **Consequences:** `brokers-common-independence` lint contract is GREEN; adding a broker no
  longer requires editing `brokers.common`. Behaviour unchanged (registry populated identically).

---

## ADR-008 — `DomainEventBus` is the event port; infrastructure implements it
- **Status:** Implemented (Phase C, slice 1)
- **Context:** `domain.ports.event_publisher` re-exported the concrete `EventBus`, creating a
  `domain → infrastructure` violation; the `DomainEventBus` ABC had a stale, unused signature.
- **Decision:** `DomainEventBus` (`domain.events.bus`) is the port with signature
  `publish(event)`, `subscribe(event_type, handler) -> token`, `unsubscribe(token) -> bool`.
  `infrastructure.event_bus.event_bus.EventBus` and `...async_event_bus.AsyncEventBus` subclass it.
  `domain` never imports `infrastructure`.
- **Consequences:** Domain is event-port-agnostic; infra is swappable. (See Phase C slice 1 log.)

---

## ADR-009 — Domain ports are abstract only; no infrastructure re-exports
- **Status:** Implemented (Phase D, slice 2)
- **Context:** `domain/ports/*` defined proper `Protocol` ports but also re-exported infrastructure
  concretes (`metrics_registry`, `time_service`, `EventMetrics`, `trace_operation`,
  `LifecycleManager`/`HealthState`/`ManagedService`, `EventBus`), violating `Domain independence`
  and `Application infrastructure separation`.
- **Decision:** `domain.ports.*` modules contain only `Protocol` definitions and domain types; they
  never import `infrastructure`. Consumers that need a concrete import it from `infrastructure.*`
  directly. The re-export convenience is removed.
- **Consequences:** `lint-imports` is fully green (all contracts pass). Upper layers depend on ports,
  not on infrastructure concretes.

---
*ADR-001..006 are Accepted pending Phase 0 sign-off. ADR-007, ADR-008 and ADR-009 are **Implemented**
during the incremental evolution (Phases C–D) — the architecture-review loop runs as living
docs, not a big-bang rewrite.*
