# TradeXV2 — Module Program (Deep, Non-Cosmetic)

**Status:** Binding companion to [`TARGET_SYSTEM_DESIGN.md`](./TARGET_SYSTEM_DESIGN.md)  
**Reality override:** [`CODE_REALITY_AND_PLAN.md`](./CODE_REALITY_AND_PLAN.md) — verified from **source files** (2026-07-10). Where this file’s assumptions disagree with CODE_REALITY, **CODE_REALITY wins**.  
**Delivery:** Incremental **git commits** (same rules as design doc)  
**Rule:** A module is **not done** until its **exit criteria + contract tests** pass. Renames, comment cleanups, re-exports, or “looks cleaner” refactors **do not count**.

---

## 0. Anti-cosmetic standard

### 0.1 What “same level of accuracy” means

For **every** module below, work must specify and deliver:

| Dimension | Required content |
|-----------|------------------|
| **Purpose** | Why the module exists in the platform goal |
| **Owns** | Types/state/files it is sole owner of |
| **Must not own** | Forbidden responsibilities (layer leaks) |
| **Inbound / outbound** | Who calls it; what it calls (ports only where required) |
| **Public contract** | Methods/events/schemas that are stable |
| **Invariants** | Rules that tests enforce forever |
| **Defects (code-grounded)** | Real failures today — not style |
| **Target behavior** | Correct end state, not “refactored” |
| **Tests (mandatory)** | Unit + contract/integration as listed |
| **Commit IDs** | Named slices; red→green allowed |
| **Done when** | Measurable exit — binary |

### 0.2 Cosmetic work (explicitly forbidden as a “module done”)

- Renaming packages without behavior change  
- Moving files without wiring dead code  
- Adding docs/comments only  
- Re-export shims without deleting the dual  
- Increasing coverage by testing trivial getters  
- “Aligning” types that still diverge at runtime  
- Logging/metrics pretty-print without changing fail/success paths  

Cosmetic commits may exist **only as follow-ups after** behavioral exit is green, and must be labeled `chore:` not `phaseN/`.

### 0.3 Depth bar (applies to all modules)

A module fix is deep enough only if:

1. **Happy path works** with real collaborators or faithful fakes  
2. **Failure path is defined** (reject, retry, gate, error type)  
3. **Restart / reconnect story** exists if the module holds state or money/data integrity  
4. **Cross-module contract** is asserted (not “assumed via import”)  
5. **Old dual path** is deleted or hard-redirected in the same commit stream  

---

## 1. Platform goals ↔ module ownership

| Goal | Primary modules | Supporting |
|------|-----------------|------------|
| G1 One money path | `application.execution`, `application.oms`, `cli/services`, `api/routers/orders` | `tradex.session` |
| G2 Correct books | `application.oms`, `infrastructure.persistence`, trade ledger, recon | `brokers.*.reconciliation` |
| G3 Risk works | `application.oms` risk, `domain.risk`, capital/margin ports | broker margin adapters |
| G4 Broker parity | `brokers.dhan/upstox/paper`, `brokers.common` | domain ports |
| G5 Mode parity | `application.execution` FillModels, paper, backtest adapters | `analytics.replay` (costs only) |
| G6 Scanner→order | `analytics.scanner`, `analytics.strategy`, `application.trading` | event bus |
| G7 Test gates | `tests/contract`, `tests/chaos`, CI | package tests |
| G8 Market data truth | broker WS, `application.streaming`, `datalake` | tick validation |
| G9 Research integrity | `analytics.replay`, `walk_forward`, `datalake.quality` | trading_costs |
| G10 Operable single-node | `infrastructure.lifecycle`, health, composition roots | `runtime/*`, `cli` doctor |

Goals G8–G10 are first-class; they are **not** optional polish.

---

## 2. Dependency law (all modules)

```text
presentation (api, cli)
    → application (use cases, oms, trading, streaming, composer)
        → domain (entities, ports, pure policy)
            ← adapters implement ports (brokers, persistence, lake data provider)
infrastructure provides technical services; application does not import broker concretes
analytics may publish candidates/signals; must NOT place orders
tradex is public SDK façade over composition — not a second OMS
```

**Violation = failed architecture test**, not a warning.

---

## 3. Module catalog

For each module: **Depth sheet**. Commit prefixes: `phase0|1|2|3 / <module> / <slice>`.

---

### M01 — `domain` (src/domain)

| Field | Content |
|-------|---------|
| **Purpose** | Pure trading language: identities, orders, positions, ports, state machines, costs, event shapes |
| **Owns** | `entities/*`, `instruments/*`, `ports/*`, `events/types`, `state_machine`, `trading_costs`, `risk` **policy/math only** |
| **Must not own** | SQLite, HTTP, broker SDKs, thread buses, composition |
| **Contract** | Stable types: `Order`, `Trade`, `Position`, `InstrumentId`, `OrderStatus` transitions; ports as Protocols |
| **Invariants** | No import of `brokers`, `application`, `infrastructure`, `api`, `cli`; Position PnL uses multiplier; notional calculator pure |
| **Defects today** | Orphan `domain.risk.policy` unused by OMS; dual indicators vs analytics; shallow-frozen events; oversized `capability_manifest`, `universe`, `instrument.py`; ports proliferation without enforcement |
| **Target** | One risk **policy** module used by app RiskEngine; ports reduced to minimal stable set (§ design); entities complete for F&O (multiplier, lot); costs single source for sim |
| **Tests** | Import-linter domain independence; property tests order transitions; unit PnL/multiplier; port runtime_checkable smoke for fakes |
| **Commits** | `C-M01.1` notional+multiplier pure functions; `C-M01.2` risk policy single module wired by app; `C-M01.3` prune/mark deprecated dead ports; `C-M01.4` event payload codecs registry for Order/Trade |
| **Done when** | App risk imports domain policy math; F&O PnL unit tests green; domain import-linter 0 violations; no broker import in domain prod code |

---

### M02 — `application.oms`

| Field | Content |
|-------|---------|
| **Purpose** | Sole owner of working order book, position book, pre-trade risk engine, recon gate, recovery |
| **Owns** | `OrderManager`, `PositionManager`, `RiskEngine`, `TradingContext`, trade recorder, idempotency, placement gate |
| **Must not own** | Broker HTTP/WS; scanner logic; duckdb |
| **Contract** | place/modify/cancel/on_trade/on_order_update; risk check; recover(); health snapshot |
| **Invariants** | correlation_id required; TRADE→apply→mark ledger; all status via state machine; store upsert on mutation; daily PnL fed from portfolio |
| **Defects today** | OrderStore assigned never used; mark-before-apply; daily PnL unwired; MARKET notional hole; phantom capital; cancel skips SM; extended orders bypass risk; overfill accepted |
| **Target** | Full G1–G3; recover() cold-start; extended path through risk |
| **Tests** | Existing OMS suite **plus** cold-start multi-process; daily loss after fill; MARKET reject; extended risk; apply-then-mark crash test |
| **Commits** | Align design **C0.1–C0.5**, **C1.2**, **C1.4** — these are **behavioral**, not cosmetic |
| **Done when** | Kill -9 → restart books match; risk trips; no second book |

---

### M03 — `application.execution`

| Field | Content |
|-------|---------|
| **Purpose** | Use cases + FillModel selection (live / paper / backtest); only path to OMS for strategies |
| **Owns** | `PlaceOrderUseCase`, `ModifyOrderUseCase`, `CancelOrderUseCase`, `ExecutionService`, fill adapters |
| **Must not own** | Risk formulas; broker mapping |
| **Contract** | `execute(command) -> OrderResult`; modes only change fill adapter |
| **Invariants** | Always OMS; live never uses SimulatedFill; backtest cancel/modify real against OMS |
| **Defects today** | **`PlaceOrderUseCase` is orphan** (only re-exported from `application/execution/__init__.py`; api/cli/orchestrator do not call it). Parallel: `ExecutionService`, `composer/execution.py`, CLI `order_manager.place_order`, API `tradex.connect`. Mode adapters exist under `execution_mode_adapter.py` / `oms_backtest_adapter.py` |
| **Target** | One use-case / OrderServicePort spine; all presentation paths redirect; FillModel protocol |
| **Tests** | Parity assertions; cancel in backtest updates OMS; import allowlist for place_order |
| **Commits** | Phase **C1.1a–e** in CODE_REALITY; then FillModel / stub cancel |
| **Done when** | Grep allowlist: only OrderService/PlaceOrderUseCase/OMS internals place; mode parity green |

---

### M04 — `application.trading`

| Field | Content |
|-------|---------|
| **Purpose** | Scanner candidates → strategy eval → place via use case |
| **Owns** | `TradingOrchestrator`, feature fetcher bridge, multi-strategy **policy** (later) |
| **Must not own** | Broker, risk math, feature computation engines |
| **Contract** | `on_candidate` → 0..1 order per symbol per cycle (Phase 1 policy) |
| **Invariants** | No direct ExecutionProvider; dry_run does not mutate book; kill switch observed via OMS |
| **Defects today** | MultiStrategyRuntime is pipeline-only shell; can multi-fire signals; private capital attr access |
| **Target** | Documented netting/confidence policy; optional strategy tags on correlation_id only until Phase 3 silos |
| **Tests** | Two strategies same candidate → one order; dry_run zero places; kill switch blocks |
| **Commits** | `C-M04.1` single-order policy tests+impl; `C-M04.2` only PlaceOrderUseCase; `C-M04.3` Phase3 strategy risk budgets (later) |
| **Done when** | e2e candidate→order; no double place in suite |

---

### M05 — `application.streaming` + stream orchestration

| Field | Content |
|-------|---------|
| **Purpose** | Own live subscription lifecycle; normalize ticks to domain events |
| **Owns** | Stream orchestration wiring (today partly `tradex.runtime.stream_orchestrator` / `application.streaming`) |
| **Must not own** | Strategy decisions; OMS books |
| **Contract** | subscribe/unsubscribe; emit TICK/DEPTH with InstrumentId; reconnect resubscribe |
| **Invariants** | Tick validation (ltp); no silent swallow of subscribe failures; reconnect restores set |
| **Defects today** | Logic split tradex vs application; Upstox subscribe kwargs bug; no tick dedup; REST backfill ≠ tick continuity |
| **Target** | One orchestrator home under application; broker only provides transport; gap policy explicit (bar backfill vs tick hole metric) |
| **Tests** | Fake WS disconnect→resub; invalid tick dropped+counted; subscribe failure raises/metrics not silent |
| **Commits** | `C-M05.1` fail loud on subscribe error; `C-M05.2` consolidate orchestrator ownership; `C-M05.3` gap metrics + tests; `C-M05.4` tick dedup policy (exchange seq or ltp+ts key) |
| **Done when** | Contract: subscribe yields ticks on all three providers (paper=fixture feed) |

---

### M06 — `application.data` (historical coordinator)

| Field | Content |
|-------|---------|
| **Purpose** | Federated historical bars: chunk, cache, multi-broker/lake |
| **Owns** | `HistoricalDataCoordinator` |
| **Must not own** | Live streaming; orders |
| **Contract** | request bars → deterministic series; provenance on source |
| **Invariants** | No partial silent empty without error class; timezone consistent |
| **Defects today** | God-sized coordinator; error swallowing risk at edges |
| **Target** | Clear SourceSelector; fail closed when all sources miss; tests for chunk boundaries |
| **Tests** | Multi-chunk stitch; missing range error; lake vs broker preference policy |
| **Commits** | `C-M06.1` failure taxonomy; `C-M06.2` stitch tests; `C-M06.3` split god only after behavior locked |
| **Done when** | Coordinator contract suite green; no empty DataFrame for hard errors |

---

### M07 — `application.composer` + `runtime/*` composition

| Field | Content |
|-------|---------|
| **Purpose** | **One** composition root path for process: wire ports → TradingContext → register OMS |
| **Owns** | Factories that assemble live/paper; process registration |
| **Must not own** | Business rules |
| **Contract** | `build_trading_stack(mode, broker) -> TradingContext`; registers `process_context` |
| **Invariants** | Live: capital+store+ledger+margin required; single OMS register; no second stack |
| **Defects today** | Multiple composition roots (cli, api, tradex, runtime); unsafe standalone paper paths; dual env names |
| **Target** | Single `runtime/composition.py` (or `application/composer`) used by cli/api/tradex; others thin |
| **Tests** | Boot live without capital fails; double register warns/keeps first; paper explicit capital |
| **Commits** | `C-M07.1` fail-closed boot matrix; `C-M07.2` unify roots behind one function; `C-M07.3` delete unsafe live standalone |
| **Done when** | cli, api, tradex.connect share same OMS instance in one process (test) |

---

### M08 — `application.portfolio` / services / scheduling / audit

| Field | Content |
|-------|---------|
| **Purpose** | Portfolio views, scheduled jobs (PnL reset), audit trail for money actions |
| **Owns** | Daily PnL scheduler wiring, audit append for place/cancel |
| **Must not own** | Risk decisions (calls RiskEngine) |
| **Contract** | Scheduler resets daily pnl at IST boundary; audit record per accepted command |
| **Invariants** | Reset actually calls RiskEngine.reset_daily_pnl; audit durable if configured |
| **Defects today** | update_daily_pnl never fed; audit split memory vs OMS logger; portfolio thin |
| **Target** | Portfolio service computes MTM → risk; audit one sink |
| **Tests** | Clock skew chaos for reset; audit line after place |
| **Commits** | `C-M08.1` MTM→risk pipeline; `C-M08.2` single audit sink; `C-M08.3` scheduler lifecycle test |
| **Done when** | Daily loss e2e uses real scheduler path or documented manual update from portfolio service only |

---

### M09 — `brokers.common`

| Field | Content |
|-------|---------|
| **Purpose** | Shared contracts, tick validation, capability model, recon helpers — **no** broker-specific I/O |
| **Owns** | `BrokerCapabilities`, tick validation, status mapping registry hooks, capability validator |
| **Must not own** | Dhan/Upstox imports in prod code |
| **Contract** | Capability flags match methods; tick validator shared |
| **Invariants** | import-linter brokers.common isolation; validator covers place/cancel/get_order/stream/slice/margin |
| **Defects today** | Weak capability validator; capability flag lies (slice native); dual capability systems |
| **Target** | One capability SSOT; boot validator fails on lie; tick validation mandatory in feeds |
| **Tests** | Validator rejects misdeclared slice; tick invalid rejected |
| **Commits** | `C-M09.1` expand validator; `C-M09.2` unify capability flags; `C-M09.3` truth table fixtures per broker |
| **Done when** | Boot fails if Upstox claims native slice while client-side only |

---

### M10 — `brokers.dhan`

| Field | Content |
|-------|---------|
| **Purpose** | Dhan transport: REST+WS → domain types; ExecutionProvider + DataProvider |
| **Owns** | HTTP client, market feed, order placement, mappers |
| **Must not own** | OMS state; risk |
| **Contract** | Full ExecutionProvider + DataProvider; **get_order on gateway**; modify forwards trigger/type; stream(mode=, on_tick=) |
| **Invariants** | Rate limit + CB; reconnect resub; status mapped to domain; trade_id deterministic |
| **Defects today** | get_order missing on gateway; modify transport drops SL fields; god market_feed; cumulative fill map not durable |
| **Target** | Port-complete; gateway = thin façade over providers; durable fill watermark if needed for reconnect |
| **Tests** | Contract matrix; chaos disconnect; modify SL fields; get_order after place (fake HTTP) |
| **Commits** | `C-M10.1` get_order; `C-M10.2` modify field parity; `C-M10.3` fill watermark persistence; `C-M10.4` feed split only after contract green |
| **Done when** | Contract matrix 100% core rows for Dhan fake + unit |

---

### M11 — `brokers.upstox`

| Field | Content |
|-------|---------|
| **Purpose** | Upstox transport → domain; same ports as Dhan |
| **Owns** | Auth/token, WS v3, mappers, orders |
| **Must not own** | OMS |
| **Contract** | Same as M10; subscribe kwargs correct; slice **flagged non-native** with crash-safe recon note |
| **Invariants** | Token refresh; reconnect; no silent subscribe failure |
| **Defects today** | DataProvider.subscribe wrong signature; client-side slice; thinner CB than Dhan; god domain_mapper |
| **Target** | Port parity; honest capabilities; resilience parity bar (min: rate limit + CB on order path) |
| **Tests** | Subscribe contract; slice capability false for native; order path CB test |
| **Commits** | `C-M11.1` subscribe fix; `C-M11.2` capability honesty; `C-M11.3` order-path resilience; `C-M11.4` mapper characterization tests before split |
| **Done when** | SDK Instrument.subscribe gets ticks in integration fake; matrix green |

---

### M12 — `brokers.paper`

| Field | Content |
|-------|---------|
| **Purpose** | Deterministic execution+data for development and **validation** — not random fantasy market |
| **Owns** | Paper ExecutionProvider (sim fills through OMS), Paper DataProvider |
| **Must not own** | Random walk as default “validation” source |
| **Contract** | history from lake/fixture; stream from recorded ticks or bar-as-tick; fills via OMS + SimulatedFill config |
| **Invariants** | Same order SM as live; capital explicit; no pretend native slice |
| **Defects today** | Random OHLCV; stream stubs; instant fills only; false-green strategies |
| **Target** | Fixture/lake required for `paper_validate` profile; optional toy mode **named** `paper_toy` |
| **Tests** | History equals fixture; place→fill→position; restart paper store |
| **Commits** | `C-M12.1` split toy vs validate profiles; `C-M12.2` lake/fixture history; `C-M12.3` stream from fixture; `C-M12.4` forbid validate profile on random |
| **Done when** | `paper_validate` cannot boot without data source; parity suite uses validate only |

---

### M13 — `analytics.scanner`

| Field | Content |
|-------|---------|
| **Purpose** | Produce `CANDIDATE_GENERATED` with stable schema from features/universe |
| **Owns** | Query/rules/runner/scorer |
| **Must not own** | Order placement |
| **Contract** | CandidateDTO fields; determinism for same inputs; event payload validated |
| **Invariants** | Pure given FeatureSet; no broker side effects |
| **Defects today** | Large query modules; determinism markers exist but must be mandatory for release features |
| **Target** | Deterministic runner; contract with orchestrator on CandidateDTO |
| **Tests** | `scanner_determinism` required for changed rules; golden candidates |
| **Commits** | `C-M13.1` CandidateDTO validation; `C-M13.2` determinism gate in CI for scanner paths; `C-M13.3` no place_order grep gate |
| **Done when** | Same parquet fixture → same candidate set hash |

---

### M14 — `analytics.strategy`

| Field | Content |
|-------|---------|
| **Purpose** | Evaluate candidates → SignalDTO (actionable or not) |
| **Owns** | Pipeline, registry, builtins, evaluator bridge to domain port |
| **Must not own** | OMS |
| **Contract** | `StrategyEvaluator.evaluate` → signals; confidence bounds; strategy id set |
| **Invariants** | Side effects free; bridge is only adapter to orchestrator |
| **Defects today** | Multi-strategy runtime shell; weak capital awareness |
| **Target** | Evaluator port only; pipeline tested per builtin |
| **Tests** | Each builtin golden vector; bridge unit |
| **Commits** | `C-M14.1` port-only path; `C-M14.2` builtin goldens; `C-M14.3` confidence floor enforced in pipeline |
| **Done when** | Orchestrator uses StrategyEvaluator port exclusively |

---

### M15 — `analytics.replay` + `walk_forward` + `backtest`

| Field | Content |
|-------|---------|
| **Purpose** | Research simulation of **strategy** PnL — **not** OMS crash recovery |
| **Owns** | ReplayEngine, walk_forward, backtest runners |
| **Must not own** | Live order routing; confusing name “replay” for OMS recovery |
| **Contract** | Uses `domain.trading_costs`; deterministic given bars+seed; exports equity curve |
| **Invariants** | Costs applied to PnL; no random paper gateway history |
| **Defects today** | Naming collision with OMS event replay; cost application uneven; god engines |
| **Target** | Rename clarity in APIs (`research_replay`); costs always on; optional OMS-backed paper path separate |
| **Tests** | Cost applied ≠ zero fees; walk_forward windows; golden equity |
| **Commits** | `C-M15.1` force trading_costs; `C-M15.2` API naming disambiguation; `C-M15.3` golden determinism |
| **Done when** | Research PnL matches cost model tests; docs/API never say “crash recovery” |

---

### M16 — `analytics.features` / indicators / views / sector / options analytics

| Field | Content |
|-------|---------|
| **Purpose** | Feature computation and research views |
| **Owns** | Feature pipelines, indicator wrappers, view manager |
| **Must not own** | Duplicate pure indicators if domain owns math — **one** pure impl |
| **Contract** | FeatureSet schema for strategy; versioned feature names |
| **Invariants** | Deterministic features for same bars; no live order |
| **Defects today** | Dual indicators domain vs analytics; ViewManager god; precompute large |
| **Target** | domain = pure math; analytics = data plumbing; feature version in metadata |
| **Tests** | Feature golden; indicator parity domain vs analytics wrapper |
| **Commits** | `C-M16.1` indicator SSOT decision+tests; `C-M16.2` FeatureSet contract; `C-M16.3` split views after goldens |
| **Done when** | Strategy tests use Feature only via FeatureFetcher port |

---

### M17 — `analytics.paper` (research paper engine)

| Field | Content |
|-------|---------|
| **Purpose** | Legacy/research paper engine — **must not** be a second live paper OMS |
| **Owns** | Until merge: research-only simulation |
| **Must not own** | Competing order book |
| **Defects today** | Dual with `brokers.paper` |
| **Target** | **Merge path:** research calls FillModel/OMS paper; delete dual book |
| **Tests** | Single book assertion process-wide |
| **Commits** | `C-M17.1` characterize dual behavior; `C-M17.2` redirect to brokers.paper+OMS; `C-M17.3` delete dual engine |
| **Done when** | Only one paper order book in process |

---

### M18 — `datalake` (storage, ingestion, quality, research, gateway)

| Field | Content |
|-------|---------|
| **Purpose** | Durable market history SoR for research + paper_validate + backtest |
| **Owns** | Parquet layout, DuckDB catalog, ingestion, quality engines, gateway |
| **Must not own** | Orders, broker auth |
| **Contract** | read bars by symbol/tf/range; quality report; ingestion idempotent |
| **Invariants** | No silent corrupt OHLC; quality gates optional-but-defined for validate profile |
| **Defects today** | Local-only; quality not forced for paper_validate; time sync limited |
| **Target** | `paper_validate` and backtest **require** quality threshold or explicit override flag |
| **Tests** | Duplicate detection; gap report; ingestion idempotent; gateway contract |
| **Commits** | `C-M18.1` quality gate API; `C-M18.2` wire paper_validate; `C-M18.3` ingestion idempotency tests; `C-M18.4` normalize timezone contract |
| **Done when** | Backtest refuses empty/corrupt ranges without override |

---

### M19 — `infrastructure.event_bus` + `event_log`

| Field | Content |
|-------|---------|
| **Purpose** | In-process dispatch + durable audit log for capital events |
| **Owns** | EventBus, DLQ, EventLog/BufferedEventLog, metrics hooks |
| **Must not own** | Order business rules |
| **Contract** | publish/subscribe; persist-before-dispatch for capital; DLQ on handler fail |
| **Invariants** | TRADE/ORDER fsync; no drop of TRADE/ORDER_UPDATED on async path; codecs round-trip Order/Trade |
| **Defects today** | Buffered loss window; async critical set wrong; mark-before-handler bus idempotency; weak DLQ payload; cold deserialize |
| **Target** | Capital events durable; codecs; DLQ redrive CLI; async never drops money events |
| **Tests** | Round-trip serialize; kill during buffer; async drop test inverted; redrive |
| **Commits** | `C-M19.1` fsync capital; `C-M19.2` codecs; `C-M19.3` async critical set; `C-M19.4` DLQ full payload+redrive; `C-M19.5` bus idempotency after success |
| **Done when** | Cold process replays capital events into objects (with OMS store as SoR) |

---

### M20 — `infrastructure.persistence` + idempotency + ledger

| Field | Content |
|-------|---------|
| **Purpose** | Durable OMS order store + processed trade ledger + locks |
| **Owns** | `SqliteOrderStore`, writer lock, processed trade repo impl |
| **Must not own** | Risk |
| **Contract** | upsert/load_all/lock; ledger is_processed/mark/load |
| **Invariants** | Single writer; load after crash complete; fsync policy documented |
| **Defects today** | Store not wired to OMS; WAL NORMAL may lose last tx on power loss (document + optional FULL for live) |
| **Target** | Wired SoR; live profile synchronous=FULL optional flag |
| **Tests** | Writer lock exclusion; restart load; concurrent place |
| **Commits** | `C-M20.1` wire OMS (with C0.4); `C-M20.2` durability profile; `C-M20.3` ledger/store integration test |
| **Done when** | Store empty ⇒ recover fails closed or recon-only mode explicit |

---

### M21 — `infrastructure.resilience` (+ kill dual in tradex)

| Field | Content |
|-------|---------|
| **Purpose** | Retry, CB, rate limit, backoff — **one** library |
| **Owns** | Canonical implementations under `infrastructure/resilience/` |
| **Must not own** | Broker-specific business mapping (config ok) |
| **Contract** | Same classes used by dhan/upstox HTTP |
| **Invariants** | No second implementation tree |
| **Defects today** | **Mostly fixed in code:** `tradex/runtime/resilience/*.py` are already re-export shims (e.g. `from infrastructure.resilience.circuit_breaker import *`). Remaining: standardize import sites; optional delete shims later |
| **Target** | Imports prefer `infrastructure.resilience`; shims optional for compat |
| **Tests** | CB state machine; rate limit; import graph |
| **Commits** | **Demoted** — not a Phase 0/1 blocker. Optional `chore`: prefer infra imports; delete shims when safe |
| **Done when** | No second full implementation tree (already true); greps show no divergent logic |

---

### M22 — `infrastructure.lifecycle` / health / observability / time

| Field | Content |
|-------|---------|
| **Purpose** | Start/stop ordered services; health; metrics; clocks |
| **Owns** | LifecycleManager, health aggregation, metrics registry, TimeService |
| **Contract** | register/start/stop; /healthz /readyz reflect OMS gate + broker |
| **Invariants** | Ready false until recon gate open if configured; time tz-aware |
| **Defects today** | Empty health registry can look healthy; alerting not mandatorily wired |
| **Target** | Ready = composition checks; alerting optional sink interface |
| **Tests** | Lifecycle drain; ready false when gate closed |
| **Commits** | `C-M22.1` ready semantics; `C-M22.2` health requires checks; `C-M22.3` time contract tests |
| **Done when** | e2e: pre-recon readyz not ready |

---

### M23 — `infrastructure.auth` / connection / gateway (technical)

| Field | Content |
|-------|---------|
| **Purpose** | Token/TOTP helpers, connection bootstrap — shared by brokers |
| **Owns** | Credential resolution, token ensure patterns |
| **Must not own** | API user auth (that's api.auth — deferred security) |
| **Contract** | Token refresh hooks; fail on missing creds in live |
| **Defects today** | Split with broker auth packages |
| **Target** | Clear boundary: infra = generic; broker = vendor endpoints |
| **Tests** | Missing creds fail; refresh scheduling unit |
| **Commits** | `C-M23.1` boundary tests; `C-M23.2` remove duplicate token logic where safe |
| **Done when** | Live boot without creds fails with typed error |

---

### M24 — `api` (HTTP + WS)

| Field | Content |
|-------|---------|
| **Purpose** | Presentation: map HTTP/WS ↔ use cases; no business rules |
| **Owns** | routers, schemas, middleware, ws bridge |
| **Must not own** | Risk formulas; direct broker place bypassing OMS |
| **Contract** | Orders → PlaceOrderUseCase; WS ticks from bus; errors typed |
| **Invariants** | correlation_id generated/required; broker resolved server-side |
| **Defects today** | Possible connect-per-request cost; extended raw dict; feature flags (security deferred but money flags still dangerous — **control-plane flags that change execution must go through admin or local-only until SEC**) |
| **Target** | All order routes use use cases; WS backpressure documented; schemas for extended orders |
| **Tests** | API order → OMS book; WS seq; reject without correlation where required |
| **Commits** | `C-M24.1` orders router → use case only; `C-M24.2` extended schemas; `C-M24.3` ws contract tests |
| **Done when** | Integration: POST order visible in OMS get |

**Security:** deferred; still no cosmetic-only “auth refactor” without SEC plan.

---

### M25 — `cli` + TUI

| Field | Content |
|-------|---------|
| **Purpose** | Operator surface; doctor; place/cancel; dashboards |
| **Owns** | commands, services bootstrap, textual UI |
| **Must not own** | Parallel OMS |
| **Contract** | Bootstrap calls unified composition; doctor checks ports+store+risk feed |
| **Invariants** | Same process OMS as API if both run — document single entry |
| **Defects today** | Large command set; bootstrap complexity; doctor may not check recovery readiness |
| **Target** | Doctor verifies Phase 0 exits (store, capital, ledger); commands call use cases |
| **Tests** | Offline command smoke; doctor fails if store unwired |
| **Commits** | `C-M25.1` doctor money-path checks; `C-M25.2` commands → use cases; `C-M25.3` remove duplicate bootstrap |
| **Done when** | `cli doctor` fails red on intentional broken capital |

---

### M26 — `tradex` (SDK façade)

| Field | Content |
|-------|---------|
| **Purpose** | Public Python API: `connect`, Session, Instrument ergonomics |
| **Owns** | `session.py`, thin exports |
| **Must not own** | Second runtime kernel; duplicate resilience |
| **Contract** | connect → providers + registered OMS; Instrument.buy → use case |
| **Invariants** | Live refuses unsafe standalone OMS; uses process registry |
| **Defects today** | Large `tradex.runtime` second platform; dual resilience |
| **Target** | runtime shrink to zero business logic; move to application/infrastructure |
| **Tests** | connect paper_validate; buy hits OMS; live without register fails |
| **Commits** | `C-M26.1` buy→use case; `C-M26.2` move stream/router ownership; `C-M26.3` delete residual runtime code in slices |
| **Done when** | tradex/runtime LOC &lt; threshold of shims only (track metric) |

---

### M27 — `config` + feature flags + profiles

| Field | Content |
|-------|---------|
| **Purpose** | Typed config, profiles (dev/stage/prod), feature flags |
| **Owns** | schema, profiles, flags, secrets_manager (env/file) |
| **Contract** | Profile defines mode requirements (live needs capital path) |
| **Invariants** | Single env name for environment (`TRADEX_ENV`); flags cannot silently disable risk |
| **Defects today** | APP_ENV vs TRADEX_ENV; flags can change execution without admin (SEC deferred — for money: **flags that bypass risk forbidden in code**) |
| **Target** | Risk bypass flags do not exist; env alias one way |
| **Tests** | Profile validation; risk_fail_open rejected |
| **Commits** | `C-M27.1` env unify; `C-M27.2` ban risk bypass flags; `C-M27.3` profile matrix boot tests |
| **Done when** | production_config + profile tests green; no RISK_FAIL_OPEN path |

---

### M28 — Cross-cutting `tests/` + CI

| Field | Content |
|-------|---------|
| **Purpose** | Contract, chaos, e2e, quant parity, architecture fitness |
| **Owns** | Cross-module suites; CI workflows |
| **Contract** | See design §6 + this program exits |
| **Defects today** | Ghost frontend job; missing e2e file; chaos not multi-process cold start; markers sparse |
| **Target** | CI reflects real suite; architecture tests encode module laws |
| **Commits** | `C-M28.1` fix CI ghosts; `C-M28.2` cold-start job; `C-M28.3` architecture grep gates (no analytics place_order); `C-M28.4` contract matrix job |
| **Done when** | CI config references only existing paths; money gates required |

---

## 4. Integration contracts (module ↔ module)

These are **tests**, not diagrams for show.

| ID | Producer | Consumer | Assertion |
|----|----------|----------|-----------|
| I1 | Scanner | Orchestrator | CandidateDTO schema validates |
| I2 | Strategy | Orchestrator | SignalDTO actionable fields |
| I3 | Orchestrator | PlaceOrderUseCase | only entry |
| I4 | Use case | OMS | risk called once |
| I5 | OMS | OrderStore | row exists after place |
| I6 | OMS | Ledger | after fill, is_processed |
| I7 | OMS | RiskEngine | daily_pnl changes after fill path |
| I8 | Broker stream | OMS | TRADE updates position once |
| I9 | DataProvider | Instrument | subscribe delivers tick |
| I10 | Composition | Process registry | get_oms_context is identity |
| I11 | Datalake | Paper validate | history non-random |
| I12 | Replay research | trading_costs | fees &gt; 0 when configured |
| I13 | Lifecycle | Readyz | false if gate closed |
| I14 | Recon | Placement gate | blocks until success |

---

## 5. Master commit roadmap (module-complete, not cosmetic)

Phases still ordered by **risk**, but each phase **finishes modules** to exit criteria — not “touch files.”

### Phase 0 — Money integrity (modules M01 partial, M02, M03 partial, M10–11 partial, M19–20, M28 partial)

Behavioral commits only (see design C0.* +):

- Domain notional/multiplier (M01)  
- OMS risk+store+ledger (M02, M20)  
- Event durability (M19)  
- Broker P0 (M10, M11)  
- CI truth (M28)  

**Phase 0 exit:** G2+G3 true; I5–I9 core green.

### Phase 1 — Single path + honest modes (M03, M04, M07, M12, M17, M24–26, M05 partial)

- Use cases only; paper validate; kill dual paper; composition one root; orchestrator policy; API/CLI/tradex redirect  

**Phase 1 exit:** G1+G5+G6; I1–I4, I10–I11.

### Phase 2 — Platform kernel + data truth (M05, M06, M09, M18, M21, M22, M15, M16 partial)

- Stream ownership; lake quality gates; single resilience; research costs; capability honesty; health ready  

**Phase 2 exit:** G4 full matrix; G8–G9; dual resilience gone.

### Phase 3 — Depth & scale-out of correctness (M14 multi-strategy, M16, M10–11 feed quality, options risk)

- Strategy silos; indicator SSOT; tick dedup; greeks risk if F&O auto  

**Phase 3 exit:** multi-strategy without double books; F&O risk complete.

---

## 6. Per-module status board (track in commits)

Copy into a living checklist (update when a module hits **Done when**):

| ID | Module | Status | Exit evidence (test path / commit) |
|----|--------|--------|-------------------------------------|
| M01 | domain | OPEN | |
| M02 | application.oms | OPEN | |
| M03 | application.execution | OPEN | |
| M04 | application.trading | OPEN | |
| M05 | streaming | OPEN | |
| M06 | historical data | OPEN | |
| M07 | composition | OPEN | |
| M08 | portfolio/audit/sched | OPEN | |
| M09 | brokers.common | OPEN | |
| M10 | brokers.dhan | OPEN | |
| M11 | brokers.upstox | OPEN | |
| M12 | brokers.paper | OPEN | |
| M13 | analytics.scanner | OPEN | |
| M14 | analytics.strategy | OPEN | |
| M15 | analytics.replay/wf | OPEN | |
| M16 | features/indicators | OPEN | |
| M17 | analytics.paper dual | OPEN | |
| M18 | datalake | OPEN | |
| M19 | event bus/log | OPEN | |
| M20 | persistence/ledger | OPEN | |
| M21 | resilience unify | OPEN | |
| M22 | lifecycle/health | OPEN | |
| M23 | infra auth/conn | OPEN | |
| M24 | api | OPEN | |
| M25 | cli | OPEN | |
| M26 | tradex | OPEN | |
| M27 | config | OPEN | |
| M28 | tests/CI | OPEN | |

Status values: `OPEN` | `IN_PROGRESS` | `EXIT_MET` | `DEFERRED` (only security-related slices).

---

## 7. Definition of “module EXIT_MET”

All must be true:

1. **Done when** row satisfied  
2. Mandatory tests listed exist and pass  
3. Integration contracts for that module green  
4. No known dual path remaining for that module’s ownership  
5. Commit messages under `phase*/mXX` or design C* references in log  
6. No `chore`-only commits counted as exit  

---

## 8. What we refuse

- “Cleanup pass” across brokers without contract matrix  
- “Refactor tradex.runtime” without moving behavior to named module exits  
- “Improve paper” without lake/fixture profile  
- “Add logging” instead of fail-closed  
- Marking M02 done without cold-start  
- Marking M12 done while random walk remains default  

---

*This program is the exhaustive module plan. Architecture spine: `TARGET_SYSTEM_DESIGN.md`. Findings: `docs/reports/PRODUCTION_BOARD_REVIEW_CODE_ONLY_2026-07-10.md`.*
