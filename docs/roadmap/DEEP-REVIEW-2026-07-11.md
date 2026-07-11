# Deep Review — Trade_XV2 → Trading OS
**Date:** 2026-07-11 · **Baseline:** `8f825b5d` (`refactor/structural-cleanup`)
**Method:** 6 parallel codebase-exploration agents (brokers, domain, application/OMS, infrastructure/runtime, analytics/datalake, interface/tests/CI) + direct source verification of 9 load-bearing claims + cross-reference against the existing program of record (`docs/reviews/2026-07-11-trading-os-transformation-program/`) and the two prior reviews (2026-07-10, 2026-07-11-architecture-audit).

> **How to read this review.** The existing transformation program is strong and is treated as the source of truth. This review (a) *validates* what the program got right against the real code, (b) *reconciles* drift between the program's assumptions and current reality, and (c) *surfaces gaps the program under-addresses*. Findings are tagged with a `DR-` id; where a finding maps to an existing `TRANS-*`/`AUDIT-*` item it is noted, otherwise it is **NEW** and should be absorbed into the backlog.

---

## 1. System at a glance (verified)

| Dimension | Finding |
|---|---|
| Size | ~149.5k LOC `src/` (brokers 40k · interface 23.6k · domain 21.7k · analytics 17k · infrastructure 17.6k · application 15.1k · datalake 9.4k). Tests: **738 files / 127.8k LOC**. |
| Layering | Clean Architecture present: `domain → application → infrastructure`, plus `brokers`, `interface{api,ui,agent}`, `analytics`, `datalake`, `config`, `runtime` (composition root). |
| Architecture contracts | **import-linter 15/15 pass** (verified exit 0 on 2026-07-11). `tests/architecture/` = 43 files. |
| Eventing | Real synchronous `EventBus` + `AsyncEventBus` (bounded queue, DLQ, fsync on capital events `ORDER_*/TRADE_*/POSITION_*`). |
| Brokers | dhan (18.6k/90) + upstox (13.9k/129) = 87% of broker code. paper = synthetic reference (1.6k/9). |
| ADRs | 012 (CQRS) · 013 (brokers) · 014 (brokers-TOS / persistence) · 015 (execution ledger) · 016 (market-data eventbus) · 017 (composition root) · 018 (certification tiers) · 019 (CI gates). |
| Tests/CI | Pyramid unit 401 / component 97 / integration 151 / e2e 33 / architecture 43 / chaos 12. Coverage `fail_under=80` + per-module gates. Mutation `fail_under=90` configured but **advisory**. |
| Dev tooling | `broker doctor/verify/certify`, `tradex` CLI, MCP server, TUI doctor, load-test runner, notebooks, golden datasets. Mature *relative to most repos*. |

---

## 2. What the existing program got right (validation)

These program claims are **confirmed by the code**, not just aspirational:

1. **Clean dependency direction is enforced and real.** Zero `from brokers` in `src/domain/`; infrastructure does not leak upward. The `MarketSurface` + `BrokerCapabilities` routing model exists and is the intended single source of market-coverage truth.
2. **The broker kernel landed.** `BrokerTransport` (domain port), `ReconnectingTransport`, wire adapters (`DhanWireAdapter`, `UpstoxWireAdapter`, `PaperGateway`), and `MarketSurface`/`BrokerCapabilities` are present (commit `8f825b5d`) — the strangler-fig kernel plan from the `.kilo` audit is in motion.
3. **Explicit order/position state machines exist.** `domain/state_machine.py` + `OrderStateValidator` (per-order `TTLCache`) + `PositionManager` `StateMachine[PositionState]`. Not ad-hoc strings.
4. **Execution ledger + mode ports are real.** `OrderTransportPort`, `ExecutionLedgerPort`, `OrderStorePort`, `RiskManagerPort` exist; OMS reaches brokers only via `OrderTransportPort`.
5. **Production-grade analytics core.** `ReplayEngine` (ring buffer, intra-bar stops, event interleave), parity `BacktestEngine`, `PaperTradingEngine`, fail-closed `FeaturePipeline`, `DataQualityEngine`, DuckDB lake + materialized views, JSON→DuckDB `RuleEngine`.
6. **Mature derivatives domain.** `Greeks`, `GreeksSurface`/`IVSurface`, `OptionChain` (atm/pcr/max_pain/itm/otm), `FutureChain`, pure Black-Scholes in `derivatives_math.py`. No stubs/TODOs.
7. **Developer platform + cert tiers.** `BrokerCertifier` (drives paper/dhan/upstox via identical `BrokerSession`), cert schema **v2** (ADR-018), platform-ops unity tests.

**Conclusion:** the program's foundation phases (P0–P3) are *substantially executed and verified*. The risk is now in **completion and truthfulness**, not in direction.

---

## 3. Evidence-based findings register

Severity: 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Positive/Informational.

### A. Broker-agnosticism leaks (the headline risk)

| ID | Severity | Finding | Evidence | Program mapping |
|----|----------|---------|----------|-----------------|
| **DR-B1** | 🔴 | `ExtendedOrderService` introspects gateway internals (`getattr(gw,"_broker")`, `"_conn"`) and branches on broker **name strings** (`"dhan"`/`"upstox"`) for super/forever/trigger/gtt/cover/slice/exit-all. This is core→broker coupling in the OMS; adding a broker requires editing core. | `application/oms/extended_order_service.py:130–300` | **NEW** (under-addressed by P5 plugins/ADR-014) |
| **DR-B2** | 🟠 | Certification suite encodes broker identity: `if s.broker_id == "paper": raise NotImplementedError()` in 5+ checks (token refresh/expiry/reconnect/disconnect/recovery). *Nuance (review-again):* for genuinely live-only checks, raising is partially expected — the fix is a **capability-gated skip**, not broker-name branching. | `brokers/certification/suite.py:120,130,139,326,332` | **NEW** (ADR-018 defines tiers but still hardcodes identity) |
| **DR-B3** | 🟠 | Resilience layer names concrete brokers: `importlib.import_module("brokers.dhan.config.capabilities" / "brokers.upstox.capabilities")`. | `infrastructure/resilience/rate_limiter.py:332,335` | **NEW** (violates "infrastructure independence" contract) |
| **DR-B4** | 🟠 | `interface/ui/services/*` imports `brokers.dhan.identity.account_registry`, `brokers.dhan.wire.DhanBrokerGateway`, `brokers.upstox.mappers.domain_mapper`, `brokers.paper.PaperGateway` directly — bypassing the `interface.ui` import-linter contract (which exists but isn't catching it). | `interface/ui/services/broker_facade.py`, `oms_bootstrap.py:189`, `broker_registry.py`, `broker_manager.py` | **NEW** |
| **DR-B5** | 🟡 | Two competing "unified port" abstractions: `BrokerAdapter` (Protocol) and `BrokerTransport` (ABC) overlap with no clear owner. | `domain/ports/broker_adapter.py:45`, `domain/ports/broker_transport.py:26` | Revisit ADR-013/014 |
| **DR-B6** | 🟠 | **Protocol/signature divergence (two surfaces — *corrected in review-again*).** The canonical `DataProvider.get_quote(InstrumentId)` / `ExecutionProvider.place_order(OrderRequest)` ports are **implemented by the broker adapters** (`DhanDataAdapter`/`DhanDataProvider`) and **used by the domain** (`Instrument.get_quote`, `QuoteService`, `broker_transport`) — so they are **not dead**. The lower-level *wire adapters* (`DhanWireAdapter`/`UpstoxWireAdapter`) instead expose `(symbol, exchange)` string methods (`wire.py:48,127`), and some call sites (`BrokerSession`, quote pull-through `Instrument.refresh`) invoke those string methods directly, bypassing the port. Because the ports are `runtime_checkable` (name-only), the `InstrumentId`/`OrderRequest` contract is **not enforced at the wire boundary**. | `domain/ports/protocols.py:90` vs `brokers/dhan/wire.py:48`, `brokers/upstox/wire.py:127`; domain callers `instruments/instrument.py:488`, `services/quote.py:41` | **NEW** (relates to P2 contract freeze) |
| **DR-B7** | 🟡 | Fragmented plugin registration: 5 parallel registries (`register_broker_plugin`, `_data_adapter`, `_execution_provider`, `_broker_extensions`, `_segment_mapper`) with no single `BrokerPluginInterface` enforcing completeness for a new broker. | `brokers/{dhan,upstox,paper}/__init__.py` | **NEW** |
| **DR-B8** | 🟡 | `ensure_core_plugins()` duplicates broker metadata already declared in entry points (drift-prone). | `infrastructure/broker_plugin.py:69–108` | **NEW** |

### B. Domain-model type-safety gaps

| ID | Severity | Finding | Evidence | Mapping |
|----|----------|---------|----------|---------|
| **DR-D1** | 🟠 | `Money` VO is **defined but unused** — every money field is raw `Decimal` (`Order.price`, `Position.avg_price`, `Trade.trade_value`, `Balance.*`). No `Quantity` VO (raw `int`). Currency/time safety absent. | `domain/value_objects/money.py` (only referenced in its own module + `__init__` + 2 schema spots); grep confirms zero arithmetic use | **NEW** |
| **DR-D2** | 🟠 | **No `Clock` abstraction.** `datetime.now(timezone.utc)` is called *inside* VOs → impure, non-deterministic, hard to test. | `domain/value_objects/state.py:52,104,113,123` | **NEW** (note: `infrastructure/time_service.py` exists but VOs don't use it) |
| **DR-D3** | 🟡 | Two `OrderIntent` classes with the same name but different shapes/semantics (pre-risk desire vs durable persisted command). | `domain/orders/intent.py:25` vs `domain/execution_contracts.py:28` | **NEW** |
| **DR-D4** | 🟡 | `Instrument` name collision: 3 meanings (`domain.instruments.instrument.Instrument` rich object; `InstrumentRecord` aliased `Instrument` at `entities/instrument_record.py:48`; deprecated `aggregates/instrument.py`). | cited files | **NEW** |
| **DR-D5** | 🟡 | `domain/services/*` (`OrderService`, `QuoteService`, `HistoryService`, `StreamingService`, `AnalyticsService`) and ambient-session global wiring blur the domain/application boundary. | `domain/services/*`, `instrument.py:144 get_ambient_session` | **NEW** |
| **DR-D6** | 🟡 | `Portfolio` aggregate is **mutable & not thread-safe** (`_positions` dict), unlike `PositionAggregate`/`AccountAggregate` which use locks. | `domain/portfolio/portfolio.py:24` | **NEW** |
| **DR-D7** | 🟢 | Options/futures domain is mature and pure (see §2.6). No action beyond adding to the lake (DR-A4). | — | — |

### C. Execution / OMS

| ID | Severity | Finding | Evidence | Mapping |
|----|----------|---------|----------|---------|
| **DR-E1** | 🟠 | God-services: `OrderManager` (404 LOC — owns in-memory book + lock + idempotency + validation + lifecycle + publishing), `TradingOrchestrator` (807), **`RiskManager` (678 — `application/oms/_internal/risk_manager.py`; the `application/oms/risk_manager.py` is a 10-line re-export)**, `ExtendedOrderService` (453). | `application/oms/order_manager.py:111`, `application/trading/trading_orchestrator.py:107`, `application/oms/_internal/risk_manager.py`, `application/oms/extended_order_service.py:31` | part of P5 spine |
| **DR-E2** | 🟠 | **Mixed concurrency model.** RLock-based OMS/execution vs asyncio streaming; the bridge is ad-hoc (`composer/factory.py:_run_async` spins a *new* event loop; `loop.call_soon_threadsafe`). Risk: lock-model mismatch when stream events mutate the order book under RLock. | `composer/factory.py:62`, `streaming/orchestrator.py:337` | **NEW** (program's mode-unification omits concurrency) |
| **DR-E3** | 🟡 | Portfolio *mutation* lives in OMS `PositionManager`; `application/portfolio` is read-only and typed `Any`. Asymmetry. | `application/oms/position_manager.py:27`, `application/portfolio/portfolio_service.py:67` | **NEW** |
| **DR-E4** | 🟡 | Audit *side-channel* into `infrastructure.observability.audit` (`emit_*`) bypasses the existing `EventMetricsPort`/`TracerPort`. | `composer/router.py:140`, `streaming/orchestrator.py:370`, `data/historical_coordinator.py` | **NEW** |
| **DR-E5** | 🟡 | `oms/ledger_shadow.py:11` imports `runtime.ledger_policy` — couples OMS to the runtime layer (wrong direction). | cited | **NEW** |
| **DR-E6** | 🟢 | Explicit state machine + validator + per-order TTLCache + position state machine are real and correct (see §2.3). | — | — |

### D. Analytics / Datalake

| ID | Severity | Finding | Evidence | Mapping |
|----|----------|---------|----------|---------|
| **DR-A1** | 🟠 | **No uniform strategy/scanner plugin system in the default path.** The facade hardcodes a 4-scanner dict and `StrategyPipeline()` hardcodes `[Momentum, Breakout]`; `StrategyRegistry.discover()` is only used in multi-strategy runtime + API. Most CLI/API backtest paths bypass discovery. | `analytics/facade.py:103–111`, `analytics/strategy/pipeline.py:38,151` | extends P6 |
| **DR-A2** | 🟡 | Analytics internals import `datalake` directly (precompute_features, views/*, rules, halftrend_backtest) bypassing `MarketDataPort` → storage swap ripples. | 10 files grep-confirmed | **NEW** |
| **DR-A3** | 🟡 | **Golden-dataset CLI broken:** `GOLDEN_DIR = Path("data/golden")` but fixtures live in `tests/fixtures/golden` — save path writes elsewhere and is unusable, though fixture-based tests still pass. | `analytics/replay/golden_dataset.py:22` | P4 gap |
| **DR-A4** | 🟠 | `DataLakeGateway.option_chain`/`future_chain` `return []` (stubs), yet option-analytics SQL exists → **latent empty-data failures** for derivatives. The rich options domain (DR-D7) has no data backing. | `datalake/gateway.py:199,377` | **NEW** (relates to derivatives capability) |
| **DR-A5** | 🟡 | Dual parquet layouts coexist (legacy `symbol=` vs curated `year=/month=`); `migrate_legacy_to_curated` is a `NotImplementedError` stub. | `datalake/core/paths.py:196` | P5 migration |
| **DR-A6** | 🟠 | **Exchange-agnosticism is aspirational, not real.** Hardcoded `exchange="NSE"`, `risk_free_rate=0.065`, paisa/`Decimal`, slippage/commission models throughout. Adding a non-Indian market requires edits across layers. | multiple | **NEW** (contradicts program's "exchange-agnostic" claim) |
| **DR-A7** | 🟡 | `UnifiedReplayOrchestrator` is a stub: `_execute_replay` says "simplified version"; `_derive_expected_equity` ignores commissions/slippage. Rough drift check, not a guarantee. | `analytics/replay/orchestrator.py:247,564` | **NEW** |
| **DR-A8** | 🟢 | Small indicator set (no ADX, stochastic, native Bollinger indicator). Extend, don't block. | — | P6 |

### E. Infrastructure / Runtime

| ID | Severity | Finding | Evidence | Mapping |
|----|----------|---------|----------|---------|
| **DR-I1** | 🟠 | Resilience primitives defined in infra but **applied per-broker**; `brokers/dhan/resilience/retry_executor.py` *duplicates* infra `RetryExecutor`; not on EventBus/gateway/connection hot paths. | `brokers/dhan/resilience/retry_executor.py` | **NEW** |
| **DR-I2** | 🟡 | **Two idempotency mechanisms** overlap: EventBus in-memory dedup deque + `IdempotencyService` (redis/file/memory). | `event_bus.py:358`, `infrastructure/idempotency/service.py` | **NEW** |
| **DR-I3** | 🟠 | **Token encryption is optional.** If `SECRET_ENCRYPTION_KEY` unset, `SecretManager` only *warns* and tokens persist **unencrypted**; `EncryptedTokenStore` sniffs `gAAAAA`/`Zg==` (fragile). | `infrastructure/security/secret_manager.py:78–83,189` | security (P7) — elevate |
| **DR-I4** | 🟡 | EventBus/AsyncEventBus daemon threads are **not registered with `LifecycleManager`**, contradicting its "no thread without a lifecycle" rule. | `event_bus.py:217`, `async_event_bus.py:189` | **NEW** |
| **DR-I5** | 🟡 | Config split across two homes: `infrastructure/config` (broker settings) vs `config/profiles` (env profiles/schema/flags). No single source of truth. | cited | **NEW** |
| **DR-I6** | 🟠 | **Multiple composition roots** coexist (`runtime/trading_runtime_factory`, `interface/ui/services/compose.py`, `tradex/session.py`, `infrastructure/gateway/factory`); the `infrastructure/di.py` `Container` is effectively unused (only `clock` pre-registered). | cited; `di.py:263` | ADR-017 / P5 (Iter3 partial) |
| **DR-I7** | 🟡 | State is file-sprawl (`market_data/*.sqlite` + event logs) under a single-process `flock` invariant. No centralized/horizontally-scalable store; DuckDB is analytics-only despite pyproject listing it as a dependency for state. | `sqlite_order_store.py:110` | P7 scale |

### F. Interface / API / Web

| ID | Severity | Finding | Evidence | Mapping |
|----|----------|---------|----------|---------|
| **DR-F1** | 🟡 | **Dual API surface:** clean routers + a parallel `/live/` package (`live/extended.py` = 19 endpoints: webhook, market, orders, portfolio, derivatives…). Two API shapes to maintain. | `interface/api/routers/live/extended.py` | **NEW** |
| **DR-F2** | 🟠 | **No real `/ready` readiness gate** (TRANS-P4-005 pending) — only a `/health` *shape* exists; readiness is not enforced. | `interface/api/routers/health.py` | P4 (open) |
| **DR-F3** | 🟡 | Agent/MCP tool surface thin: 9 tools; no `doctor`/`diagnose`/`subscribe`/streaming; `platform_ops` unity exists but isn't surfaced via `interface.agent`. | `interface/agent/tools_schema.py` | P4 |
| **DR-F4** | 🟡 | **Web SPA is not in CI** — no frontend build/test/lint job; Playwright e2e is a stub. `web/README.md` says backend is source of truth. | `web/e2e/smoke.spec.ts` | **NEW** |
| **DR-F5** | 🟡 | No Web SDK / OpenAPI→TS codegen; `web/` is hand-typed fetch. | `web/src/types.ts` | **NEW** |

### G. Testing / CI drift

| ID | Severity | Finding | Evidence | Mapping |
|----|----------|---------|----------|---------|
| **DR-T1** | 🟡 | **TESTING-STRATEGY.md test-count table was partly inaccurate** (*corrected in review-again*). The doc counts `def test_` **functions** (not files), and most figures match reality (unit 4,179≈4,400, component 1,076≈1,067, e2e 320≈318, chaos 175=175). It was wrong on **Architecture (claimed 469, actual 222)** and **Integration (claimed ~1,600, actual 1,343)**. Minor doc-drift, fixed in-place. | `docs/.../TESTING-STRATEGY.md` vs measured `tests/` (7,331 functions / 745 files) | **NEW** |
| **DR-T2** | 🟠 | **Mutation testing is advisory + duplicated:** two redundant nightly workflows (`mutation_testing.yml` **and** `mutation_nightly.yml`, both `0 2 * * *`), `continue-on-error: true`, scoped to 3 dirs; never on the PR gate despite `fail_under=90`. | `.github/workflows/mutation_*.yml` | AUDIT-006 area / P3 |
| **DR-T3** | 🟠 | **CI is "partially truthful":** 4 `continue-on-error` safety steps remain (AUDIT-006 open); mypy/safety are warn-only until P7. Green ≠ live-safe. | `ci.yml` | P3 (open) |
| **DR-T4** | 🟡 | Pytest **collection errors (12+) flagged but not zeroed** (TRANS-P3-001 area). | `pytest` collection | P3 |

---

## 4. Reconciliation with the program of record

**Progress since the 2026-07-10 review (resolved concerns):**
- import-linter **15/15** and `tests/architecture` 43 files → dependency direction is now *enforced* (was a top concern).
- Broker kernel (`BrokerTransport`/wire adapters/`MarketSurface`) **landed** → strangler-fig plan is no longer just a doc.
- Certification **tiers v2 schema** (ADR-018) in place.

**Correction to a prior claim:** the 2026-07-11 architecture-audit's A-tier risk #4 ("domain imports concrete brokers", `segment_mapper.py:22-31`) is **no longer true** — I found zero `from brokers` in `src/domain/` and import-linter is 15/15. This concern should be closed.

**Still-open A-tier risks (persist):**
1. *Fragmented composition roots* — **partially** addressed by `runtime.factory.build` (Iter 3) but **DR-I6** shows multiple roots remain and DI is unused.
2. *No unified Upstox market-data→EventBus publish* — **partially re-checked (review-again):** `event_bus` is wired into `UpstoxBroker` (`brokers/upstox/broker.py:110`), but no clear `publish` call was found in the market-data websocket path (`websocket/market_data_v3.py`). Treat as **open** until confirmed by a golden-bus test (`TRANS-P5-010`).
3. *CI/certification path drift (AUDIT-006)* — **partially** repaired; **DR-T2/DR-T3** show it is still not truthful.
4. *Silent failure semantics* — **DR-E4 / datalake soft-fail / `event_bus=None` no-ops** still present; "fail-closed" is not yet the default everywhere.

**Net verdict:** The 2026-07-10 program verdict — *"not yet safe to enable unattended live trading with material capital"* — **still holds** for that specific use case, but the *engineering foundation* to get there is now real and enforced. The remaining work is **completion, truthfulness, and the production-safety gaps** (broker-name branching, optional token encryption, CI truth, execution-spine unification), not a change of architecture.

---

## 5. Gaps the program under-addresses (must be absorbed into backlog)

Items the existing `TRANS-*` backlog does **not** explicitly cover, ordered by leverage:

| Rank | Finding | Why it matters | Suggested task id |
|---|---|---|---|
| 1 | **DR-B1** broker-name branching in OMS | Directly defeats the program's #1 success criterion ("add a broker = plugin + cert, zero OMS edits") | `TRANS-P5-B1` |
| 2 | **DR-I3** optional token encryption | Security/compliance blocker for real-money; silent unencrypted token files | `TRANS-P7-I3` |
| 3 | **DR-T2 / DR-T3** CI not truthful | "CI green = real" is a program success criterion; currently false | `TRANS-P3-T2` |
| 4 | **DR-I6** multiple composition roots + unused DI | Blocks single-spine unification (program M5) | `TRANS-P5-I6` |
| 5 | **DR-D1 / DR-D2** Money/Clock VOs absent | Type-safety and determinism goals unmet; tests fragile | `TRANS-P1-D12` |
| 6 | **DR-E2** mixed thread/asyncio | Correctness risk on order-book mutation from stream events | `TRANS-P5-E2` |
| 7 | **DR-A6** hardcoded NSE/Indian-market | "Exchange-agnostic" is a headline property; currently false | `TRANS-P5-A6` |
| 8 | **DR-A4** option/future lake stubs | Rich derivatives domain has no data backing → empty-result failures | `TRANS-P6-A4` |
| 9 | **DR-B2 / DR-B3 / DR-B4** identity leaks in cert/rate-limiter/UI | Each re-introduces broker coupling the kernel was meant to remove | `TRANS-P5-B2` |
| 10 | **DR-F2 / DR-F4 / DR-F5** `/ready`, web-in-CI, TS SDK | Developer-platform + operational-readiness gaps | `TRANS-P4-F2` |

All other findings (DR-B5/6/7/8, DR-D3/4/5/6, DR-E3/4/5, DR-A1/2/3/5/7, DR-I1/2/4/5/7, DR-F1/3, DR-T1/4) map onto existing `TRANS-*` lanes (P1 ubiquitous-language, P2 contracts, P4 dev-platform, P5 core-refactor, P6 features, P7 hardening) and should be appended there rather than given new ids.

---

## 6. Immediate actions (next 1–2 weeks, the "truthful baseline" sprint)

1. **DR-T2/DR-T3** — Make CI truthful: collapse the two mutation workflows into one blocking-on-PR (or explicitly non-blocking + documented), remove the 4 `continue-on-error` safety steps, flip mypy to error on the `application/oms` + `domain` paths first. *Owner: Integration/Release.*
2. **DR-B1** — Introduce a `BrokerExtension` capability for super/forever/trigger/gtt/cover/slice/exit-all resolved via `ExtensionRegistry`; deprecate `_get_broker`/`_get_conn` with a removal deadline. *Owner: OMS/Execution + Broker Platform.*
3. **DR-I3** — Make `SECRET_ENCRYPTION_KEY` mandatory in prod profiles; fail-closed if unset for live brokers. *Owner: Runtime/Platform + Security.*
4. **DR-I6** — Freeze composition roots: route all wiring through `runtime.factory.build`; add an architecture test forbidding `import` of concrete brokers from `interface/ui` and `tradex/session`. *Owner: Runtime/Platform.*
5. **DR-D1/DR-D2** — Promote `Money`/`Quantity`/`Clock` VOs; stop calling `datetime.now()` inside VOs (inject `TimeService`). *Owner: Domain & Contracts.*
6. **DR-T1** — Correct `TESTING-STRATEGY.md` to actual counts; add a CI check that fails on collection errors. *Owner: Integration/Release.*

> These six move the system from "foundation in place" to "foundation *trustworthy*," which is the prerequisite the program itself names for starting P5 production refactoring.

---

## 7. Review-again corrections (2026-07-11, second pass)

A second verification pass (direct `grep`/`Read`, not agent summaries) corrected two assertions and refined two others. All other `DR-*` findings were re-confirmed.

| # | Finding | Correction |
|---|---------|-----------|
| 1 | **DR-B6** (port/signature divergence) | **Overstated in first pass.** The `InstrumentId`/`OrderRequest` ports are **not dead**: the domain uses `get_quote(InstrumentId)` via `Instrument` (`instruments/instrument.py:488`) and `QuoteService` (`services/quote.py:41`), and broker **adapters** (`DhanDataAdapter`) implement the ports. The real, narrower issue: lower-level *wire adapters* expose `(symbol, exchange)` string methods and a few call sites use them directly, bypassing the port; `runtime_checkable` (name-only) doesn't enforce the contract at the wire boundary. Fix reframed in `TRANS-P2-005` (enforce boundary via adapter + integration test, not "make wire adapters implement ports"). |
| 2 | **DR-E1** (god-services) | The 678-LOC `RiskManager` is at `application/oms/_internal/risk_manager.py`; `application/oms/risk_manager.py` is a 10-line re-export. Path corrected. Counts (`OrderManager` 404, `TradingOrchestrator` 807, `ExtendedOrderService` 453) re-confirmed. |
| 3 | **DR-B2** (cert identity) | Added nuance: raising `NotImplementedError` for genuinely live-only checks is partially expected; the fix is a capability-gated *skip*, not broker-name branching. Severity unchanged (🟠). |
| 4 | **Upstox unified-bus** (A-tier risk, prior audit) | **Partially re-checked:** `event_bus` is wired into `UpstoxBroker` (`brokers/upstox/broker.py:110`) but no clear `publish` call found in the market-data websocket path (`websocket/market_data_v3.py`). Remains **open** pending a golden-bus test (`TRANS-P5-010`). |

**Re-confirmed as-is (verified this pass):** DR-B1 (OMS broker-name branching), DR-B4 (`interface/ui` concrete-broker imports — extensive, `broker_facade.py:18-25` + `oms_bootstrap.py:192` + `broker_registry.py`), DR-I1 (parallel `brokers/dhan/resilience/` duplicates infra `RetryExecutor`/`CircuitBreaker`/`ExponentialBackoff`), DR-A1 (facade/`StrategyPipeline` hardcode `[Momentum, Breakout]`), DR-T2 (two `mutation_*` workflows), DR-F1 (`/live/` = 50 router decorators vs 16 clean routers), DR-A5 (`migrate_legacy_to_curated` → `NotImplementedError`).

**Corrected in this pass (was listed as re-confirmed above):** **DR-T1** — the doc's counts are *function* counts and mostly accurate; only Architecture (469→222) and Integration (~1,600→1,343) were wrong. The doc was fixed in-place; DR-T1 downgraded 🟠→🟡.

---

## 8. Code-verification addendum (2026-07-11, post multi-agent wave)

> **Live status lives in** [`EXECUTION-ROADMAP-2026-07-11.md` §9](./EXECUTION-ROADMAP-2026-07-11.md#9-code-verified-status-2026-07-11).  
> This section records how subsequent implementation changed the original `DR-*` findings.

| Original finding | Code-verified status | Notes |
|---|---|---|
| DR-B1 OMS name branching | ✅ **Fixed** | `OrderCapabilityPort`; arch tests pass; one component test still expects old type |
| DR-B2/B3 cert + rate-limiter | ✅ **Fixed** | Capability/plugin dispatch |
| DR-B4 UI concrete brokers | ⚠️ **Partial** | Funnel via allowlisted `broker_registry`; imports still present |
| DR-T2 dual mutation workflows | ✅ **Fixed** | Single `mutation_nightly.yml` |
| DR-T3 untruthful CI | ⚠️ **Partial** | Clean-subset mypy error-mode; residual advisory `continue-on-error` |
| DR-T4 collection errors | ✅ **Fixed** | Collection gate; 0 collect errors on major layers |
| DR-F2 no `/ready` | ✅ **Fixed** | Real readiness evaluator |
| DR-F3 thin agent surface | ✅ **Fixed** | 12 tools |
| DR-F4/F5 web/SDK | ✅ **Fixed** | `web.yml` + generated TS SDK |
| DR-E3 portfolio `Any` | ✅ **Fixed** | `PortfolioContext` |
| DR-I1 dual RetryExecutor | ⚠️ **Partial** | Canonical infra executor; Dhan shim remains |
| DR-I2 dual idempotency | ✅ **Fixed** | EventBus → `IdempotencyService` |
| DR-I3 optional encryption | 🟡 **Still open** | Optional; plaintext when key unset; `gAAAAA` sniff remains |
| DR-I6 multi composition roots | ⚠️ **Partial** | `factory.build` spine; not sole root |
| DR-D1/D2 Money/Clock | ⚠️ **Partial** | VOs exist; not used on Order; impure state VOs |
| DR-A6 hardcoded NSE | ⚠️ **Partial** | `MarketSurface` exists; NSE defaults remain |
| DR-E2 mixed concurrency | ⚠️ **Partial** | `runtime/event_loop.py`; ad-hoc loops remain |
| DR-A4 lake stubs | 🟡 **Still open** | Still empty option/future chains |
| DR-A1 plugins | 🟡 **Still open** | Hardcoded defaults |
| import-linter 15/15 claim | ❌ **Stale** | Now **14/15** (`order_lifecycle` → `runtime.ledger_policy`) |

Original §1–§7 remain historical evidence for the *pre-wave* baseline. Do not re-open fixed rows without re-verifying source.
