# TradeXV2 — Architecture Discovery & Review (Phase 0)

- **Date:** 2026-07-08
- **Commit reviewed:** `7ca47df` (graphify corpus built from same commit)
- **Branch:** `agent/p0-smart-gateway-contract`
- **Status:** DISCOVERY ONLY. No source files were modified. This document is the
  gap analysis between the *current* architecture and the *target* architecture.
- **How to read:** Sections 0–12 map 1:1 to the requested deliverables. Companion
  files: `TECHNICAL_DEBT.md`, `REFACTORING_ROADMAP.md` (incl. Migration Plan),
  `ADRS.md`.

---

## 0. Executive Architecture Assessment

### 0.1 Verdict
The system is **further along than an "inventory" suggests**. A DDD `domain` layer,
port-based broker abstraction, an event-driven core (EventBus hub), import-linter
contracts, and an architecture fitness test already exist. The dominant risk is **not
missing architecture** — it is **(a)** an oversized `brokers` package that has absorbed
orchestration/OMS concerns, **(b)** hidden layer violations masked by lazy imports, and
**(c)** a half-migrated domain (parallel `entities`/`aggregates` models plus legacy
shims). The blueprint is roughly right; the execution is incomplete and partially
unguarded.

### 0.2 What is already good (preserve)
- **Clear DDD intent**: `src/domain` with `aggregates/`, `entities/`, `options/`,
  `futures/`, `exchanges/`, `quotes/`, `specifications/`, `ports/` (23 port modules).
- **Broker-agnostic by design**: ports `BrokerGateway`, `MarketDataGateway`,
  `DataProvider`, `ExecutionProvider`, `SubscriptionHandle`; a capability manifest in
  `src/domain/capability_manifest.py`; a broker `registry`/`broker_port`.
- **Event-driven core**: `infrastructure/event_bus/` with dead-letter queue, priority,
  persistent crash recovery, and replay scripts (`scripts/verify_event_replay.py`).
- **Guardrails exist**: `.import-linter.ini` (15 contracts) + `tests/test_architecture.py`.
- **Object-oriented SDK**: `Instrument.buy()` / `Instrument.sell()`
  (`src/domain/instruments/instrument.py:411,421`) — answers the "stock.buy() vs
  broker.buy()" question in favour of `stock.buy()`.
- **Single composition root**: `runtime/trading_runtime_factory.py`
  (`TradingRuntimeFactory`) unifies CLI/API/scripts wiring.

### 0.3 Critical gaps (current → target)
1. **`brokers/` is a 86k-LOC god-package (531 files).** `common` alone has **39
   top-level modules** including `router`, `stream_orchestrator`, `historical_coordinator`,
   `provenance`, `intelligent_market_gateway`, `connection_pool`, `quota_*`, `policy`,
   `capabilities`, `instruments`, `bootstrap`, `factory`, `gateway`. This violates
   "broker implementation must not leak upward" and "common = broker-agnostic core only".
2. **Hidden layer violations.** `brokers.common` *lazily* imports `brokers.dhan` /
   `brokers.upstox` inside function bodies (`adapter_factory.py:35-36`,
   `oms/margin_provider.py:39`, `infrastructure.py:13-14`). `lint-imports` exits 0
   (default analysis ignores in-function imports) **but `tests/test_architecture.py`
   FAILS** — the guardrail is currently red.
3. **Parallel domain models.** `domain.aggregates` is deprecated (emits
   `DeprecationWarning`) yet coexists with `domain.entities` / `domain.instruments` /
   `domain.options`. `OptionChain`, `Instrument`, `Order`, `Position` are each defined
   **twice** (e.g. `src/domain/entities/options.py:101` vs `src/domain/options/option_chain.py:24`).
   No single source of truth.
4. **OMS bypasses ports.** `application.oms.*` imports `infrastructure.*` directly
   (import-linter `application-infrastructure-separation` carries 30+ `ignore_imports`
   carve-outs — acknowledged, tracked debt).
5. **`market_data` package dismantled.** There is no `market_data/` Python package
   (only a data directory). Market-data responsibility is scattered across `brokers.common`,
   `infrastructure`, `datalake`, `analytics`, `src/domain/quotes` — no single owner.
6. **Dead/empty packages.** `markets/` (empty), `brokers/runtime/` (0 files),
   `domain.aggregates` (deprecated).
7. **Multiple composition mechanisms.** Custom `infrastructure.di.Container`
   (singleton/transient/request) + `runtime.composition.create_api_event_bus` +
   `brokers.common.registry` / `broker_port`. Overlap/ambiguity in wiring.
8. **Procedural sprawl.** 35 `scripts/*.py` (diagnostics, verification, migration) —
   operational logic not yet productized into commands/services.

### 0.4 Recommendation
**Do not begin a broad package reshuffle yet.** The target shape is already encoded in
`brokers-architecture.mmd` and `.import-linter.ini`. Sequence the work as:
1. Make the guardrails *truthful* (fix the 2 failing fitness tests + enable internal-import
   linting) — see ADR-001.
2. Complete the domain consolidation (delete `domain.aggregates`; finish shim removal).
3. Split `brokers.common` into broker-agnostic core vs orchestration.
4. Only then perform package re-org. Full sequencing in `REFACTORING_ROADMAP.md`.

---

## 1. Business Capability Map

| Capability | Primary owner (current) | Bounded context? | Notes |
|---|---|---|---|
| Trading / Execution | `application/execution`, `application/trading` | ✅ | Orchestrator + execution service |
| OMS / Order lifecycle | `application/oms` | ✅ | OrderManager, PositionManager, RiskManager, reconciliation |
| Market Data (live) | `brokers.common` (gateways) + `infrastructure/market_data_adapter` | ⚠️ split | No single owner (see gap 5) |
| Market Data (historical) | `brokers.common/historical_coordinator`, `datalake` | ⚠️ split | |
| Portfolio | `application/portfolio` | ✅ | |
| Accounts | `domain.aggregates/account`, `brokers.common` | ⚠️ | AccountAggregate deprecated |
| Risk | `application/oms` (RiskManager) + `domain/constants/risk.py` | ✅ | |
| Analytics | `analytics/` | ✅ | 22 subpackages |
| Scanner | `analytics/scanner`, `application/scanner` | ⚠️ split | Two scanner homes |
| Strategies | `analytics/strategy`, `domain/ports/strategy_evaluator` | ✅ | |
| Replay / Backtest | `analytics/replay`, `analytics/backtest`, `datalake/fast_backtest` | ⚠️ split | |
| Options / Greeks | `domain/options`, `datalake/options_*` | ✅ | |
| Broker Integration | `brokers/` | ✅ (too big) | God-package |
| Configuration | `config/` | ✅ | |
| Observability | `infrastructure/observability`, `api/freshness`, `api/middleware` | ✅ | |
| Authentication | `brokers/*/auth`, `api/auth`, `config/secrets_manager` | ⚠️ split | Per-broker auth + API auth |
| Research | `datalake/research_dataset`, `analytics/*` | ✅ | |
| CLI | `cli/` | ✅ | 125 files |
| API | `api/` | ✅ | FastAPI |

**Questions answered**
- *Are these bounded contexts?* Mostly yes, but Market Data, Scanner, Replay/Backtest,
  Accounts, and Authentication are **split across 2+ packages** → not yet clean contexts.
- *Should some be merged/split?* **Split** `brokers` (the single biggest issue). **Merge**
  `analytics/scanner` + `application/scanner`, and `analytics/replay` + `analytics/backtest`
  + `datalake/fast_backtest` under one "Backtesting/Replay" context.
- *Is every capability owned by exactly one module?* No — see the ⚠️ rows.

---

## 2. Bounded Context Map

```
┌──────────────┐   ports    ┌──────────────────────────────┐
│   DOMAIN     │◀──────────▶│  Broker Adapters (Dhan/Upstox) │
│ (entities,   │  (BrokerGW,│  ── wrapped by ──            │
│  aggregates, │   MktDataGW)│  brokers.common (TOO BIG)    │
│  ports, VO)  │            └──────────────────────────────┘
└──────┬───────┘
       │ depends on ports only
┌──────▼──────────────────────────────────────────────┐
│  APPLICATION (OMS, Execution, Trading, Portfolio,     │
│  Scanner, Backtest)  ── uses ──▶ INFRASTRUCTURE        │
│  (event_bus, di, persistence, resilience, observability)│
└───────────────────────────────────────────────────────┘
       │
   ANALYTICS ──(reads domain + datalake)──▶ DATALAKE (DuckDB/Parquet)
       │                                        ▲
       └──────────── CLI / API ────────────────┘  (entry points)
```

**Observation (target vs reality):**
- Intended (`brokers-architecture.mmd`): `Instruments → Ports → Adapters → Gateways →
  Composition Root`. That is sound.
- Reality: `brokers.common` sits *between* ports and adapters but also *performs*
  routing, stream orchestration, historical coordination, provenance, and intelligent
  gateway selection — i.e. it has absorbed Application/Infrastructure responsibilities.

---

## 3. Domain Model Review

| Object | Type (should be) | Current location | Assessment |
|---|---|---|---|
| `Instrument` | Entity + Aggregate root | `domain.instruments.instrument` (+ `aggregates/instrument` **deprecated**) | **Duplicate.** Rich behaviour (`buy/sell`) is good. Kill the aggregate copy. |
| `InstrumentId` | Value Object | `domain.instruments/instrument_id.py` | ✅ Strong identity VO |
| `OptionChain` | Aggregate | `domain.options/option_chain.py` (canonical) + `domain.entities/options.py:101` (**legacy**) | **Duplicate.** Migrate refs to `domain.options`. |
| `Quote` / `QuoteSnapshot` | Value Object | `domain.entities/market.py:176` + `ports.protocols.QuoteSnapshot` | Two representations; unify on `QuoteSnapshot`. |
| `MarketDepth` | Value Object | `domain.entities` | ✅ |
| `Order` | Entity + Aggregate | `domain.entities/order.py:60` + `domain.aggregates/order.py` (**deprecated**) | **Duplicate.** State machine lives in infra (`state_machine.py`) — should be domain-owned. |
| `Trade` | Entity/VO | `domain.entities/trade.py:13` | ✅ |
| `Position` | Entity + Aggregate | `domain.entities/position.py:13` + `domain.aggregates/position.py` (**deprecated**) | **Duplicate.** Lifecycle owned by `application.oms.PositionManager` (acceptable). |
| `Portfolio` | Aggregate | `application/portfolio` | ✅ (application-level aggregate) |
| `Account` | Aggregate | `domain.aggregates/account` | ⚠️ Only in deprecated layer — needs a canonical home in `domain`. |
| `Option`/`Future` | Entity/VO | `domain.options`, `domain.futures` | ✅ |
| `HistoricalSeries` | Value Object | `analytics` (graph hub) | ⚠️ Analytics-defined; should be a domain VO consumed by analytics. |
| `Strategy` | Entity/Service | `analytics/strategy` + `ports/strategy_evaluator` | ✅ port exists |
| `Scanner` | Service | `analytics/scanner` + `application/scanner` | ⚠️ Two homes |
| `CapabilityManifest` | Value Object / config | `domain/capability_manifest.py` (1279 LOC) | ✅ in domain, but **god file** — split per capability group. |
| `Event` / `DomainEvent` | Domain Event | `infrastructure/event_bus/event_types` | ⚠️ Events defined in infra, not domain. Replay-compatible (buffered log exists). |

**Recurring problems**
- **Duplicate state**: 4 core objects defined twice (`entities` vs `aggregates`).
- **Infrastructure leakage**: order/position state machines and events live in
  `infrastructure`, not `domain`.
- **Missing invariants**: domain objects rely on `application`/infra for lifecycle rules.
- **God file**: `capability_manifest.py` (1279 LOC) and `brokers/common` modules.

---

## 4. Package Organization Review

**Current top-level packages (Python LOC):**

| Package | Files | LOC | Verdict |
|---|---|---|---|
| `brokers` | 531 | 86,000 | ❌ God-package |
| `analytics` | 135 | 22,119 | ⚠️ Large but cohesive |
| `cli` | 125 | 21,894 | ⚠️ Large; mixes commands + services |
| `datalake` | 115 | 18,097 | ✅ Cohesive |
| `src/domain` | 184 | 15,682 | ✅ (but has parallel `aggregates`) |
| `application` | 82 | 14,542 | ✅ (OMS reaches into infra) |
| `infrastructure` | 73 | 12,293 | ✅ |
| `api` | 42 | 7,430 | ✅ |
| `config` | 20 | 4,095 | ✅ |
| `runtime` | 7 | 509 | ✅ thin composition root |
| `plugins` | 9 | 77 | ⚠️ Near-empty |
| `providers` | 4 | 298 | ⚠️ Near-empty / overlapping with `domain/providers` + `brokers/common/registry` |
| `market_data` | 0 | 0 | ❌ Dismantled (data dir only) |
| `markets` | — | — | ❌ Dead/empty |

**Target hierarchy (proposal — see ADR-004):**
```
src/
  domain/            # entities, aggregates (single set), value objects, ports, events
  application/       # use-cases: oms, execution, trading, portfolio, scanner, backtest
  brokers/
    common/          # ONLY broker-agnostic core (ports impls, normalizers, errors)
    dhan/ upstox/ paper/
  market_data/       # PROMOTED: live + historical feeds, normalization, replay source
  analytics/         # indicators, scanner, strategy, options, reporting
  datalake/          # storage, parquet/duckdb, research datasets
  infrastructure/    # event_bus, di, persistence, resilience, observability
  api/ cli/ config/ runtime/
```
Key moves: (1) shrink `brokers.common` and move orchestration/routing/historical/
provenance/intelligent-gateway OUT to `application`/`market_data`/`infrastructure`;
(2) **promote market_data to a real package**; (3) delete `markets`, `domain.aggregates`,
near-empty `plugins`/`providers` (fold into `domain/providers` + `brokers/common/registry`).

---

## 5. Layer Review Matrix

| Package | Current layer | Expected layer | Reason | Migration |
|---|---|---|---|---|
| `brokers/common` (router, stream_orchestrator, historical_coordinator, provenance, intelligent_market_gateway) | Infrastructure/Common | **Application / Market Data / Infrastructure** | These are orchestration, not broker-agnostic core | Split out (ADR-004) |
| `domain.aggregates` | Domain | **Delete** | Superseded by `domain.entities`/`instruments`/`options` | Consolidate, remove |
| `domain.events` (in infra) | Infrastructure | **Domain** | Events are domain concepts | Move `event_types` to `domain` |
| `application.oms.* → infrastructure.*` | Application | Application (via ports) | OMS must depend on abstractions | Extract ports, inject |
| `analytics → datalake.gateway/research` | Analytics | Analytics (via port) | Concrete datalake imports violate layering | Route through `datalake` port/adapter |
| `capability_manifest.py` (1279 LOC) | Domain | Domain (split) | God file | Split per capability group |
| `indicators` (domain + analytics) | Both | Domain (primitives) + Analytics (strategies) | Two indicator impls risk drift | Single source in domain; analytics imports it |
| `markets/` | — | **Delete** | Empty/dead | Remove |

---

## 6. Dependency Graph & Violations

**Runtime god-nodes (graphify, edge count = coupling):**
`EventBus` (494) · `OmsOrderCommand` (298) · `BrokerGateway` (297) ·
`FeaturePipeline` (281) · `BrokerService` (253) · `OrderManager` (250) ·
`PositionManager` (209) · `Trade` (199) · `TradingContext` (192) ·
`UpstoxBrokerGateway` (187).

→ The system is correctly **event-centric**; `EventBus` is the backbone.

**Cycles (graphify):**
- Self-cycles in `cli/commands/analytics_*.py` and `datalake/quality_universe.py`,
  `research_dataset.py` (inference artifacts — verify, likely benign).
- **Real 3-file cycle**: `cli/services/broker_service.py → oms_setup.py →
  capital_provider.py → broker_service.py`. Must be broken (introduce a port or move
  `CapitalProvider` into domain/application).

**Dependency violations:**
| # | Violation | Evidence | Severity |
|---|---|---|---|
| V1 | `brokers.common` → `brokers.dhan`/`upstox` (lazy) | `adapter_factory.py:35-36`, `oms/margin_provider.py:39`, `infrastructure.py:13-14` | **Critical** (fitness test fails) |
| V2 | `application.oms.*` → `infrastructure.*` | import-linter `application-infrastructure-separation` (30+ carve-outs) | High |
| V3 | `analytics` → concrete `datalake.gateway`/`research` | import-linter `analytics-no-datalake-concrete` (carve-outs) | Medium |
| V4 | `domain` shim imports (`brokers.common.core.*`) | `tests/test_architecture.py::test_no_shim_imports_in_production_code` (enforced, passing) | Low (being cleaned) |
| V5 | `cli/services` cycle | graphify 3-file cycle | Medium |

**Why `lint-imports` passes but the fitness test fails:** import-linter analyses
*module-level* imports by default; the V1 violations are **inside function bodies**
(lazy imports), so they are invisible to it. The AST-based fitness test catches them.
**Fix:** enable import-linter internal-import analysis OR convert the lazy imports into
a registry/plugin lookup (preferred — see ADR-001).

---

## 7. Runtime Lifecycle

Boot order (from `runtime/trading_runtime_factory.py` + `runtime/composition.py` +
`brokers/common/bootstrap.py`):

```
Config (env/secrets) ─▶ DI container (infrastructure.di) ─▶ Broker auth
   ─▶ Broker gateway / MarketDataGateway ─▶ EventBus (shared BrokerService+OMS)
   ─▶ TradingContext (OMS) ─▶ TradingOrchestrator (optional)
   ─▶ IntelligentMarketDataGateway (optional, ENABLE_INTELLIGENT_GATEWAY)
   ─▶ Parity gate (runtime/parity_gate) ─▶ API/CLI serve ─▶ Shutdown (drain)
```

**Issues**
- The composition root (`TradingRuntimeFactory`) imports `cli.services.broker_service`
  and `cli.services.oms_service` → **runtime couples to CLI**. Composition should sit
  below `cli`.
- Two wiring styles coexist: `infrastructure.di.Container` (string-keyed) and
  `runtime.composition.create_api_event_bus`. Pick one as the canonical root.
- `ENABLE_INTELLIGENT_GATEWAY` / `ORCHESTRATOR_DRY_RUN` env flags gate major behaviour
  — acceptable for rollout, but should become explicit config, not env side-effects.

---

## 8. Event Flow

```
Broker tick/order ─▶ MarketDataGateway/OMSGateway ─▶ EventBus.publish
   ─▶ subscribers: Analytics, Strategy evaluator, OMS OrderManager/PositionManager,
      Reconciliation, Audit, Observability
   ─▶ dead-letter queue (on handler error) ─▶ persistent DLQ ─▶ replay
```

**Assessment**
- EventBus is well-built (priority, sharded locks, DLQ, persistence, replay scripts).
- **Gap:** event *types* live in `infrastructure/event_bus/event_types`, not `domain`.
  Domain events should be defined in `domain` and the bus should be a port.
- **Gap:** no single catalogue of domain events / ownership / schema versioning.
  Recommend an explicit event registry for replay compatibility guarantees.

---

## 9. Data Flow

```
Broker (Dhan/Upstox) ─▶ normalize (brokers.common normalizers)
   ─▶ Domain (Quote/Depth/Instrument VOs) ─▶ MarketDataAdapter (infrastructure)
   ─▶ Analytics (features/indicators/scanner) ─▶ Strategy evaluator
   ─▶ OMS (OrderManager → ExecutionProvider → Broker) ─▶ Persistence (sqlite/duckdb)
                                   ▲
        Replay/Backtest feed from datalake (parquet/duckdb) replaces Broker leg
```

**Issues**
- Normalization is duplicated: `brokers.common` normalizers **and** `datalake/normalize.py`
  and `analytics` transforms. One normalization boundary (broker → canonical domain VO)
  should feed everything.
- `analytics` reaches concrete `datalake.gateway`/`research` (V3) instead of a port.
- Replay currently bypasses the broker boundary partially; must be a first-class
  `DataProvider` implementation so strategies/OMS cannot tell replay from live.

---

## 10. Public SDK Review

**Current surface**
- Object-oriented: `Instrument.buy()` / `Instrument.sell()` ✅ (good — `stock.buy()`).
- Ports are explicit and rich: `BrokerGateway`, `MarketDataGateway`, `DataProvider`,
  `ExecutionProvider`, `SubscriptionHandle`, `OrderTransportPort`.
- Multiple entry points: `cli/main.py` (Click), `api/main.py` (FastAPI),
  `scripts/*.py`, `runtime/trading_runtime_factory`.

**Issues**
- **Two gateway port files with confusing naming:** `domain/ports/broker_gateway.py`
  defines `OrderTransportPort` (not "BrokerGateway"); the actual `BrokerGateway` /
  `MarketDataGateway` live in `domain/ports/protocols.py`. Consolidate port naming.
- **Discovery:** a developer must know to import `Instrument` then call `.buy()`. There
  is no top-level `tradexv2` facade aggregate (e.g. `tradexv2.connect(broker).instrument("X").buy()`).
- **Consistency:** some flows use the OO `Instrument` API; others use the lower-level
  `BrokerService`/`OMSGatewayProxy` APIs directly. Pick the OO path as the public SDK and
  keep the service layer internal.

---

## 11. Broker Architecture Review

**Target (`brokers-architecture.mmd`):** `Instruments → Ports → Adapters → Gateways →
Composition Root` — sound and should be the contract.

**Current reality**
- `brokers/common` (28.7k LOC, 39 modules) has absorbed **router**, **stream_orchestrator**,
  **historical_coordinator**, **provenance**, **intelligent_market_gateway**,
  **connection_pool**, **quota**, **policy**, **capabilities**, **instruments**,
  **bootstrap**, **factory**, **gateway**. This is far beyond "common".
- **Capability model:** `src/domain/capability_manifest.py` (good — in domain) + per-broker
  `capabilities.py`. The intelligent gateway selects sources by capability — good direction.
- **Extension model:** `plugins/` is near-empty (77 LOC) — the extension model is not yet
  realised; `ExtensionBundle`/`ExtensionRegistry` exist in graph but plugin surface is thin.
- **Auth:** per-broker (`DhanSessionManager`, `UpstoxTotpClient`), plus `api/auth`. TOTP
  refresh, token state stores, IP management — substantial and per-broker (acceptable, but
  should be behind a `BrokerAuth` port).
- **Subscription lifecycle:** `SubscriptionHandle` port exists; `BrokerStreamHandle` in graph.
  Upstox V3 multiplexer/subscription-manager are sophisticated.
- **Symbol mapping:** `SymbolResolver`/`InstrumentResolver` per broker — broker-specific
  (acceptable), but canonical `InstrumentId` should be the stable key (it is — good).
- **Metadata ownership:** `brokers.common/instruments.py` + `datalake` master + `domain`.
  Instrument master has multiple owners.

**Top broker issues**
1. `brokers.common` is too big and leaks upward (V1).
2. `adapter_factory` hard-codes broker selection via lazy imports (should be registry/plugin).
3. Instrument metadata has 3 owners.

---

## 12. Summary of Findings → Roadmap pointer

All findings are ranked in `TECHNICAL_DEBT.md`. The sequenced, gated migration plan is in
`REFACTORING_ROADMAP.md`. Architecture decision records are in `ADRS.md`.

**This document is the review only. No code was changed. Awaiting approval before any
implementation in `REFACTORING_ROADMAP.md` begins.**
