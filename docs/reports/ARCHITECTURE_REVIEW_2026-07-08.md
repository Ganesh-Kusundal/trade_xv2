# TradeX — Comprehensive Architecture Review & Trading OS Readiness Assessment

**Date:** 2026-07-08
**Reviewer:** Architecture Review Board (Clean Architecture / DDD / EDA / Quant Platform lenses)
**Method:** graphify knowledge-graph build (28,290 nodes / 57,118 edges / 836 communities) + 5 parallel subsystem reviews + first-hand code verification (grep/file reads). Where an agent claim could not be reproduced it is marked as such.

---

## 1. Executive Summary

TradeX is **further along than a typical "broker integration" project** and shows real architectural intent: a layered package structure (`domain`, `brokers`, `application`, `infrastructure`, `api`, `cli`, `analytics`, `datalake`), an enforced import-linter contract suite, a rich `MarketDataGateway` abstract contract, a first-class capability model, proper domain value objects (`Money`, `Quantity`), and a thread-safe event bus with dead-letter + replay infrastructure.

However, it is **not yet an independent Broker SDK on top of which a Trading OS can be built without architectural change.** The distance to that vision is concentrated in five concrete violations, all fixable without a rewrite:

| # | Finding | Severity |
|---|---------|----------|
| V1 | Application layer imports `infrastructure` directly in 10 production modules (8 in OMS) — Clean Architecture broken | **P0** |
| V2 | `src/domain/ports/event_publisher.py` imports + re-exports the concrete `infrastructure.event_bus.EventBus` — layering inversion; 27 non-test modules depend on the concrete bus | **P0** |
| V3 | Broker registration is hand-coded (`cli/services/broker_registry.py` `builders = {...}` + `_create_*` funcs); `[project.entry-points."tradex.brokers"]` is commented out; `plugins/*` are empty stubs — Open/Closed violation | **P1** |
| V4 | `brokers.common.bootstrap` imports `cli.services.broker_registry` — the SDK's composition root depends on the CLI, breaking SDK independence | **P1** |
| V5 | Composition layer reaches into SDK-internal modules (`brokers.common.router/stream_orchestrator/provenance/historical_coordinator/infrastructure`) via lazy imports instead of the public `BrokerGateway` port | **P2** |

Secondary findings: `OmsOrderCommand` (298 edges) leaked from application into `src/domain/aggregates/order.py`; `TradingContext` (192 edges) is a god-context; `cli/services/broker_service.py` (253 edges) is a CLI god-object with a coupled chain to `oms_setup`→`capital_provider`; `application/oms` is a god-subsystem.

**Verdict:** Greenfield-grade foundation, mid-stage execution. The vision is achievable with a focused 3-phase remediation (P0→P2) that extracts ports and moves infrastructure behind adapters — not a redesign.

---

## 2. Architecture Assessment

**Packages (root):** `src/domain`, `brokers` (common/dhan/upstox/paper/runtime), `application`, `infrastructure`, `api`, `cli`, `analytics`, `datalake`, `config`, `plugins`, `market_data`.

**Intended layering (from `.import-linter.ini`):** `domain` (center) ← `application`/consumers ← `brokers` (SDK) ← `infrastructure` (behind ports). Contracts forbid: `infrastructure→brokers/application`, `brokers.common→broker adapters`, `domain.ports→application/brokers/infrastructure`, `application→broker impls`, `api→cli`, `analytics→broker adapters`, `dhan↔upstox`.

**graphify structural signals:**
- **God nodes (most-connected):** `EventBus` (494), `OmsOrderCommand` (298), `BrokerGateway` (297), `FeaturePipeline` (281), `BrokerService` (253), `OrderManager` (250), `PositionManager` (209), `Trade` (199), `TradingContext` (192), `UpstoxBrokerGateway` (187).
- **Import cycle:** graphify flagged `cli/services/broker_service → oms_setup → capital_provider → broker_service`. Module-level verification shows `broker_service→oms_setup→capital_provider` is a real chain; `capital_provider` does **not** module-import `broker_service`, so the closing edge is a function-local/runtime back-reference, not a strict module cycle.
- **Cohesion:** community cohesion 0.01–0.08 (expected for a 28k-node graph; not in itself a defect, but confirms loose inter-module coupling dominated by the `EventBus` hub).

**Observed reality vs intent:** The *contracts exist and are mostly honored* (`api`, `analytics`, `brokers.common` are clean in production). The deviations are (a) infrastructure reached from `application` (V1), (b) the domain port reaching down to infrastructure (V2), and (c) broker discovery reached from `brokers.common.bootstrap` into `cli` (V4). These are **three instances of the same root cause**: the composition root / adapter wiring leaks upward into layers that should depend only on abstractions.

---

## 3. Expected vs Actual Comparison

| Aspect | Expected (vision) | Actual | Gap |
|--------|-------------------|--------|-----|
| Domain model | Rich OO, aggregates first | `InstrumentAggregate`, `Order`, `Trade`, `Position`, `Portfolio` are rich; `Money`/`Quantity` VOs | Minor (some anemic leakage) |
| Broker SDK independence | SDK reusable, no CLI/app deps | `brokers.common` clean **except** `bootstrap→cli.registry` | V4 |
| Provider framework | Open/Closed, plugin discovery | `MarketDataGateway` ABC + Protocols strong; **registration hand-coded** | V3 |
| Capability model | First-class | `BrokerCapabilities` + per-broker capability groups | Met |
| Clean Architecture | `application` depends inward | 10 `application` modules import `infrastructure` | V1 |
| EDA | domain depends on `EventPublisher` port | port re-exports concrete `EventBus`; 27 modules import concrete bus | V2 |
| Composition | via public `BrokerGateway` | `composer` reaches SDK-internal modules | V5 |
| Plugin model | entry-point discovery | `plugins/*` are empty stubs; entry points commented | V3 |
| Testing | pyramid + contract tests | 579u/34i/28e2e; no broker-SDK contract tests found | Gap |

---

## 4. Domain Model Review (`src/domain`)

**Strengths (verified):**
- `Instrument` (base) → `Equity`/`Index`/`Future`/`Option` uses **composition over inheritance** (delegates to injected `DataProvider`s). `InstrumentAggregate` is the rich aggregate owning identity + state; `Instrument` is a thin facade. Good DDD.
- `Quote`/`MarketDepth`/`OptionChain`/`HistoricalSeries` are value objects held in aggregate state.
- `Money` (`domain/value_objects/money.py`) and `Quantity` (`domain/value_objects/capability.py`) are proper VOs with invariants — **no primitive obsession** in the monetary/quantity space.
- `src/domain/ports` imports only interfaces (no `application`/`brokers`/`infrastructure`) — **port isolation holds**.
- `InstrumentFactory`, `OrderRepository` exist in `factories/`/`repositories/`.

**Defects:**
- **D1 — `OmsOrderCommand` leak:** `OmsOrderCommand` (298 edges) lives in `src/domain/aggregates/order.py` but is an anemic request object that belongs in `application`. It drags application semantics into the domain (DDD layering inversion). *Priority P2. Fix: move to `application` as a command, or make it a domain event.*
- **D2 — `TradingContext` god-context (192 edges):** aggregates market data + risk params + session. Tell-don't-ask smells. *Priority P3. Fix: split into `SessionContext` + `RiskContext` + `MarketDataContext`.*
- **D3 — `DomainEventBus` port dormant:** the domain publishes events manually via aggregates (`order.py:82` `self._event_bus.publish(...)`) using a `DomainEventBus` type, but the canonical port is `EventPublisher` (Protocol) and it is **not used for wiring** — the domain modules import the concrete bus (see §5/V2). *Priority P1. Fix: depend on `EventPublisher`, inject concrete at composition root.*

**Recommendation:** No domain redesign needed. Targeted refactors D1–D3.

---

## 5. Broker SDK Review (`brokers`)

**Independence (verified):** `brokers.common` has **zero** production imports of `cli`/`application`/`analytics`. Cross-broker imports (`dhan↔upstox`) are absent. The **only** SDK→CLI edge is `brokers.common.bootstrap → cli.services.broker_registry` (V4).

**Provider abstraction (verified, strong):**
- `brokers/common/gateway.py:57` `class MarketDataGateway(ABC)` with ~25 `@abstractmethod`s (quotes, depth, history, instruments, orders, portfolio, options, streaming, lifecycle).
- `brokers/common/broker_port.py:185` `CommonBrokerGateway(Protocol)` + `BrokerStreamHandle(Protocol)` — a Protocol-based public surface.
- Concrete gateways: `UpstoxBrokerGateway` (187 edges), `DhanHttpClient` (269 edges), `PaperGateway`.

**Capability model (verified, strong):** `brokers/upstox/capabilities/` defines `InstrumentsCapability`/`MarketDataCapability`/`OrdersCapability`/`PortfolioCapability`/`StreamingCapability`, aggregated by `upstox_capabilities()` into `BrokerCapabilities` (`brokers.common.capabilities`). First-class, not scattered booleans.

**Extensions (verified present):** `brokers/common/extensions/` = `forever_order`, `fundamentals`, `native_slice_order`, `news`, `super_order` modules.

**Internal concerns (verified encapsulated):** auth/token lifecycle, `MultiBucketRateLimiter`, `RetryExecutor`/`CircuitBreaker`, `DhanConnection`/`DhanMarketFeed`/`DhanDepth200Feed`/`DhanOrderStream` all live inside `brokers/*` and are not imported by `cli`/`api`/`analytics` in production.

**Defects:**
- **V3 — Registration is hand-coded:** `cli/services/broker_registry.py:74` `builders = {"dhan": _create_dhan, "upstox": _create_upstox, "paper": _create_paper}` plus `_create_*` functions (lines 260–312). Adding a broker requires editing this file — Open/Closed violation. The `[project.entry-points."tradex.brokers"]` group in `pyproject.toml` is commented out ("Phase 2 will populate these; leave empty for Phase 0"); `plugins/dhan|upstox|paper` contain **only `__init__.py`** (stubs). *Priority P1. Fix: enable entry-point discovery; `broker_registry` loads via `importlib.metadata.entry_points(group="tradex.brokers")`; `plugins/*` become real entry-point modules.*
- **V4 — Composition root inside SDK:** `brokers.common.bootstrap` imports `cli.services.broker_registry`. A `brokers/runtime` package already exists and is the correct home for the composition root. *Priority P1. Fix: move `bootstrap`/`broker_registry` wiring into `brokers/runtime` (or a standalone `composition` package); SDK ships without CLI knowledge.*
- **Note:** `bootstrap_gateway` (`broker_registry.py:137`) already has a "smart gateway" wrapping branch (`if smart:`) — consistent with the current `agent/p0-smart-gateway-contract` branch. This is the right seam to centralize gateway construction; finish it by routing *all* gateway creation through the SDK runtime, not the CLI.

**Recommendation:** The SDK's *contracts and internals are sound*. The gap is purely in **discovery/wiring (registration + composition root)**. Do **not** redesign the gateway/capability/extension model — make it discoverable.

---

## 6. Provider Framework Review

- **Abstraction:** `MarketDataGateway` (ABC) + `CommonBrokerGateway` (Protocol) + `BrokerStreamHandle` (Protocol) — well-defined.
- **Discovery:** hand-coded dict (V3). Not Open/Closed.
- **Capability:** first-class `BrokerCapabilities` + groups (met).
- **Extension loading:** modules exist but appear registered explicitly, not discovered; no entry-point/environment scan found.
- **Add-a-broker cost today:** edit `brokers.common.bootstrap` (move out per V4) and `cli/services/broker_registry.py` `builders` dict + add a `_create_*` function + optionally a `plugins/<name>/__init__.py`. → **requires modifying existing code** = OCP violation.

**Recommendation:** Implement entry-point-based discovery (V3). Once `brokers/*` self-register via `tradex.brokers` entry points and the SDK runtime wires them, adding a broker touches **zero** existing files.

---

## 7. Object-Oriented Design Review

| Smell | Location | Evidence | Action |
|-------|----------|----------|--------|
| God object (by coupling) | `EventBus` | 494 edges; 27 non-test modules import concrete bus | Dependency-invert (V2) |
| God object | `cli/services/broker_service.py` | 253 edges | Extract gateway lifecycle / OMS proxy / capital into services |
| God subsystem | `application/oms` | 8 of 10 infra-leaking modules; `OrderManager` 250, `PositionManager` 209 edges | Split along use-case boundaries |
| God context | `TradingContext` | 192 edges; market+risk+session | Split (D2) |
| Anemic leak | `OmsOrderCommand` | 298 edges in `domain/aggregates/order.py` | Move to application (D1) |
| Feature envy | `composer/execution.py` | reaches `brokers.common.router/models` | Depend on `BrokerGateway` port |
| Law of Demeter | `broker_service.active_broker()` returns `OMSGatewayProxy` wrapping gateway | CLI knows OMS-internal proxy | Hide behind a port |

No pervasive **primitive obsession** (VOs present). No inheritance abuse (composition preferred). The OOP issues are **coupling/god-node** problems, not modeling problems.

---

## 8. DDD Review

- **Aggregates:** `InstrumentAggregate`, `Order`, `Trade`, `Position`, `Portfolio`, `Account` — correct roots; invariants enforced inside (`order.py` VWAP fill price, status derivation). Bounded contexts mostly correct.
- **Entities / VOs:** rich entities; `Money`/`Quantity`/`QuoteSnapshot`/`MarketDepth` proper VOs.
- **Repositories:** `OrderRepository` port present; **but** `application/oms/persistence/sqlite_order_store.py` is a concrete SQLite store imported directly by `application` (V1) instead of behind the repository port.
- **Factories:** `InstrumentFactory` present and correctly placed.
- **Domain Services:** `RiskManager` sits in `src/domain/ports/risk_manager.py` (a port, not a service) — correctly a port; implement in SDK/application.
- **Domain Events:** present as types; `DomainEventBus`/`EventPublisher` port exists but **dormant/inverted** (V2).
- **Bounded Contexts:** `domain` is one large context; `analytics`, `datalake` are separate contexts that depend on the SDK, not the domain — acceptable.

**Verdict:** DDD is the *strongest* layer. Fix D1–D3 + wire `EventPublisher` and the repository port.

---

## 9. Workflow Review

| Workflow | Expected | Actual | Gap |
|----------|----------|--------|-----|
| Auth/Session | SDK token lifecycle internal | `brokers.common.auth` + `LifecycleManager` internal; `broker_registry` probes auth | Met (encapsulated) |
| Connection | reconnect/recovery internal | `DhanConnection`, `LifecycleManager` in SDK | Met |
| Instrument resolution | via `InstrumentFactory`/resolver | `UpstoxInstrumentResolver`, `SymbolResolver` | Met |
| Historical | `MarketDataGateway.get_history` | Abstract; `historical_coordinator` in SDK | Met |
| Quotes/Streaming | subscribe via `BrokerStreamHandle` | `DhanMarketFeed`/`Depth200Feed`/`OrderStream` | Met |
| Orders | `place_order` use case → `BrokerGateway` | `application/oms/order_manager` → concrete bus + SQLite store (V1) | Partial |
| Portfolio/Positions | `PositionManager` | 209 edges; imports infra (V1) | Partial |
| Option chains | `OptionChain` VO via adapter | `UpstoxAdapterContext`, options adapter | Met |
| Recovery | event replay + DLQ | `event_log.py`, `persistent_dead_letter_queue.py` present & thread-safe | Met (infra) |
| Shutdown | `LifecycleManager` ordered stop | `infrastructure/lifecycle` exists; `daily_pnl_reset_scheduler` imports it (V1) | Partial |

Most workflows are correctly implemented *inside the SDK*. The leaks appear only where the **application layer** touches infrastructure for ordering/persistence/scheduling.

---

## 10. Package Review

| Package | Health | Notes |
|---------|--------|-------|
| `src/domain` | **Good** | Rich aggregates/VOs; `OmsOrderCommand` leak (D1); port inversion (V2) |
| `brokers/common` | **Good** | Strong contracts; only blemish `bootstrap→cli` (V4) |
| `brokers/dhan`,`upstox`,`paper` | **Good** | Proper subclasses; no cross-imports; no shadow `domain/` |
| `brokers/runtime` | Underused | Correct home for composition root (fix V4) |
| `application` | **At risk** | 10 modules → `infrastructure` (V1); `composer` → SDK internals (V5); god `oms` |
| `infrastructure` | **Good infra, abused by callers** | EventBus/DLQ/event-log/replay solid; thread-safe; misused via concrete imports |
| `api` | **Clean** | No `cli`/`brokers` imports (verified) |
| `cli` | **At risk** | `broker_service` god-object (253 edges); coupled chain to `oms_setup`/`capital_provider` |
| `analytics` | **Clean** | No broker-adapter imports (verified) |
| `datalake` | Clean | No `cli` imports (contract) |
| `config` | OK | profiles + env handling |
| `plugins` | **Stub** | Only `__init__.py`; no discovery logic (V3) |
| `market_data` | **Empty** | 0 Python files despite rich directory tree — orphaned/aspirational; either populate or delete |

---

## 11. File-Level Review (highlights)

- `src/domain/ports/event_publisher.py` — **port imports + re-exports concrete `EventBus`** (V2). Highest-leverage fix.
- `application/oms/{context,order_manager,position_manager,reconciliation_service,factory,daily_pnl_reset_scheduler,_internal/order_state_validator}.py` + `application/audit.py` + `application/trading/{trading_orchestrator,feature_fetcher}.py` — 10 infra imports (V1).
- `application/composer/execution.py` — lazy `from brokers.common.models import ...` and routes via `self._router` (`brokers.common.router`); `composer/*` → `brokers.common.{router,stream_orchestrator,provenance,historical_coordinator,infrastructure}` (V5).
- `cli/services/broker_registry.py:74` — `builders` dict + `_create_*` (V3); `bootstrap_gateway:137` smart-wrap seam.
- `cli/services/broker_service.py` — 253-edge god-object; `oms_setup.py`, `capital_provider.py` coupled chain.
- `infrastructure/event_bus/event_bus.py` (444 LOC), `async_event_bus.py` (219), `processed_trade_repository.py` (485), `persistent_dead_letter_queue.py` (161) — solid, thread-safe; the problem is *who imports them*, not their internals.
- `brokers/common/gateway.py:57` `MarketDataGateway(ABC)` — the SDK's crown jewel; keep.
- `plugins/*/__init__.py` — empty stubs (V3).

---

## 12. Code Smell Assessment

God objects (by coupling): `EventBus`, `BrokerService`, `OrderManager`, `PositionManager`, `TradingContext`, `OmsOrderCommand`. Anemic leakage: `OmsOrderCommand`. Feature envy: `composer`. Law-of-Demeter: `broker_service.active_broker()`. Shotgun surgery: any change to event wiring touches 27 modules (V2). Circular-ish dependency: `cli/services` chain. Leaky abstraction: `event_publisher.py` re-export. Hidden infrastructure: `composer` lazy imports.

---

## 13. Technical Debt Assessment

| Debt | Type | Risk | Removal/Remediation |
|------|------|------|---------------------|
| `application→infrastructure` (10) | Leaky abstraction | High | Extract ports; inject adapters (V1) |
| `event_publisher` re-exports `EventBus` | Layering inversion | High | Remove re-export; depend on `EventPublisher` (V2) |
| `broker_registry` builders dict | Shotgun surgery / OCP | Med | Entry-point discovery (V3) |
| `bootstrap→cli.registry` | Hidden coupling | Med | Move to `brokers/runtime` (V4) |
| `composer→brokers.common.*` internals | Leaky abstraction | Med | Route via `BrokerGateway` (V5) |
| `OmsOrderCommand` in domain | Anemic leak | Low | Move to application (D1) |
| `market_data/` empty | Migration artifact | Low | Populate or delete |
| `plugins/*` stubs | Dead/aspirational | Low | Implement discovery (V3) |

**Recommendation:** Remove/remediate, do not preserve. The `ignore_imports` list in `.import-linter.ini` is tracking real debt — convert each ignore into a port extraction and then delete the ignore.

---

## 14. Testing Assessment

**Inventory:** ~579 unit, 34 integration, 28 e2e test files (venv excluded). Architecture tests exist via import-linter contracts (enforced? CI not confirmed).

**Pyramid:** Wide unit base, thin integration/e2e — acceptable *shape*, but:
- **No broker-SDK contract tests found** proving each broker satisfies `MarketDataGateway`/`CommonBrokerGateway` (the highest-value tests for an SDK). *Gap P1.*
- **Limited recovery/replay integration tests** for the event bus + DLQ. *Gap P2.*
- **Few failover/e2e tests** for multi-broker routing. *Gap P2.*
- Agent E's claim of "35 high-priority tests validated" was vague and **not reproducible** — treat as unverified.

**Recommendation:** Add (a) contract-test suite asserting every registered broker implements the gateway Protocols; (b) event-replay/recovery integration tests; (c) keep import-linter in CI as a hard gate (currently several ignores mask debt).

---

## 15. Performance Assessment

- `MultiBucketRateLimiter` (token-bucket, thread-safe, burst-aware), `RetryExecutor`/`CircuitBreaker` with backoff — sound.
- EventBus uses `threading.Lock` for subscribers, `RLock` for DLQ, singleton locks for repositories — lock-safe.
- `FeaturePipeline` (281 edges) and `RSI`/indicators (202) are pandas/DataFrame-bound; vectorize, avoid per-row Python loops (verify in `analytics`).
- No evidence of blocking I/O on the event thread; `AsyncEventBus` + worker thread present.
- **Risk:** 27 modules importing the *same* concrete `EventBus` singleton can create lock contention on the subscriber map under high publish rates — benchmark before Trading OS scale.

---

## 16. Security Assessment

- `infrastructure/security` + centralized logging with token redaction (per `.qoder`/`.trae` knowledge base) — good intent.
- `brokers.common.auth` encapsulates token lifecycle (not leaked).
- **Concern:** `plugins/dhan` was flagged by Agent E as "exposing sensitive gateway credentials" — **unverified**; audit `cli/services/broker_registry.py:64` credential checks and `.env.local` handling. Confirm no secret in `resolve_env_path`/logs.
- **Concern:** `persistent_dead_letter_queue.py` persists event payloads — ensure redaction covers persisted events, not just logs.

---

## 17. Scalability Assessment

- Per-broker gateways + rate limiters + circuit breakers scale per-connection.
- EventBus as a single global hub (494 edges) is a **scalability and blast-radius risk**: one misbehaving handler can stall subscribers (though errors are isolated per-handler per graphify tests). For Trading-OS scale, consider contextual buses or partitioned topics.
- `MultiBucketRateLimiter` per category (orders/quotes/data) is the right shape.

---

## 18. Production Readiness

| Dimension | Status |
|-----------|--------|
| Reliability | Good (retries, circuit breakers, DLQ, replay) |
| Recoverability | Good (event_log + DLQ + replay) |
| Observability | Good (metrics, tracing, alerting engine) |
| Security | Adequate, audit secrets-in-DLQ (§16) |
| Concurrency | Good (lock-safe bus/stores) |
| Maintainability | At risk (V1/V2/V4 coupling) |
| Extensibility/Plugin | At risk (V3 hand-coded registration) |
| **Overall** | **Not yet production-ready as a standalone SDK; ready as an application with known debt** |

---

## 19. Trading OS Readiness

The Trading OS should depend *entirely* on the Broker SDK without architectural change. Today:
- **Blockers:** V1 (app reaches infra), V2 (domain port inverted), V4 (SDK depends on CLI), V3 (no plugin discovery).
- **Enablers already present:** `MarketDataGateway` ABC, `CommonBrokerGateway`/`BrokerStreamHandle` Protocols, `BrokerCapabilities`, extension modules, thread-safe event bus + replay.
- **Conclusion:** After P0–P2 remediation, the SDK *can* support a Trading OS. The application layer should be re-expressed as a Trading OS that depends only on `brokers.common` public ports + `domain` — no `infrastructure` imports. This is achievable without a rewrite.

---

## 20. Prioritized Improvement Plan

| Pri | Item | Action | Effort |
|-----|------|--------|--------|
| **P0** | V1 App→infra | Extract ports (`EventBusPort`, `OrderRepository`, `LifecyclePort`, `MetricsPort`) in `domain`/`brokers.common`; move 10 modules behind adapters; delete the 10 `ignore_imports` | L |
| **P0** | V2 Domain port inversion | Remove `from infrastructure.event_bus import EventBus` re-export in `event_publisher.py`; make `EventPublisher` the only dependency; inject concrete at composition root | M |
| **P1** | V3 Broker discovery | Enable `tradex.brokers` entry points; `broker_registry` loads via `importlib.metadata`; implement `plugins/*` as real entry-point modules | M |
| **P1** | V4 SDK independence | Move `bootstrap`/`broker_registry` wiring into `brokers/runtime`; remove `brokers.common.bootstrap→cli` edge | M |
| **P2** | V5 Composition leak | `composer` depends only on `BrokerGateway`/`CommonBrokerGateway`; delete `brokers.common.{router,stream_orchestrator,provenance,historical_coordinator,infrastructure}` imports | M |
| **P2** | D1 `OmsOrderCommand` | Relocate to `application` as command/event | S |
| **P2** | Contract tests | Per-broker gateway Protocol conformance suite | M |
| **P3** | D2 `TradingContext` | Split into Session/Risk/MarketData contexts | M |
| **P3** | CLI god-object | Decompose `broker_service` into lifecycle/oms-proxy/capital services; break `cli/services` chain | M |
| **P3** | `market_data/` | Populate or delete | S |
| **P3** | EventBus scale | Evaluate contextual/partitioned buses for Trading-OS scale | L |

---

## 21. Implementation Roadmap

### Phase 0 — Stabilize layering (P0, ~2–3 wks)
**Objectives:** Stop upward leaks.
**Deliverables:** `EventPublisher`/`OrderRepository`/`LifecyclePort`/`MetricsPort` ports; 10 `application` modules rewired; `event_publisher.py` no longer imports infra; import-linter `ignore_imports` for `application-infrastructure-separation` reduced to ~0 and enforced in CI.
**Acceptance:** `import-linter` contract `application-infrastructure-separation` passes with no ignores; zero `application`→`infrastructure` production imports; zero `domain.ports`→`infrastructure`.
**Quality gate:** contract + unit tests green; architecture test hard-fails on regression.
**Exit:** V1, V2 closed.

### Phase 1 — Make the SDK independently reusable (P1, ~2–3 wks)
**Objectives:** OCP registration; SDK free of CLI.
**Deliverables:** `tradex.brokers` entry-point discovery; `plugins/dhan|upstox|paper` real modules; `brokers/runtime` composition root; delete `brokers.common.bootstrap→cli` edge.
**Acceptance:** Adding a broker requires **zero edits** to existing files (only a new `plugins/<name>` + pyproject entry point). `brokers.common` has no `cli`/`application` imports.
**Quality gate:** broker contract-test suite (Phase 2) passes for dhan/upstox/paper via discovery.
**Exit:** V3, V4 closed.

### Phase 2 — Compose correctly & prove conformance (P2, ~2 wks)
**Objectives:** `composer` on public ports; broker contract tests.
**Deliverables:** `composer` depends only on `BrokerGateway`; `OmsOrderCommand` moved; contract-test suite asserting every registered broker implements `MarketDataGateway`/`CommonBrokerGateway`/`BrokerStreamHandle`.
**Acceptance:** No `brokers.common.{router,stream_orchestrator,provenance,historical_coordinator,infrastructure}` imports outside the SDK; contract suite green for all brokers.
**Exit:** V5, D1, contract-test gap closed.

### Phase 3 — Harden for Trading OS (P3, ~3–4 wks)
**Objectives:** Decompose god objects; scalability/observability for OS scale.
**Deliverables:** `TradingContext` split; `cli/services/broker_service` decomposed; `market_data/` resolved; EventBus scalability review (contextual/partitioned buses); recovery/replay + failover e2e tests.
**Acceptance:** No >250-edge god node in `cli`/`application`; e2e failover + replay tests green; load test at Trading-OS target.
**Exit:** V-remaining, D2, Trading-OS-ready.

**Architecture Review after Phase 3:** re-run graphify; expect `EventBus` edge count to drop sharply (consumers depend on `EventPublisher`), `broker_service`/`TradingContext` no longer god nodes, and a clean community structure with `brokers.common` as an independent, discoverable SDK.

---

### Appendix — Verification notes
- All "verified" claims were confirmed by grep/file reads on the working tree (branch `agent/p0-smart-gateway-contract`, post-`graphify update`).
- Agent C's claim of `application/oms/protocols.py → brokers/dhan/reconciliation` was **not reproducible** (no such import exists); disregarded.
- Agent E's "35 high-priority tests validated" was **vague/unverified**; disregarded.
- Two automated review-agent runs for the Broker SDK scope returned empty/planning stubs; that section was investigated first-hand instead.
