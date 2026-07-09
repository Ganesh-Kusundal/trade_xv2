# TradeX V2 — Target Architecture Specification

- **Status:** TARGET STATE (forward-looking). No source files were modified.
- **Companion document:** [`ARCHITECTURE_REVIEW.md`](./ARCHITECTURE_REVIEW.md) is the **Current State Assessment** (a discovery audit of the existing code). This document is the opposite direction: the architecture we are *building toward*.
- **How to read:** The refactoring roadmap (`REFACTORING_ROADMAP.md`) is driven by the **gap** between the Current State Assessment and this specification — not by cleanup tasks alone.
- **Guiding rule:** *Architecture leads implementation.* Every package move, rename, or deletion is justified by a difference measured against the models below. If a cleanup task is not traceable to a section here, it is deferred to Phase G.

---

## 0. Migration Philosophy

The Current State Assessment follows a *bottom-up* flow:

```
Fix → Clean → Consolidate → SDK
```

This specification inverts it. The work is **target-driven**, not *code-driven*:

```
Target Architecture
   ↓ Architecture Review (this doc vs. Current State)
   ↓ Domain Model
   ↓ Runtime Model
   ↓ Object Model
   ↓ Event Model
   ↓ Package Organization
   ↓ Incremental Migration
   ↓ Cleanup (Phase G — last, not first)
```

The current folder layout is treated as an *implementation detail*. We define the correct Runtime, Domain, Object, Event, and Data models first; package reorganization follows from those models (see §9 Dependency Rules and §10 Migration Plan).

---

## 1. Architecture Principles

These principles are the contract every future refactoring and new feature must satisfy. They are the lens used to evaluate the Current State Assessment.

1. **`Instrument` is the primary domain object.** Everything (quotes, orders, positions, greeks, history) hangs off an `Instrument` identified by a stable `InstrumentId`. `Instrument.buy()` / `Instrument.sell()` is the public OO surface (already in `src/domain/instruments/instrument.py`).
2. **Composition over inheritance.** Runtime components are composed from ports + adapters, not subclassed hierarchies.
3. **Broker SDKs never leak into the domain.** `src/domain` imports zero broker-specific symbols. Broker behaviour enters only through `domain/ports/*` at composition time.
4. **Behaviour belongs to domain objects.** State machines for `Order`, `Position`, `Subscription` live in `domain`, not `infrastructure`/`application`.
5. **Infrastructure implements domain ports.** `infrastructure/`, `brokers/`, `application/` are *adapters* of `domain/ports/*`.
6. **One source of truth for every concept.** A single canonical `Instrument`, `OptionChain`, `Order`, `Position`, `Quote`, `Event`. No parallel `entities` vs `aggregates`.
7. **No duplicate ownership of state.** Each mutable state has exactly one owner (e.g. `Position` lifecycle owned by OMS; `Instrument` metadata by `InstrumentRepository`).
8. **Local / paper / live share one runtime and one object model.** Replay, paper, and live run on the *same* `TradingRuntime`; only the `DataProvider` / `ExecutionProvider` adapter differs (principle 3 in action).
9. **Events are immutable, versioned, replay-compatible value objects**, defined in `domain/events`, emitted by domain objects, consumed via `DomainEventBus`.
10. **Backtest parity is a hard constraint.** A strategy cannot distinguish replay from live. The replay runtime is the live runtime with a different feed.

---

## 2. Target Runtime Model

The platform is composed of a small set of runtime components orchestrated by a single `RuntimeContext`. Each runtime is a *long-lived, behaviour-bearing service* with a defined lifecycle (§5); none is a "package" in the cleanup sense.

```
RuntimeContext                      (composition root + lifecycle owner)
├── BrokerSession                   (one per connected broker; auth + capability)
├── MarketDataRuntime              (feeds, normalization, subscription mgmt)
├── TradingRuntime                 (orders, OMS, risk, execution)
├── StrategyRuntime                (signal generation, strategy registry)
├── ScannerRuntime                 (universe screening pipeline, §7)
├── AnalyticsRuntime               (indicators, reporting, greeks)
└── ReplayRuntime                  (deterministic historical replay, §8)
```

| Runtime | Responsibility | Owns | Key ports |
|---|---|---|---|
| `RuntimeContext` | Boot, wire, lifecycle, shutdown/drain | Composition, config | `CompositionRoot` |
| `BrokerSession` | Authenticated broker connection, capability negotiation | Session auth, capability manifest | `BrokerGateway`, `MarketDataGateway`, `ExecutionProvider` |
| `MarketDataRuntime` | Live + historical feed multiplexing, normalization, subscription fan-out | Subscriptions, Quote cache | `DataProvider`, `MarketDataGateway` |
| `TradingRuntime` | Order lifecycle, OMS, risk, sizing, execution | Orders, Positions, Portfolio | `OMSPort`, `ExecutionProvider`, `RiskPort` |
| `StrategyRuntime` | Load strategies, evaluate signals, emit order intents | Strategy registry, signal state | `StrategyEvaluatorPort` |
| `ScannerRuntime` | Screening pipeline (§7) | Universe selection state | `ScannerPort`, `DataProvider` |
| `AnalyticsRuntime` | Indicators, greeks, reporting | Derived series | `AnalyticsPort` |
| `ReplayRuntime` | Deterministic replay; reuses all above with a fixed feed | Replay clock | `DataProvider` (historical), `ExecutionProvider` (sim) |

**Current state anchors:** `BrokerSession` already exists (`brokers/common/objects/session.py`); `RuntimeContext` exists in spirit as `runtime/trading_runtime_factory.py` but is entangled with `cli`. The target promotes `RuntimeContext` to the single, UI-agnostic composition root.



---

## 3. Object Model (Future)

The object model is the vocabulary every runtime speaks. These are the canonical types; duplicates in the Current State (e.g. `entities` vs `aggregates`) collapse onto these.

### 3.1 Core (one source of truth)

```
BrokerSession
  └── InstrumentRepository
        ├── Instrument  (Equity | Index | Future | Option)
        │     ├── InstrumentId        (stable VO, canonical key)
        │     ├── Quote / QuoteSnapshot
        │     ├── MarketDepth
        │     └── Metadata
        ├── OptionChain
        │     └── Option  ──(underlying Instrument)
        └── LiveSubscription   (managed stream handle)
  └── BrokerCapabilities       (capability manifest for this session)
  └── HistoryManager           (historical series store/loader)
```

| Type | Role | Notes / current anchor |
|---|---|---|
| `BrokerSession` | Authenticated broker facade | `brokers/common/objects/session.py` |
| `InstrumentRepository` | Single owner of `Instrument` metadata | new; resolves `InstrumentId` → canonical `Instrument` |
| `Instrument` | Primary domain object (principle 1) | `src/domain/instruments/instrument.py`; rich `buy/sell` |
| `InstrumentId` | Stable identity VO | `src/domain/instruments/instrument_id.py` |
| `Quote` / `QuoteSnapshot` | Immutable price VO | unify `entities/market.py` + `ports.protocols.QuoteSnapshot` |
| `MarketDepth` | Immutable depth VO | `domain/quotes` |
| `Metadata` | Static instrument attributes | single owner — kills the 3-owner instrument-master problem |
| `BrokerCapabilities` | What this broker/session supports | `domain/capability_manifest.py` |
| `LiveSubscription` | Active streaming handle | `src/domain/instruments/subscription.py` |
| `OptionChain` | Aggregate of `Option`s for an underlying | `src/domain/options/option_chain.py` (canonical) |
| `Option` | Derivative instrument | `src/domain/instruments/instrument.py` |
| `HistoryManager` | Load/warm historical series | new; backed by `datalake` behind a port |

### 3.2 Invariants
- `InstrumentRepository` is the **only** creator/resolver of `Instrument`. No ad-hoc `Instrument(...)` construction outside it (kills duplicate instrument-master ownership).
- `Quote` / `MarketDepth` are immutable value objects; updates are represented as new events (§4), not mutation in place.
- `Instrument.buy()/sell()` returns an `OrderIntent` that flows through the execution pipeline (§6); it does **not** touch broker code directly.

### 3.3 Public SDK Shape
The public SDK is broker-agnostic and object-oriented. A `BrokerSession` is the entry point;
domain objects expose behavior; broker-specific capabilities are reached only via `.broker` and
are gated by `BrokerCapabilities`.

```python
session = TradingOS.connect("dhan", profile="prod")   # -> BrokerSession
reliance = session.equity("RELIANCE")                  # -> Instrument (domain)
reliance.quote                                        # Quote VO
reliance.history("5m")                                # HistoricalSeries VO
reliance.market_depth                                 # MarketDepth VO
reliance.buy(qty=10)                                  # -> OrderIntent -> execution pipeline (§6)
chain = reliance.option_chain()                      # -> OptionChain aggregate
reliance.broker.depth200()                            # broker-specific, behind capability port
reliance.broker.depth30()                             # only if BrokerCapabilities allows
```
- `session.equity/option/future(...)` resolves via `InstrumentRepository` (single owner).
- Generic behavior (`quote`, `history`, `buy`, `option_chain`) is defined on `Instrument` (domain).
- `.<broker>` exposes only capabilities declared by `BrokerCapabilities`; an unsupported call
  raises a clear error. **Broker SDKs never leak into the domain** (principle 3).

---

## 4. Event Architecture

Events are first-class. The bus is a domain port; broker feeds are normalized into domain events at the edge and everything downstream is event-driven.

```
Exchange / Broker Feed
   ↓ (raw websocket / REST)
Normalizer            (broker-specific → canonical domain VO; lives in adapters)
   ↓
Domain Event         (immutable VO, defined in domain/events, versioned)
   ↓
DomainEventBus       (port; priority, sharded, DLQ, persistence, replay)
   ↓ (pub/sub)
┌────────────┬────────────┬──────────┬──────────┬────────────┬──────────┐
Runtime    Strategies  OMS       Portfolio  Persistence  Analytics
```

### 4.1 Event ownership & catalogue
Events are emitted by the object that *owns the state change*:
- `QuoteChanged`, `DepthChanged`, `TickReceived` → `MarketDataRuntime` / `Instrument`
- `OrderPlaced`, `OrderFilled`, `OrderRejected`, `OrderCancelled` → `TradingRuntime`/OMS
- `PositionOpened`, `PositionClosed` → OMS `PositionManager`
- `SubscriptionStarted`, `SubscriptionStopped` → `LiveSubscription`
- `MarketOpened`, `MarketClosed` → `RuntimeContext`
- `HistoricalLoaded`, `ReplayStarted`, `ReplayFinished` → `ReplayRuntime`/`HistoryManager`

(Catalogue seeded in ADR-004; this spec makes ownership explicit and mandates a single `domain/events` registry with schema versioning.)

### 4.2 Event guarantees (must hold for all events)
- **Immutability:** frozen value objects; never mutated after publish.
- **Lifetime:** events retained in the persistent log until `ReplayFinished` + retention policy; consumer-local state is rebuilt from the log on replay.
- **Replay compatibility:** every event carries a schema `version` and an `event_id` + `instrument_id` + `ts`. Old schemas are forward-compatible via migration shims; replay re-emits *canonical* domain events (not raw feeds).
- **Idempotency:** handlers key off `event_id`; re-delivery (DLQ redrive, replay) is safe. OMS/Portfolio are idempotent on `event_id`.


---

## 5. Runtime Lifecycle

Two distinct sequences: the **boot/composition** sequence and the **trading session** lifecycle.

### 5.1 Boot / Composition (RuntimeContext)
```
Config (env/secrets) ─▶ DI/Composition root (RuntimeContext)
   ─▶ BrokerSession(s) (auth + capability negotiation)
   ─▶ InstrumentRepository (warm from cache/master)
   ─▶ MarketDataRuntime (feed adapters)
   ─▶ DomainEventBus (shared)
   ─▶ TradingRuntime (OMS, Risk, Execution)
   ─▶ StrategyRuntime / ScannerRuntime / AnalyticsRuntime
   ─▶ Parity gate
   ─▶ API / CLI serve
   ─▶ Shutdown (drain bus, flush persistence, close sessions)
```
*Difference from current:* today `TradingRuntimeFactory` imports `cli.services`, coupling runtime to CLI. Target: `RuntimeContext` sits **below** `cli`/`api` and is UI-agnostic.

### 5.2 Trading session lifecycle
```
Startup
  ─▶ Configuration (load strategy/scanner/risk config)
  ─▶ Broker Login (BrokerSession auth)
  ─▶ Metadata (InstrumentRepository refresh)
  ─▶ Instrument Cache (warm Instruments + OptionChains)
  ─▶ Warm History (HistoryManager loads recent series)
  ─▶ Start Streams (LiveSubscriptions)
  ─▶ Trading (signals → risk → orders → execution)
  ─▶ Market Close (halt new orders, finalize positions)
  ─▶ Replay (optional; deterministic, §8)
  ─▶ Shutdown (drain, flush, close)
```

---

## 6. Execution Architecture (the platform backbone)

The order lifecycle is the spine of the system. A signal is never directly an order; it passes through explicit, testable stages.

```
Signal            (StrategyRuntime emits)
  ─▶ Risk         (RiskPort: limits, exposure, greeks)
  ─▶ Sizing       (position sizing model)
  ─▶ Order Intent (domain object, not a broker call)
  ─▶ OMS          (order lifecycle, idempotency, state machine — domain-owned)
  ─▶ Broker       (BrokerSession / ExecutionProvider adapter)
  ─▶ Exchange     (venue)
  ─▶ Execution Report (normalized → Domain Event)
  ─▶ Portfolio    (PositionManager updates)
  ─▶ PnL          (mark-to-market on QuoteChanged)
  ─▶ Analytics    (persist + report)
```

Requirements:
- `OrderIntent` and `Order` are domain objects; the OMS state machine is **domain-owned** (kills the `infrastructure/state_machine.py` leak).
- `Execution Report → Domain Event` path is identical for live and replay (§8).
- OMS is idempotent on `event_id` (§4.2).
- Risk runs *before* sizing and *before* broker submission; reject paths return an `OrderRejected` event without touching the exchange.



---

## 7. Scanner Architecture (pipeline, not a package)

Screening is a deterministic pipeline composed from ports, producing a ranked selection that feeds strategies.

```
Universe          (InstrumentRepository selection / watchlist)
  ─▶ Market Data  (LiveSubscription / HistoryManager)
  ─▶ Feature Extraction (VOs: quote, depth, ohlc)
  ─▶ Indicators   (domain primitives; single source)
  ─▶ Scoring      (model/rule score per instrument)
  ─▶ Ranking      (sort by score)
  ─▶ Selection    (top-N / threshold)
  ─▶ Strategy Input (selected universe → StrategyRuntime)
```

Requirements:
- One indicator implementation in `domain/indicators` (single source; analytics imports it). Kills duplicate indicator impls.
- The pipeline is replayable: fed by `HistoryManager` under `ReplayRuntime`.
- `ScannerRuntime` owns pipeline orchestration; the `analytics/scanner` + `application/scanner` split is collapsed into this runtime.

---

## 8. Replay Architecture

Replay is **not** a separate code path — it is the live runtime driven by a historical `DataProvider`. This is principle 8 made concrete.

```
Historical Feed (datalake parquet/duckdb)
  ─▶ Normalizer (→ canonical domain VO; SAME normalizer contract as live)
  ─▶ Market Events (Domain Events, versioned, ordered per instrument)
  ─▶ RuntimeContext (exact same runtimes as live)
  ─▶ Strategies (cannot distinguish from live)
  ─▶ OMS (same lifecycle, idempotent)
  ─▶ Analytics (same reporting)
```

Requirements:
- `ReplayRuntime` reuses `TradingRuntime`, `StrategyRuntime`, `OMS`, `EventBus`. Only the `DataProvider` (historical) and `ExecutionProvider` (simulated fill) differ — injected at composition.
- A virtual clock advances events deterministically; `event_id` ordering matches §4.2.
- Backtest parity gate (`runtime/parity_gate.py`) asserts strategy/OMS behaviour is identical between `ReplayRuntime` and live given the same feed.

---

## 9. Package Organization & Dependency Rules

Organize by business capability, not technical type. Target hierarchy (brokers are adapters
under `infrastructure`; SDK/CLI/API are `interfaces`):

```
src/
  domain/            # business capabilities, NOT technical types
    instruments/ market/ orders/ portfolio/ accounts/
    analytics/ scanner/ strategies/ replay/ risk/
    events/ ports/
  application/       # use-cases / workflows
    workflows/ orchestration/ commands/ queries/
  infrastructure/     # adapters implementing domain ports
    brokers/ storage/ datalake/ cache/ messaging/ persistence/
  interfaces/         # delivery mechanisms
    sdk/ cli/ api/
  runtime/            # RuntimeContext + runtimes (mount application + infra)
  config/
```

Every package has a single responsibility; `runtime/` is the composition root that mounts
`application` workflows and `infrastructure` adapters. This is reorganized **last** (Phase G),
after the models above are fixed.

Layers (outer depends on inner only):

```
┌──────────────────────────────────────────────────────────────┐
│  entry points: cli / api / scripts                            │
├──────────────────────────────────────────────────────────────┤
│  application: use-cases (oms, execution, trading, portfolio,  │
│               scanner, backtest) — orchestration only          │
├──────────────────────────────────────────────────────────────┤
│  infrastructure / brokers / market_data / datalake:           │
│     ADAPTERS of domain/ports                                   │
├──────────────────────────────────────────────────────────────┤
│  domain: entities, aggregates (single set), value objects,    │
│         ports, events  ◀── no upward imports, ever             │
└──────────────────────────────────────────────────────────────┘
```

Hard rules:
- `domain` imports **zero** symbols from `brokers`, `infrastructure`, `application`, `cli`, `api`.
- `application` depends on `domain` (ports/abstractions) only, never `infrastructure` directly (kills the 30+ `ignore_imports` carve-outs).
- `infrastructure/brokers` and `infrastructure/datalkae` are adapters of `domain/ports`; they may depend on `domain` and `infrastructure` primitives, never on `application`/`cli`.
- `analytics` depends on `domain` + `datalake` **through a port**, never a concrete `datalake.gateway`.
- `brokers.common` = broker-agnostic core only (normalizers, errors, ports impls). Orchestration/routing/historical/provenance move to `application`/`market_data`.

These rules are enforced by `.import-linter.ini` contracts + `tests/test_architecture.py` (including in-function/lazy imports — the current red guardrail).



---

## 10. Migration Plan (Architecture-Led, Phase A–G)

This replaces a cleanup-first sequence. Each phase is gated by tests and is justified by a gap in the Current State Assessment.

### Phase A — Architecture Baseline
- Finalize this specification (runtime, object, event, dependency models).
- Ratify architecture principles (§1) as enforced rules.
- **Output:** this doc + ADR updates; no code yet.

### Phase B — Domain (object model, §3)
- Single `Instrument` model; kill `domain.aggregates` duplicates.
- `InstrumentRepository`, `OptionChain`/`Option` canonical, `Quote`/`MarketDepth` VOs, `Order`/`Position` state machines moved into `domain`.
- `HistoryManager` port + impl.
- **Kills:** D3, D9, D10 (duplicate domain objects), god-file `capability_manifest`.

### Phase C — Runtime (runtime model, §2)
- `RuntimeContext` as UI-agnostic composition root (decouple from `cli`).
- `BrokerSession` lifecycle + capability negotiation.
- `DomainEventBus` as the event port; `LiveSubscription` manager.
- Event types defined in `domain/events` (ADR-004).

### Phase D — Broker SDK (adapters, principle 3)
- Capability model finalized; adapters self-register (registry/plugin, ADR-001/005).
- `brokers.common` shrunk to broker-agnostic core; orchestration removed.
- Object-oriented SDK facade (`tradexv2.connect(broker).instrument("X").buy()`).
- **Kills:** D1 (lazy broker imports), D2 (god-package), D5.

### Phase E — Trading Engine (pipelines, §6–§8)
- `ScannerRuntime` (pipeline), `StrategyRuntime`, `OMS` (domain-owned), `Risk`, `Execution` stages.
- Single normalization boundary (broker → canonical VO).
- **Kills:** D4, D6, D7, D8.

### Phase F — Infrastructure
- Persistence, cache, `ReplayRuntime` (parity with live), observability.
- `analytics → datalake` via port.
- **Kills:** D12, D13.

### Phase G — Cleanup (last, not first)
- Package consolidation / renames (driven by §9 + §3 models).
- Remove duplicates, tighten import-linter contracts, remove deprecated APIs.
- Delete dead packages (`markets/`, empty `brokers/runtime`).
- **This is the only phase the Current State Assessment's "cleanup" items belong to.**

```
A ─▶ B ─▶ C ─▶ D ─▶ E ─▶ F ─▶ G
(architecture-led; each phase gated green before next starts)
```

---

## 11. Current State → Target Gap (what drives the work)

| Target concept | Current state | Gap → drives phase |
|---|---|---|
| `RuntimeContext` (UI-agnostic) | `trading_runtime_factory` coupled to `cli` | C |
| `BrokerSession` | exists (`brokers/common/objects/session.py`) but lazy-imports brokers | D (registry) |
| `InstrumentRepository` (single owner) | instrument master has 3 owners | B |
| `Instrument` single source | `entities` + `aggregates` duplicates | B |
| `DomainEventBus` as port | event types in `infrastructure/event_bus` | C |
| `Order`/`Position` state machine in domain | lives in `infrastructure/state_machine.py` | B/E |
| Single normalization boundary | duplicated in `brokers.common`/`datalake`/`analytics` | E |
| `ReplayRuntime` parity | replay partially bypasses broker boundary | F |
| `ScannerRuntime` pipeline | split `analytics/scanner` + `application/scanner` | E |
| Package reorg | premature without models above | G |

The full ranked debt list remains in `TECHNICAL_DEBT.md`; this table is the *architecture-filtered* view that the roadmap executes against.

---

*This specification is the target. `ARCHITECTURE_REVIEW.md` is the current state. `REFACTORING_ROADMAP.md` executes the gap between them, in Phase A→G order.*

- **Ordering:** per-`instrument_id` ordering is guaranteed (sharded bus); cross-instrument ordering is not guaranteed and handlers must not assume it.

## 12. Per-Phase Validation Checklist

Each phase merges only when its checklist is green. See `TESTING_STRATEGY.md` and `RISK_ASSESSMENT.md`.

- **Phase A (Baseline):** [ ] spec + ADRs ratified; [ ] import-linter analyzes in-function imports; [ ] `tests/test_architecture.py` green on current violations; [ ] `lint-imports` red on D1 until fixed.
- **Phase B (Domain):** [ ] `domain.aggregates` deleted; [ ] one definition per concept (lint gate); [ ] `Quote`/`QuoteSnapshot` unified; [ ] `Order`/`Position` state machine in `domain`; [ ] domain suite green.
- **Phase C (Runtime):** [ ] `RuntimeContext` decoupled from `cli`; [ ] boots live + replay; [ ] event types in `domain/events`; [ ] parity gate green.
- **Phase D (Broker SDK):** [ ] capability-driven registry (no hardcoded broker imports); [ ] adding a broker = new package only; [ ] OO SDK facade works; [ ] fitness test green on `brokers.common` isolation.
- **Phase E (Trading Engine):** [ ] `OrderIntent` + idempotent OMS submit; [ ] Risk gate; [ ] `ScannerRuntime`/`StrategyRuntime`; [ ] Signal→PnL test live + replay.
- **Phase F (Infrastructure):** [ ] Event Store + replay `EventSource`; [ ] replay reproduces live stream; [ ] zero `application → infrastructure` concrete imports (carve-outs removed); [ ] data-lake validation tests pass.
- **Phase G (Cleanup):** [ ] `market_data` promoted / folded; [ ] dead packages deleted; [ ] `scripts/` folded; [ ] `lint-imports` green with **zero** `ignore_imports`; [ ] full suite + parity green.
