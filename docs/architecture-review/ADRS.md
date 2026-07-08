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
*All ADRs are pending approval of the Phase 0 review. Implementation follows
`REFACTORING_ROADMAP.md` only after sign-off.*
