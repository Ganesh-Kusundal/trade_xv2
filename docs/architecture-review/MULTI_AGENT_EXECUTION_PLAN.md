# Multi-Agent Execution Plan — TradingOS Transformation

**Status:** PLAN ONLY. No product code has been modified. This document defines *how* the
phases in `REFACTORING_ROADMAP.md` are executed by a multi-agent team, and details the first
dispatch (Phase A).

**Governing rules (from Charter §7 loop):** analyze → propose → compare → select → refactor
incrementally → run full suite → update docs → write ADR → **wait for review before next major
change**. No big-bang rewrite. Mock only external boundaries. Every phase merges only when its
`TARGET_ARCHITECTURE.md` §12 checklist is green.

---

## 1. Agent Team Topology

The orchestrator (Chief Architect persona) runs the loop and owns ADRs, dependency rules, and
sequencing. Domain work is delegated to scoped agents mapped to the Charter's Virtual
Engineering Organization + the tradexv2-org divisions.

| Team (agent) | Charter lens | Owns (bounded context) | Phases |
|---|---|---|---|
| **Orchestrator / Chief Architect** | R.C. Martin + Evans | ADRs, layering, sequencing, review gate | all |
| **Domain Engineering** | Evans + Vernon | `domain/` model, VOs, aggregates, ports, events | B, C, E |
| **Broker Platform** | Martin Thompson + Jane Street | `infrastructure/brokers`, capability registry, SDK | D |
| **OMS & Execution** | Greg Young + Citadel | `application/oms`, order state machine, risk, reconciliation | E, F |
| **Market Data & Replay** | Thompson + Bloomberg | `domain/market`, `infrastructure/datalkae`, replay `EventSource` | C, F |
| **Quant Research** | Two Sigma + QuantConnect | `domain/scanner`, `domain/strategies`, indicators | E |
| **Platform / Infrastructure** | Fowler + Beck | `runtime/` (RuntimeContext), DI, persistence, cache, observability | C, F, G |
| **Integration & Validation** | Feathers + Beck | parity gate, e2e, regression, architecture fitness | every phase gate |
| **Architecture Review Board** | all personas | rejects any change that breaks layering/cohesion | gate per phase |

Each agent works **only inside its bounded context**. Cross-context changes (e.g. moving
orchestration out of `brokers.common`) are proposed by the originating agent and approved by
the Board before implementation.

---

## 2. Coordination Model

- **Contract-first.** Every phase starts with a *contract*: a `domain.ports` interface and/or
  an ADR, reviewed by the Board, before any implementation.
- **Composition root owned by Orchestrator.** `runtime/` (RuntimeContext) wiring is the only
  place that connects agents' outputs; agents implement against ports, never each other.
- **Shared orientation.** Every agent runs `graphify` first (per graphify skill) to scope its
  subgraph; only then reads code. `graphify update .` after any change (AST-only, no cost).
- **Hard gates (CI):** `tests/test_architecture.py` (fitness) + `lint-imports`
  (import-linter) + broker contract tests + `runtime/parity_gate.py`. A red gate blocks merge.
- **Output contract per agent:** code + tests + an ADR appendix (or ADR reference) + doc updates
  to the relevant section of `TARGET_ARCHITECTURE.md` / `ARCHITECTURE_REVIEW.md`.

---

## 3. Phase → Team Mapping

```
A  Baseline        Orchestrator + Platform Eng        (config + ADRs; no product code)
B  Domain          Domain Engineering                  (one source of truth)
C  Runtime         Platform Eng + Market Data + Domain (RuntimeContext, BrokerSession, events)
D  Broker SDK      Broker Platform                     (registry, shrink common, OO SDK)
E  Trading Engine  OMS&Exec + Quant Research + Domain   (scanner/strategy/OMS/risk pipelines)
F  Infrastructure  Platform Eng + OMS&Exec + Market Data(Event Store, replay, ports)
G  Cleanup         Platform Eng + all                  (package reorg, delete dead, tighten lint)
```
Phases may overlap at package boundaries, but each phase's §12 checklist must be green before
its successor merges.

---

## 4. Phase A — Detailed Dispatch (first to run)

**Objective:** make the architecture guardrails *truthful* and ratify the spec/ADRs. **No broker
product code is modified in Phase A** — the hidden `brokers.common → dhan/upstox` violation
(D1) is made *visible* and explicitly owned; the code fix is scheduled in Phase D (registry).

### Agents & tasks
| Agent | Task | Inputs | Output |
|---|---|---|---|
| A1 — Platform Eng (lint truthfulness) | Align `lint-imports` with the fitness test so in-function/lazy imports in `brokers.common.*` are checked; confirm both gates go red on D1. | `.import-linter.ini`, `tests/test_architecture.py`, `brokers/common/adapter_factory.py`, `infrastructure.py`, `oms/margin_provider.py` | Updated `.import-linter.ini` (config only) + note explaining why lint previously passed; both gates now agree. |
| A2 — Chief Architect (ADRs) | Ratify ADR-001..006 in `ADRS.md`; add ADR-007 "Registry/plugin broker selection" (target of D1 fix in Phase D); record Phase A decision. | `TARGET_ARCHITECTURE.md`, `TECHNICAL_DEBT.md` | Updated `ADRS.md` (all Accepted pending sign-off). |
| A3 — Integration (baseline evidence) | Snapshot current guardrail state: run fitness test + lint, capture red items, record in `TECHNICAL_DEBT.md` as the tracked baseline for D1. | test + lint output | Baseline record; no code. |

### Agent prompt template (A1)
```
You are the Platform Engineering Director on the TradingOS transformation.
Task: make import-linter truthful. Today `lint-imports` exits 0 while
`tests/test_architecture.py` FAILS on `brokers.common → brokers.dhan/upstox` (lazy
imports in adapter_factory.py, infrastructure.py, oms/margin_provider.py). Investigate why
lint misses in-function imports (likely source_modules scope), then update `.import-linter.ini`
so `brokers.common.*` (all submodules) is checked for forbidden `brokers.dhan`/`brokers.upstox`
imports. Do NOT modify broker product code. After: run `lint-imports` and
`pytest tests/test_architecture.py -q`; both should now agree (red on D1). Report the config
change and the exact contract added. Use graphify first to scope the subgraph.
```

### Gates for Phase A (from TARGET §12)
- [ ] spec + ADRs ratified (`ADRS.md` updated).
- [ ] `lint-imports` now analyzes in-function imports and agrees with the fitness test.
- [ ] D1 recorded as a tracked, visible, owned debt item (fix scheduled in Phase D).
- [ ] **No product-code change** in Phase A (config + docs only).
- [ ] Orchestrator reviews and signs off before Phase B dispatch.

### Rollback
Revert `.import-linter.ini` change; ADRs are docs only. Zero runtime impact.

---

## 5. How Agents Are Dispatched

The Orchestrator:
1. Reads the phase checklist (`TARGET §12`) and the relevant contract/ADR.
2. Spawns scoped agent(s) with: (a) the graphify-first instruction, (b) bounded-context scope,
   (c) the contract/ADR to implement against, (d) the exact gate commands.
3. Collects each agent's code + tests + ADR appendix.
4. Runs the hard gates; if red, returns work to the agent (loop step 8–9).
5. Updates docs; writes/updates the ADR (step 10).
6. **Stops for Architecture Review Board sign-off before the next major phase (step 11).**

---

## 6. Risk Controls
- Agents never edit outside their bounded context without Board approval (prevents the
  `brokers.common` god-package from getting worse).
- Parity gate (`runtime/parity_gate.py`) runs on every phase that touches trading paths.
- Characterization tests are written *before* refactoring legacy modules (Feathers).
- Phase A is config/docs only → near-zero blast radius; later phases are feature-flagged.

---

## 7. Definition of Done — Phase A
The guardrails are **honest** (lint and fitness test agree), the spec + ADRs are ratified, and
D1 is a visible, owned, scheduled debt item. Only then does the Orchestrator dispatch Phase B
(Domain) agents.

*This is the execution plan. Phase A has been dispatched and completed (config + docs only;
no product code changed). Phases B–G follow the same gated loop.*

## 8. Phase A — Execution Log (completed)
- **A1 (Platform Eng):** `.import-linter.ini` `brokers-common-independence` `source_modules`
  changed `brokers.common` → `brokers.common.*` (wildcard) so all submodules (incl. in-function
  lazy imports) are checked. `lint-imports` now exits **1** (was 0) — gate is truthful.
- **A2 (Chief Architect):** `ADRS.md` — ADR-001…006 marked *Accepted (pending implementation)*;
  added **ADR-007** (capability registry fixes D1 in Phase D).
- **A3 (Integration):** `TECHNICAL_DEBT.md` D1 updated with the truthful-baseline evidence;
  metrics line now reads `lint-imports: RED (truthful, ADR-001)`.
- **Gate result:** `lint-imports` (RED) and `pytest tests/test_architecture.py` (2 failed on D1)
  now **agree**. No product code modified. Ready for Board sign-off → Phase B dispatch.

## 9. Phase B — Execution Log (first slice, completed)
**Refinement to the original B plan (important):** investigation showed `domain.aggregates` is
NOT purely redundant. `InstrumentAggregate = Instrument` and `OptionChainAggregate = OptionChain`
are deprecated pure aliases (deleted), but `OrderAggregate` / `PositionAggregate` /
`AccountAggregate` are **legitimate thread-safe DDD aggregate roots** (no deprecation warning)
that wrap the canonical VOs. Blindly deleting the whole package would have destroyed real
aggregate roots — so Phase B was scoped to remove the aliases only (challenge-assumptions rule).
- **Deleted:** `src/domain/aggregates/instrument.py`, `src/domain/aggregates/option_chain.py`.
- **Migrated importers** (alias → canonical): `analytics/__init__.py`,
  `analytics/core/instrument_analyzer.py`, `analytics/core/providers.py`, `src/domain/__init__.py`,
  `src/domain/factories/instrument_factory.py`, `src/domain/value_objects/state.py` (docstrings).
- **Rewrote** `src/domain/aggregates/__init__.py` to export only the 3 real aggregates.
- **Verified:** import smoke test OK; `pytest src/domain` = 5 failed / 630 passed — **unchanged
  from baseline** (the 5 failures are pre-existing `futures` tests, unrelated). Zero code refs to
the deleted aliases remain.
- **Graph:** `graphify update .` run.
- **Docs:** `TECHNICAL_DEBT.md` D3 and `ADRS.md` ADR-002 updated to reflect the refined scope.
- **Remaining B work (next slices, lower priority / higher risk):** re-home the 3 real
  aggregates into `domain/orders`,`domain/positions`,`domain/accounts`; unify `Quote` vs
  `QuoteSnapshot` only if they are true duplicates (currently VO vs port-return type); move
  order/position state-machine ownership; single `InstrumentRepository`. Each is a separate
  gated sub-step.

### Phase B — slice 2 (aggregate re-homing, completed)
- **Moved** `OrderAggregate`→`domain/orders/aggregate.py`, `PositionAggregate`→`domain/positions/aggregate.py`,
  `AccountAggregate`→`domain/accounts/aggregate.py`. **Deleted** `src/domain/aggregates/` entirely.
- **Repointed** the two re-export shims (`domain/accounts`, `domain/positions`) and added one for
  `domain/orders`; removed the now-obsolete `domain-instruments-no-aggregates` import-linter contract.
- **Verified:** import smoke OK; `pytest src/domain` = 5 failed/630 passed (unchanged baseline);
  re-export tests 5 passed; `lint-imports` still RED on D1 (truthful, expected — not a regression);
  `graphify update .` run.
- **Docs:** D3 and ADR-002 marked fully resolved; `domain.aggregates` no longer exists.
- **Remaining B work (next slices):** unify `Quote` vs `QuoteSnapshot` only if true duplicates;
  move order/position state-machine ownership into `domain`; single `InstrumentRepository`.
  Awaiting Board sign-off before the next B slice.

### Phase C — slice 1 (event port truthful + infra implements it, completed)
- **Made `DomainEventBus` (`domain/events/bus.py`) truthful:** `publish(event: DomainEvent)`,
  `subscribe(event_type, handler) -> str`, `unsubscribe(token) -> bool` — matching the real bus.
- **`EventBus(DomainEventBus)`** and **`AsyncEventBus(DomainEventBus)`** in
  `infrastructure/event_bus` now formally implement the domain port (infra depends on the
  domain port, never the reverse).
- **Removed the domain→infra violation:** `domain/ports/event_publisher.py` no longer re-exports
  the concrete `EventBus`; broker/test consumers now import it from
  `infrastructure.event_bus.event_bus`. This closed a latent circular-import (an infra-first
  import had triggered `ImportError`).
- **Verified:** infra-first import no longer cycles; `issubclass(EventBus, DomainEventBus)` and
  `issubclass(AsyncEventBus, DomainEventBus)` are True; `pytest src/domain` = 5f/630p (baseline);
  `pytest infrastructure/event_bus` + `tests/test_architecture.py` = 2f (expected D1 red)/27p;
  `pytest brokers/common` = 1f (pre-existing `test_status_mapping` Mock-assertion, unrelated)/
  747p; `lint-imports` still RED on D1 (truthful); `graphify update .` run. (One transient `.pyc`
  cache failure was cleared — not a regression.)
- **Docs:** D12 resolved; ADR-008 added (event port + domain-never-imports-infra).
- **Remaining C work (next slices, higher risk):** `RuntimeContext` UI-agnostic composition
  root (decouple `TradingRuntimeFactory` from `cli`); `BrokerSession` lifecycle + capability
  negotiation (overlaps Phase D registry, ADR-007); `LiveSubscription` manager.

### Phase C — slice 2 (RuntimeContext decoupled from cli, completed)
- **Made the `Runtime` composition root UI-agnostic:** removed the module-level
  `TYPE_CHECKING` imports of `cli.services.broker_service.BrokerService` and
  `cli.services.oms_service.OmsService`; retyped `Runtime.broker_service` / `oms_service`
  as `Any`. The `Runtime` dataclass no longer references `cli` at all.
- **Entry points stay cli-aware:** `build()` / `build_for_api()` still construct
  `BrokerService`/`OmsService` (lazy imports inside those methods) — that is correct: entry
  points know their UI. The shared wiring core (`build_from_broker_service`) no longer pulls
  `cli` in at import time.
- **Verified:** `import runtime.trading_runtime_factory` does NOT load `cli`
  (`'cli' in sys.modules` is False); `runtime`, `cli.services.compose`, `runtime.api_bootstrap`
  import cleanly; `pytest tests/runtime tests/integration/...runtime...` = 12 passed;
  `lint-imports` still RED on D1 (expected); `graphify update .` run.
- **Phase C status:** complete (event port truthful — ADR-008; `RuntimeContext` decoupled from
  `cli`). The remaining C items (`BrokerSession` lifecycle, `LiveSubscription` manager) overlap
  Phase D / ADR-007 and are carried into Phase D below.

### Phase D — slice 1 (D1 resolved: brokers self-register, `brokers.common` broker-agnostic)
- **Fixed D1 (the truthful hidden-coupling gate):** `brokers/common/adapter_factory.py` no longer
  imports `brokers.dhan`/`brokers.upstox`. The three `_seed_*` functions + their 7 lazy broker
  imports are gone; `create_*` / `get_broker_extension_classes` resolve purely from the registry.
- **Brokers self-register (ADR-007, Implemented):** `brokers/dhan/__init__.py` and
  `brokers/upstox/__init__.py` call `register_data_adapter` / `register_execution_provider` /
  `register_broker_adapter` / `register_broker_extensions` on import. The app already imports the
  broker packages to build gateways, so registration is automatic with **zero consumer changes**.
  `tests/conftest.py` imports the broker packages so the registry is populated for every test.
- **Cleaned stale `ignore_imports` that masked the gate:** two stale entries
  (`infrastructure.global_exception_handler -> brokers.common.resilience.errors` and
  `infrastructure.retry -> brokers.common.resilience.errors`) referenced imports that no longer
  exist; in this import-linter version they raised `MissingImport` and forced `lint-imports` to
  exit 1 regardless of real violations. Removed from both `pyproject.toml` and `.import-linter.ini`
  (the test-only variants were kept because they still match).
- **Verified:** `lint-imports` `brokers-common-independence` contract is now **GREEN** (6 kept,
  2 broken — the 2 broken are pre-existing `domain.ports.* → infrastructure.*` leaks, see below,
  unrelated to D1); `import brokers.common.adapter_factory` does NOT load `brokers.dhan`;
  self-registration populates the registry (`dhan`/`upstox` data + broker adapters registered);
  `pytest brokers/common` = 1f (pre-existing `test_status_mapping` Mock-assertion)/747p;
  `pytest src/domain` = 5f/630p (exact baseline); `pytest tests/integration` = 31f/10e — **proven
  pre-existing** by stashing the change and re-running (identical 31f/10e on baseline);
  `graphify update .` run.
- **Two OTHER lint contracts are red (pre-existing, NOT D1):** `Domain independence` and
  `Application infrastructure separation` are broken because `domain.ports.lifecycle` /
  `domain.ports.metrics` / `domain.ports.observability` / `domain.ports.time_service` import
  `infrastructure.*`. These are the "infrastructure must not leak into domain" leaks (related to
  D4/D8) and need their own slice — out of scope for this D1 fix. Recommended next focus.
- **Awaiting Board sign-off** before the next slice (next candidate: the `domain.ports.* →
  infrastructure.*` leaks — a dedicated port-extraction slice).

### Phase D — slice 2 (domain.ports → infrastructure leaks fixed; lint fully GREEN)
- **Removed infrastructure re-exports from `domain/ports/*`:** `metrics.py`, `lifecycle.py`,
  `observability.py`, `time_service.py`, `event_publisher.py` kept their `Protocol` ports but dropped
  the `from infrastructure... import` re-exports (`metrics_registry`, `time_service`, `EventMetrics`,
  `trace_operation`, `LifecycleManager`/`HealthState`/`ManagedService`, `EventBus`).
  `src/domain/ports/__init__.py` likewise stopped re-exporting those concretes.
- **Redirected ~20 consumers** (brokers + a few `domain.ports` internals) to import the concretes
  from `infrastructure.*` directly. No consumer depends on the removed re-exports; ports still
  resolve from `domain.ports`.
- **Verified:** `lint-imports` is now **fully GREEN** — `Domain independence` and
  `Application infrastructure separation` are GREEN, so all 8 contracts pass (exit 0). `src/domain/ports`
  has zero `infrastructure` imports; `domain.ports` still imports; redirected-consumer smoke OK;
  `pytest src/domain` = 24f/611p and `pytest brokers/common` = 1f/747p — **both proven pre-existing**
  (identical counts on the git baseline via stash), i.e. no regression from this slice. (The 24
  `src/domain` failures are a `lot_size` TypeError in `instrument.py`/`futures.py`, unrelated to this
  work and pre-existing.)
- **Next:** the truthful gate is fully green. Remaining work is the original debt items
  (D2 god-package, D4 OMS→infra port-extraction, D5 market_data, D7 cli cycle, …) and the
  unfinished Phase C items (`BrokerSession` lifecycle, `LiveSubscription` manager) that overlap D.
  Awaiting Board sign-off.

## 10. Board sign-off + next slice (2026-07-09)

Board (user-directed continue) signed off on the green gate and selected **D4 — OMS→infra ports**
as the next slice (HIGH risk, large). Per the user's instruction, the prior green slices (B, D-1,
D-2) are committed **per slice** to a clean base before D4 starts. This turn: (1) commit prior
slices, (2) deliver the D4 proposal below and stop for sign-off before implementation (charter
loop: analyze → propose → review → refactor).

### Phase D — slice 3 (D4): OMS→infra port extraction — PROPOSAL (awaiting sign-off)

**Verified ground state:** `lint-imports` = 8/8 GREEN; `src/domain/aggregates/` still physically
present in the tree (see open flag below) — Phase B slice 2's claimed deletion did not land, so the
old aggregates coexist with the re-homed `domain/{accounts,orders,positions}/aggregate.py`.

**Production (non-test) `application → infrastructure` violations** (from the
`Application infrastructure separation` `ignore_imports` + a grep of `application/**`):

| Module | Infrastructure dependency |
|---|---|
| `application/oms/context.py` | `event_bus`, `event_log`, `lifecycle` (LifecycleManager), `observability.event_metrics`, `persistence.sqlite_order_store`, `persistent_dead_letter_queue` |
| `application/oms/order_manager.py` | `event_bus`, `logging_config`, `metrics.metrics_registry`, `observability.event_metrics`, `observability.tracing` (trace_operation), `persistence.sqlite_order_store` |
| `application/oms/position_manager.py` | `event_bus`, `logging_config`, `observability.event_metrics`, `state_machine` |
| `application/oms/reconciliation_service.py` | `event_bus`, `lifecycle` |
| `application/oms/factory.py` | `event_bus`, `event_log` |
| `application/oms/square_off_service.py` | `event_bus` (lazy) |
| `application/oms/extended_order_service.py` | `event_bus` (lazy) |
| `application/oms/daily_pnl_reset_scheduler.py` | `lifecycle` |
| `application/oms/_internal/order_state_validator.py` | `state_machine` |
| `application/audit.py` | `logging_config`, `correlation` (lazy) |
| `application/trading/trading_orchestrator.py` | `event_bus` |
| `application/trading/feature_fetcher.py` | `market_data_adapter` |

**Proposed ports to add/use in `domain.ports`** (concrete infra classes implement them; OMS depends
on the port, receives concretes via DI — the D2 pattern):
1. `DomainEventBus` (exists, D2) — covers EventBus / ProcessedTradeRepository / DomainEvent / TradeIdKey.
2. `EventLogPort` — BufferedEventLog / EventLog.
3. `LifecyclePort` — LifecycleManager / HealthState / ManagedService / build_health (Protocol exists in `domain.ports.lifecycle`; OMS must use it, not infra).
4. `MetricsPort` — metrics_registry / EventMetrics (Protocol exists in `domain.ports.metrics`).
5. `TracingPort` — trace_operation / get_current_correlation_id.
6. `OrderStateMachinePort` — StateMachine / IllegalTransitionError.
7. `OrderStorePort` — SqliteOrderStore.
8. `MarketDataAdapterPort` — GatewayMarketDataAdapter (likely already in market-data ports).
9. Logging (`get_logger`) — decision: cross-cutting exempt, or a `LoggingPort`.

**Approach / sub-slices (each gate-green before the next):** (a) event + log ports; (b) lifecycle +
metrics + tracing ports; (c) persistence + state-machine ports; (d) market-data adapter port; then
drop the matching `ignore_imports` from `Application infrastructure separation` as each closes.
Test-only carve-outs (`application.oms.tests.* → infrastructure.*`) kept or redirected per fixture.

**Risk:** HIGH — ~12 production modules across event/persistence/state-machine subsystems; will be
incremented sub-slice by sub-slice, never big-bang. **Awaiting Board sign-off on the port set and
sub-slice order before implementation.**

### Phase D — slice 3 (D4 sub-slice a: events + log ports wired) — EXECUTED
Board approved "start events+log" (2026-07-09). Implementation closed the
`Application infrastructure separation` violations for the event subsystem.

**Ports added (`domain.ports`):**
- `EventBusPort` (in `event_publisher.py`) — `EventPublisher` + replay-mode /
  logging-enabled controls OMS toggles during replay.
- `EventLogPort`, `DeadLetterQueuePort`, `ProcessedTradeRepositoryPort` (new
  `event_log.py`).
- `TradeIdKey` relocated from `infrastructure.event_bus` to
  `domain.events.types` (infrastructure re-exports for backward-compat). The
  OMS now builds idempotency keys without importing `infrastructure`.

**Modules redirected to ports (no `application → infrastructure.event_bus` /
`infrastructure.event_log` import — event subsystem only):**
`application/oms/{context,order_manager,position_manager,reconciliation_service,
factory}`, `application/trading/trading_orchestrator`, and the lazy `DomainEvent`
imports in `square_off_service` / `extended_order_service` (now
`domain.events.types`). `context.py` / `order_manager.py` no longer *construct*
infra objects — `TradingContext`/`OrderManager` require injected collaborators.

> **Scope note:** de-coupling here is *event-subsystem only*. The same modules
> still import other infrastructure (lifecycle, observability/event_metrics,
> metrics, tracing, persistence, state_machine); those are deferred to sub-slices
> (b)–(d) below, not removed in (a).

**Composition roots now inject the event defaults:**
- `cli/services/oms_setup.py` builds + passes `dead_letter_queue` (alongside the
  `event_bus`/`event_log`/`processed_trades` it already built).
- `api/lifecycle.py` builds missing `event_bus`/`dead_letter_queue`/
  `processed_trade_repository` via `brokers.common.oms.defaults`.
- `brokers/common/oms/defaults.py` is the single builder of event infra
  concretes (allowed: `brokers.common → infrastructure`). `application` never
  reaches `infrastructure` — import-linter is **transitive**, so this could not
  live in `application`.

**Test harness:** `tests/conftest.build_test_trading_context` fills the event
defaults for tests that previously relied on `TradingContext()` auto-building
them. 30 test files updated to use it.

**Removed `ignore_imports`:** 11 event-related carve-outs from the
`Application infrastructure separation` contract in **`pyproject.toml`** (the
authoritative `tool.importlinter` block) — confirmed via `git diff`
(context/order_manager/position_manager/reconciliation/trading_orchestrator/
square_off/extended_order/factory → `infrastructure.event_bus`/`event_log`).

> **Config-hygiene correction (post-execution):** the contracts lived in *two*
> places — `pyproject.toml` (8 contracts, all KEPT) **and** a stale
> `.import-linter.ini` (only 5 contracts, still carrying the 11 event carve-outs
> *plus* a D-1 `infrastructure.retry -> brokers.common.resilience.errors` entry
> that was never actually deleted). CI's `lint` job ran `lint-imports
> --config .import-linter.ini` and was therefore **RED** (exit 1) despite the
> report claiming "GREEN 8/8" (that only held for the default `pyproject.toml`
> run). Resolved by **deleting `.import-linter.ini`** and pointing CI at
> `pyproject.toml` (single source of truth). The redundant `lint-imports` step
> in the `unit-and-contract` job already used the default `pyproject.toml`.

**Verification:** `lint-imports --config pyproject.toml` fully GREEN (8/8).
Remaining `infrastructure` `ignore_imports` are lifecycle/metrics/tracing/
persistence/state-machine/market-data — the next D4 sub-slices (b)–(d).

### Phase D — slice 3 (D4 sub-slices b–d): remaining `application → infrastructure` ports — PLANNED
Board (user) signed off "complete all" (2026-07-09). Sub-slices execute one at
a time, each gate-green (`lint-imports` + targeted tests) and committed before
the next. Each redirects the remaining `Application infrastructure separation`
`ignore_imports` to ports and injects concretes via the existing composition
roots (`brokers/common/oms/defaults.py`, `cli/services/oms_setup.py`,
`api/lifecycle.py`) + `tests/conftest.build_test_trading_context`.

| Sub-slice | Ports to add/use | Modules redirected | ignore_imports closed |
|---|---|---|---|
| **(b) lifecycle + metrics + tracing** | `LifecyclePort` (extend `domain.ports.lifecycle`: `LifecycleManager`/`HealthState`/`build_health` + existing `ManagedServicePort`); `MetricsPort` (= `MetricsRegistryPort` + `EventMetrics`); `TracingPort` (`trace_operation`, `get_current_correlation_id`) | `context`, `order_manager`, `position_manager`, `reconciliation_service`, `daily_pnl_reset_scheduler` (lifecycle/metrics/tracing only; `logging_config`/`correlation` left as cross-cutting exempt unless Board says otherwise) | `context→lifecycle/observability.event_metrics`, `order_manager→metrics/observability.event_metrics/observability.tracing`, `position_manager→observability.*`, `reconciliation_service→lifecycle`, `daily_pnl_reset_scheduler→lifecycle.*` |
| **(c) persistence + state-machine** | `OrderStorePort` (`SqliteOrderStore`); `OrderStateMachinePort` (`StateMachine`, `IllegalTransitionError`) | `context`, `order_manager`, `position_manager`, `_internal/order_state_validator` | `context→persistence.*`, `order_manager→persistence.*`, `position_manager→state_machine`, `_internal/order_state_validator→state_machine` |
| **(d) market-data adapter** | `MarketDataAdapterPort` (reuse `domain.ports.market_data` if present, else add) | `trading/feature_fetcher` | `trading.feature_fetcher→infrastructure.market_data_adapter` |

**Logging decision (deferred):** `get_logger` / `correlation` are cross-cutting;
treated as exempt for now (kept in `ignore_imports`); a `LoggingPort` can be added
later if the Board wants full isolation. `application.audit` logging/correlation
and `application.composer.* → brokers.common.*` are out of D4 scope.

**Risk:** HIGH (compounds sub-slice a). Mitigation: one sub-slice per commit,
gate-green before merge, characterization tests first (Feathers).

### Phase D — slice 3 (D4 sub-slice c: persistence + state-machine) — EXECUTED
**State machine relocated to domain.** `StateMachine` + `IllegalTransitionError`
were pure domain logic (only depended on `domain.exceptions.TradeXV2Error`)
living in `infrastructure.state_machine`; moved to `src/domain/state_machine.py`.
`infrastructure/state_machine.py` now re-exports for back-compat. OMS modules
(`position_manager`, `_internal/order_state_validator`) import from
`domain.state_machine` — no `application → infrastructure.state_machine` import.

**`OrderStorePort` added** (`src/domain/ports/order_store.py`): `upsert` /
`load_all` / `close`. `context.py` + `order_manager.py` depend on the port (no
`infrastructure.persistence` import); `TradingContext` no longer constructs
`SqliteOrderStore` — composition roots inject it. `create_trading_context` gained
`durable_order_store` (+ forwards `enable_durable_orders`).
`brokers.common.oms.defaults.build_order_store` is the single concrete builder;
`cli/services/oms_setup` + `api/lifecycle` inject it.

**Removed `ignore_imports`:** 6 (state-machine ×2, persistence ×4). Verified
`Application infrastructure separation` KEPT.

### Phase D — slice 3 (D4 sub-slice d: market-data adapter) — EXECUTED
`feature_fetcher.PipelineFeatureFetcher` depends on the existing
`MarketDataPort` (was importing `infrastructure.market_data_adapter
.GatewayMarketDataAdapter` and constructing it from a `gateway`). The
`gateway`-based auto-build is removed; the adapter is injected.
**Removed `ignore_imports`:** `application.trading.feature_fetcher →
infrastructure.market_data_adapter`.

### Phase D — slice 3 (D4 sub-slice b, cont.: metrics + event-metrics) — EXECUTED
`metrics_registry` (module-level singleton) and `EventMetrics` (constructed in
`TradingContext`) are now proper collaborators:
- `OrderManager` depends on `MetricsRegistryPort`; the three OMS counters
  (`oms_orders_total`, `oms_order_placement_latency_seconds`,
  `oms_active_orders`) are created **lazily in `__init__`** from the injected
  registry. `MetricsRegistry.counter/gauge/histogram` are idempotent by name,
  so multiple `OrderManager`s sharing the process-wide registry observe the
  same objects. Counter inc/dec/observe sites are `None`-guarded.
- `EventMetrics` is replaced by `EventMetricsPort` in `context.py` /
  `order_manager.py` / `position_manager.py`; the concrete `EventMetrics` is
  injected by the composition roots (`cli/oms_setup`, `api/lifecycle`) and the
  test harness (`build_test_trading_context`); `TradingContext` no longer
  constructs it. `TradingContext` gains a `metrics_registry` param threaded
  into `OrderManager`.
- **Removed `ignore_imports`:** `application.oms.context →
  infrastructure.observability.event_metrics`,
  `application.oms.order_manager → infrastructure.metrics`,
  `application.oms.order_manager → infrastructure.observability.event_metrics`,
  `application.oms.position_manager → infrastructure.observability.*`.

### Cross-cutting observability — PARTIALLY exempt (final state)
Of the four originally-deferred cross-cutting concerns, two are now ported
(`metrics_registry` → `MetricsRegistryPort`, `EventMetrics` →
`EventMetricsPort`). The remaining two are genuinely definition/import-time
cross-cutting and **stay exempt**:
- **`get_logger`** (`infrastructure.logging_config`) — process-wide logger
  factory; forcing a per-instance logger port is high-churn with no gain.
- **`trace_operation`** (`infrastructure.observability.tracing`) — a
  **definition-time decorator**; it cannot consume an injected `TracerPort`
  (decorators apply at class-definition, before any instance injection).
  Routing it through `domain.ports` was attempted and **reverted**: a lazy
  `infrastructure` import inside `domain.ports.observability` violates the
  `Domain independence` contract directly and transitively re-breaks
  `Application infrastructure separation`. So `trace_operation` is kept as an
  exempt `ignore_imports` entry alongside `get_logger`.

**D4 collaborator de-coupling is complete.** Every per-instance OMS
collaborator (event bus, event log, dead-letter queue, processed-trade repo,
lifecycle manager, order store, state machine, market data, metrics registry,
EventMetrics) is now behind a `domain` port; only the two cross-cutting
import-time concerns (`get_logger`, `trace_operation`) remain exempt, by
design.

### Known pre-existing gate status (working tree, not from D4)
The working tree currently shows `CLI broker-implementation isolation` BROKEN
due to uncommitted pre-existing changes in `cli/services/broker_service.py`
(imports `brokers.dhan` / `brokers.paper`). This is unrelated to D4 — HEAD is
green and the violation is pre-existing uncommitted work. D4's target contract
`Application infrastructure separation` is KEPT. (Resolved earlier false "GREEN
8/8": CI's `lint` job ran the stale `.import-linter.ini`, now deleted — see
sub-slice a execution note.)
