# Deep Architecture Proposal — Institutional Trading Framework

**Date:** 2026-07-09 · **Branch:** `refactor/brokers-consolidation`  
**Board:** Multi-expert review (OMS, DDD, MD, HPC, DX, Reliability, …)  
**Companion:** `reports/ARCHITECTURE_REVIEW_BOARD_2026-07-09.md`  
**Status:** TARGET + MIGRATION PLAN — evidence-backed from live AST/graphify scan

---

## 1. Problem Statement

TradeXV2 works as a multi-broker trading platform. It does **not** yet feel like an
institutional object framework. Users still cross cut layers to place orders, three
`Instrument` types coexist, `place_order` appears in ~30 call sites across 6 layers,
and the package graph still encodes *history of refactors* rather than *domain shape*.

**Mission success criteria:**

```python
import tradex

s = tradex.connect("dhan")                 # one composition root
r = s.equity("RELIANCE")                   # domain object
print(r.quote.ltp, r.history("5m"))
o = r.buy(qty=10, limit=2955)              # OrderIntent → Risk → OMS → Exchange
s.portfolio.positions                      # first-class portfolio
```

No gateway classes, no HTTP, no DuckDB, no Redis in user code.

---

## 2. Current-State Map (evidence)

### 2.1 Package size (production Python, excl tests)

| Package | Files | LOC | Role today | Role target |
|---------|------:|----:|------------|-------------|
| `brokers/` | 297 | 40.7k | Adapters + residual common | **Adapters only** (~dhan/upstox/paper) |
| `analytics/` | 92 | 16.2k | Research engine | Research BC (ports only in) |
| `cli/` | 90 | 14.0k | Presentation + orchestration | Presentation only |
| `src/domain/` | 147 | 13.0k | Domain model | Domain (tighten purity) |
| `datalake/` | 77 | 10.6k | Storage + some analytics | Persistence BC |
| `infrastructure/` | 52 | 9.0k | Bus, DI, metrics, cache | Infrastructure |
| `application/` | 48 | 7.6k | OMS, execution, trading | Application services |
| `api/` | 42 | 7.5k | REST/WS | Presentation |
| `tradex/` | 46 | 7.1k | Public SDK + runtime kernel | **Public SDK + platform kernel** |
| `config/` | 13 | 2.6k | Config | Config |
| `plugins/` | 9 | 86 | Indicators plugins | Plugins (domain must not import) |
| `providers/` | 4 | 328 | Legacy | **Delete** (fold into brokers/tradex) |

### 2.2 Canonical types vs impostors

| Concept | Canonical | Impostors / collision |
|---------|-----------|----------------------|
| **Order** | `domain.entities.order.Order` | API `Position` schema OK; order path clean |
| **OrderRequest** | `domain.orders.requests.OrderRequest` | `api.schemas.OrderRequest` (DTO — rename to `OrderRequestDTO`); OMS uses `OmsOrderCommand` (good rename, keep) |
| **Instrument** | `domain.instruments.instrument.Instrument` | `tradex.runtime.instruments.Instrument` (registry DTO); `brokers.dhan.domain.Instrument` (broker DTO — **must not share name**) |
| **OptionChain** | `domain.options.option_chain.OptionChain` (rich) | `domain.entities.options.OptionChain` (frozen VO) — dual intentional only if renamed: VO=`OptionChainSnapshot` |
| **Session** | `domain.universe.Session` | `brokers.common.objects.BrokerSession` (composition root twin) |
| **Position** | `domain.entities.position.Position` | `api.schemas.Position` (Pydantic DTO) |
| **Portfolio** | `domain.portfolio.portfolio.Portfolio` | OK (single) |
| **OrderManager** | `application.oms.order_manager` | OK (single) |
| **place_order** | *should be one spine* | **~30 definitions** across domain ports, OMS, execution, API, CLI, brokers, datalake stub |

### 2.3 Exact file duplicates (delete candidates)

| Dup A | Dup B | Action |
|-------|-------|--------|
| `domain/aggregates/position.py` | `domain/positions/aggregate.py` | Keep one re-export → delete other |
| `domain/aggregates/account.py` | `domain/accounts/aggregate.py` | Same |
| `analytics/scanner/rules/models.py` | `datalake/scanner/models.py` | Single model in domain/analytics; datalake stores only |
| OMS tests under `application/oms/tests` | clones under `brokers/common/oms/tests` | Delete broker clone suite |
| `.qoder/skills/*` | `.trae/skills/*` | Tooling noise — not product |

### 2.4 Active dependency violations

| Edge | Severity | Fix |
|------|----------|-----|
| `domain → plugins` (indicators) | P0 | Invert or relocate indicators |
| `datalake → analytics` (cycle) | P0 | datalake pure storage; analytics → HistoryPort |
| `cli → brokers.dhan` | P1 | registry only |
| Mid-migration dual kernel `brokers.common` ⇄ `tradex.runtime` | P0 structural | Finish move |

---

## 3. Target Architecture

### 3.1 Layer cake (dependency direction: down only)

```
┌─────────────────────────────────────────────────────────────────┐
│  PRESENTATION                                                    │
│  api/  ·  cli/  ·  (future UI)                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ depends on
┌────────────────────────────▼────────────────────────────────────┐
│  PUBLIC SDK  (tradex)                                            │
│  tradex.connect · Session · Universe · re-exports domain objects │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  APPLICATION                                                     │
│  OMS · Risk · Execution · Portfolio projection · Trading orch.   │
│  StrategyRuntime · ScannerRuntime (roles, not mega-packages)     │
└────────────────────────────┬────────────────────────────────────┘
                             │ ports only
┌────────────────────────────▼────────────────────────────────────┐
│  DOMAIN  (src/domain)                                            │
│  Instrument · Order · Position · Portfolio · OptionChain         │
│  OrderIntent · Events · RiskPolicy · Ports (protocols)           │
│  ZERO imports of brokers/infra/analytics/datalake/plugins        │
└────────────────────────────▲────────────────────────────────────┘
                             │ implements ports
┌────────────────────────────┴────────────────────────────────────┐
│  ADAPTERS & INFRASTRUCTURE                                       │
│  brokers/{dhan,upstox,paper}  ·  tradex.runtime (kernel)         │
│  infrastructure/*  ·  datalake/*  ·  cache/redis/sqlite           │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Bounded contexts

| Context | Owns | Does not own |
|---------|------|--------------|
| **Domain** | Identity, invariants, VOs, ports, event *types* | HTTP, WS, DB, pandas I/O |
| **OMS** | Order lifecycle, risk admission, reconciliation orchestration | Broker wire formats |
| **Market Data** | Subscriptions, normalization to VO, history access via port | Order placement |
| **Broker Adapter** | Auth, wire, rate limits *per broker*, map raw→domain | Business risk rules |
| **Portfolio** | Positions, PnL projection from fills + quotes | Order state machine |
| **Analytics / Research** | Indicators, scanners, backtest math | Live order submit |
| **Persistence (Datalake)** | Parquet/DuckDB storage, catalog | Indicator formulas |
| **Platform Kernel** (`tradex.runtime`) | Registry, router, quotas, stream orchestration, adapter factory | Domain rules |
| **Presentation** | CLI/API DTOs, UX | Domain logic |

### 3.3 Object model (Unreal / Pandas / SQLAlchemy / PyTorch analogue)

```
tradex.Session                         # like Engine / Module root
├── .connect(broker, profile)          # composition root
├── .universe                          # Instrument factory + cache (single owner)
│     ├── equity/index/future/option → domain.Instrument
│     └── resolve(InstrumentId)
├── .oms                               # application OrderManager façade
├── .portfolio                         # domain Portfolio bound to providers
├── .account                           # balances / margin
├── .bus                               # DomainEventBus port
└── .capabilities                      # what this session can do

Instrument (domain)                    # like DataFrame / UObject
├── id: InstrumentId
├── state: InstrumentState (atomic replace)
├── quote / depth / history / subscribe
├── buy/sell → OrderIntent (never raw broker)
├── option_chain() → OptionChain
└── extensions via capability registry (not decorator subclasses)

OptionChain                            # aggregate of Option instruments + VO snapshot
OrderIntent → Order (OMS aggregate) → Trade → Position
```

**Naming rules (hard):**

1. Only **one** production class may be named `Instrument`, `Order`, `Position`, `OptionChain` (rich), `Session` (user-facing).
2. Broker/registry DTOs use suffixes: `InstrumentRecord`, `WireOrder`, `BrokerInstrumentRef`.
3. API schemas use `*DTO` / Pydantic models, never shadow domain names without `DTO` suffix.

### 3.4 Port catalogue (consolidated ~10, not 24)

| Port | Replaces / absorbs |
|------|-------------------|
| `DataProvider` | market data, history, depth, option chain, subscribe |
| `ExecutionProvider` | place/modify/cancel, order book, positions, funds |
| `BrokerAdapter` | optional union + auth lifecycle (composition only) |
| `EventBusPort` | publish/subscribe |
| `EventLogPort` / `ProcessedTradeRepositoryPort` | durability / idempotency |
| `OrderStorePort` | order persistence |
| `RiskManagerPort` | pre-trade checks (or keep as domain service injected) |
| `HistoryStorePort` | datalake / parquet access (new; breaks analytics→datalake concrete) |
| `TimeServicePort` | clock (live vs replay) |
| `MetricsPort` | counters/histograms |

Everything else is application service or adapter detail.

---

## 4. Core Flows

### 4.1 Boot / composition

```
Config + Secrets
    → tradex.connect(broker, profile)
        → Registry.resolve(broker) → concrete gateway/transport
        → create_data_adapter + create_execution_provider
        → EventBus + OrderStore + RiskManager + OrderManager
        → Domain Session(Universe, providers, oms handle)
        → optional: warm InstrumentRepository / history
    → return tradex.Session
```

**Today:** `tradex.open_session` only auto-builds **paper**; live needs injected gateway.  
**Target:** `connect("dhan")` loads credentials via config and registry.

### 4.2 Market data (quote / stream)

```
Exchange WS/REST
    → Broker transport (dhan/upstox)
    → Normalizer (broker-local) ──► domain QuoteSnapshot / MarketDepth / Tick
    → DataProvider
    → Instrument._state atomic replace
    → DomainEvent(QuoteChanged)
    → Portfolio MTM · Strategies · API WS · CLI views
```

**Invariants:**

- Normalization happens **once** at adapter edge.
- Domain never sees raw broker JSON.
- Replay injects the same VOs via `ReplayDataProvider` + `TimeService`.

### 4.3 Order lifecycle (institutional spine)

```
User / Strategy
    Instrument.buy(qty, limit) 
        → OrderIntent {instrument_id, side, qty, price, product, correlation_id}
    → RiskManager.evaluate(intent, portfolio, limits)
        → reject → OrderRejected event; stop
        → approve → RiskApproved event
    → OrderManager.admit(OmsOrderCommand)
        → persist NEW/PENDING
        → submit_fn = ExecutionProvider.place_order(domain OrderRequest)
    → Broker adapter maps OrderRequest → wire payload
    → Exchange
    → Execution report (WS/REST)
    → Normalizer → domain Order / Trade
    → OrderManager.on_order_update / on_trade
        → state machine (ORDER_STATUS_TRANSITIONS)
        → PositionManager / OrderPositionUpdater
        → events: OrderFilled, PositionChanged
    → Portfolio projection + audit log
```

**Forbidden shortcuts:**

- CLI/API → `brokers.dhan.orders.place_order` bypassing OMS  
- `Session.buy` → ExecutionProvider without Risk  
- Paper path that skips OMS state machine (paper may use in-memory OMS, not no OMS)

### 4.4 Historical / analytics

```
HistoryStorePort (datalake parquet/duckdb)
    → HistoricalSeries (domain)
    → optional .to_dataframe() at analytics boundary only
    → indicators / scanners / backtest engine
    → signals → OrderIntent (same spine as live)
```

### 4.5 Replay / paper / live parity

```
                    ┌─ LiveDataProvider + LiveExecution
Session ────────────┼─ PaperDataProvider + PaperExecution (sim fills)
                    └─ ReplayDataProvider + SimExecution + FixedTimeService
```

Same `Instrument` API. Strategy cannot branch on mode (fitness test).

### 4.6 Event flow

```
Producer (adapter / OMS / Instrument)
    → DomainEvent (frozen, tz-aware, event_id, correlation_id)
    → EventBusPort
        → sync/async handlers
        → DLQ on failure
        → optional EventLogPort persistence
    → consumers: OMS, Portfolio, Metrics, API WS fanout
```

Typed wrappers (`OrderUpdatedEvent`, …) preferred for OMS-critical paths.

---

## 5. Duplication & Smell Removal Plan

### 5.1 P0 — Kill identity collisions

| # | Item | Action | Owner layer |
|---|------|--------|-------------|
| D1 | 3× `Instrument` | Rename runtime DTO → `InstrumentRecord`; dhan → `DhanInstrumentRef` | kernel / broker |
| D2 | 2× `OptionChain` | VO → `OptionChainSnapshot`; rich stays `OptionChain` | domain |
| D3 | 2× Session entry | Merge `BrokerSession` into `tradex.Session` / domain `Session` | SDK |
| D4 | Exact dup aggregates | Delete `positions/aggregate.py` or `aggregates/position.py` twin | domain |
| D5 | OMS test clones in `brokers/common/oms/tests` | Delete entire clone tree | brokers |
| D6 | `domain → plugins` indicators | Domain defines `Indicator` protocol + pure refs **or** move indicators fully to analytics/plugins | domain |
| D7 | `datalake ↔ analytics` cycle | Introduce `HistoryStorePort`; datalake implements; analytics depends on port only | research |

### 5.2 P1 — Collapse order placement fan-out

**Target call graph (only):**

```
Presentation → Application OMS → ExecutionProvider port → Broker adapter
```

| Current site | Disposition |
|--------------|-------------|
| `OrderManager.place_order` | **Canonical** |
| `ExecutionProvider.place_order` | Port (transport) |
| `application/execution/*` | Thin mode adapters → OMS |
| `api/routers/orders.place_order` | DTO → OMS command |
| `cli/.../order_placement` | CLI → OMS |
| `brokers/*/orders.place_order` | Private transport only |
| `datalake.gateway.place_order` | **Delete** (nonsense on storage gateway) |
| `domain/services/orders.py` | Delete or make pure domain helper without I/O |
| `domain/repositories/order_repository.py` | Port only; impl in application/infra |
| dual API live vs non-live routers | Unify behind one orders module |

### 5.3 P1 — Symbol / status / OHLCV normalization

| Function | Keep | Delete / delegate |
|----------|------|-------------------|
| `domain.symbols.normalize_symbol/exchange` | **Canonical** | — |
| `datalake.core.symbols.normalize_symbol` | Delegate to domain | Remove divergent logic |
| `StatusMapperRegistry` + broker maps | **Canonical** | OK pattern |
| `upstox.domain_mapper.normalize_status` | Call registry | No private map drift |
| `analytics.core.models.normalize_ohlcv` | Analytics-local bar hygiene OK | Must not redefine symbol rules |
| `datalake.normalize` / `ingestion.normalize_to_canonical` | Storage schema hygiene | Share VO builders with broker normalizers where possible |

### 5.4 P2 — Package / module smells

| Smell | Evidence | Fix |
|-------|----------|-----|
| God file | `capability_manifest.py` ~1279 LOC | Split by capability family |
| God object residual | `Instrument` 565 LOC + extensions | OK if pure; strip pandas; stubs → real or remove |
| Dual kernel | common re-exports + residual auth/resilience | Finish `tradex.runtime` move |
| Fat port set | 24 port modules | Consolidate to ~10 |
| Anemic stubs | `Future.basis/rollover` return None | Implement domain math or hide API |
| Shadow DTO names | API `Position`, `OrderRequest` | Suffix `DTO` |
| Presentation orchestration | CLI imports dhan | Registry + application services only |
| Multiple composition roots | DI + factory + registry + open_session | One: `tradex.connect` |
| Test-coupled architecture | OMS unit tests import infrastructure | Prefer fakes implementing ports |
| Dead packages | `providers/`, empty aggregates long-term | Delete |
| pandas in domain | `instrument.py` import pandas | Lazy export at boundary |

### 5.5 P2 — `place_order` / gateway naming debt

- Public docs and SDK: never say `Gateway`.
- Internal: `*Transport` or `*Adapter`.
- `MarketDataGateway` alias: mark expired (deadline + import counter in CI).

---

## 6. Package-by-Package Verdict

| Package | Keep? | Merge/Split/Remove | Notes |
|---------|-------|--------------------|-------|
| `src/domain` | **Keep** | Split capability_manifest; delete aggregates when zero-ref; fix indicators | Core |
| `application/oms` | **Keep** | Canonical OMS | Expand as only order brain |
| `application/execution` | **Keep thin** | Must route through OMS | No parallel OMS |
| `application/trading` | **Keep** | Strategy orchestration | |
| `application/composer` | **Keep** | Composition helpers | Eventually absorbed by tradex.connect |
| `tradex` | **Keep & grow** | Public API + runtime kernel | Primary product surface |
| `tradex.runtime` | **Keep** | Absorb remaining common | Kernel |
| `brokers.common` | **Shrink → delete** | Re-exports then gone | Residual subsystems move to runtime/infra |
| `brokers.dhan/upstox/paper` | **Keep** | Adapters only | Rename local Instrument types |
| `infrastructure` | **Keep** | Implement ports | No domain logic |
| `datalake` | **Keep** | No analytics imports | HistoryStorePort impl |
| `analytics` | **Keep** | Consume domain + HistoryPort | |
| `api` / `cli` | **Keep** | No broker concretes | DTOs only |
| `config` | **Keep** | Single config story | |
| `plugins` | **Keep** | Outward only | |
| `providers` | **Remove** | Fold | |
| `poc` | **Isolate** | Research sandbox | Not product |

---

## 7. Phased Implementation Plan

### Wave A — Isolation truth (2–4 days)

1. Fix domain indicators dependency (D6).
2. Break datalake→analytics cycle (D7).
3. Rename colliding `Instrument` types (D1).
4. Fitness tests + import-linter: fail without carve-outs for D6/D7.
5. Delete exact aggregate file twins (D4) and OMS test clones (D5).

**Gate:** `lint-imports` green; architecture fitness green; no `from plugins` in domain.

### Wave B — Single kernel (1 week)

1. Move residual common (auth, resilience, idempotency, services, options, objects) into `tradex.runtime` or `infrastructure` by ownership.
2. `brokers/` = dhan + upstox + paper only (+ shim package with expiry).
3. Unify Session: one public `tradex.Session`.
4. CI counter for `brokers.common` imports trending to zero.

**Gate:** no new code under `brokers/common` except shims; registry resolves all brokers.

### Wave C — Order spine (1–2 weeks)

1. Introduce `OrderIntent` VO.
2. `Instrument.buy/sell` → intent only.
3. Wire Session/API/CLI exclusively through `OrderManager`.
4. Delete `datalake.gateway.place_order` and orphan domain order service I/O.
5. Paper/live/replay parity tests on spine.
6. Risk mandatory (no bypass flag in prod profiles).

**Gate:** single path integration test: intent → risk → OMS → fake execution → position.

### Wave D — Object completeness (1–2 weeks)

1. `tradex.connect("dhan"|"upstox"|"paper")` full.
2. Universe cache sole factory.
3. OptionChain VO rename; rich chain complete.
4. Remove pandas from domain import graph.
5. Implement or remove Future/Option stubs.
6. Split capability_manifest.

**Gate:** 5-line script places paper order via Instrument; strategy tests import zero brokers.

### Wave E — Data boundary (ongoing)

1. One normalizer family: wire → domain VO.
2. HistoryStorePort; analytics/datalake decouple.
3. ReplayDataProvider first-class.

### Wave F — Deletion & DX

1. Remove shims, gateway aliases, dead packages.
2. Port consolidation.
3. SDK cookbook (10 recipes).
4. Update ARCHITECTURE.md to match reality.

---

## 8. Testing Strategy (architecture-enforcing)

| Layer | Tests | Rule |
|-------|-------|------|
| Domain | Pure unit, fakes for ports | No network, no pandas required |
| OMS | Port fakes (EventBusPort, OrderStorePort) | No real EventBus/SQLite for core lifecycle |
| Broker adapters | Contract suite + golden packets | Map to domain VOs only |
| Integration | One spine per broker | Real or recorded HTTP/WS |
| Architecture | import-linter + fitness + “one type” greps | CI red on regression |
| Parity | same strategy live/paper/replay | assert identical decisions given same VO stream |

---

## 9. Performance & Reliability Notes (HPC / SRE)

- **Hot path:** tick → VO → Instrument state replace → bus publish. No ORM, no reflection.
- **Batch:** `get_quotes_batch` / `history_batch` stay on DataProvider; avoid N+1 in scanners.
- **Backpressure:** EventBus DLQ + bounded queues (already present) — keep; do not add Kafka until single-process proven insufficient.
- **Idempotency:** correlation_id required (OMS already enforces) — extend to all presentation entry points.
- **Kill switch / square-off:** stay in application OMS, not broker-specific.

---

## 10. DX Target API

```python
import tradex

# Research
s = tradex.connect("paper")
nifty = s.index("NIFTY")
df = nifty.history("1D", lookback_days=252).to_dataframe()  # export only

# Live
s = tradex.connect("dhan", profile="prod")
rel = s.equity("RELIANCE")
rel.subscribe()
intent = rel.buy(qty=1, limit=rel.quote.ltp)
# intent tracked: s.oms.orders[intent.correlation_id]

# Options
chain = rel.option_chain(expiry="2026-07-31")
atm = chain.atm
print(atm.greeks.delta)
```

---

## 11. Risks & Non-Goals

**Risks:** Wave B/C touch CLI/API wiring — mitigate with shims + parity gate.  
**Non-goals:** microservices, full UI redesign, rewrite of broker HTTP stacks, new broker before Wave B.

---

## 12. Board Decision

**Approve target architecture in this document.**  
**Execute Wave A immediately**, then B, then C — no parallel feature work that deepens residual `brokers.common` or bypasses OMS.

**Reject:** decorator instrument stacks, permanent dual kernel, pandas-as-domain, buy-without-OMS, domain→plugins imports.

---

## Appendix — Evidence snapshot

- `place_order` definitions: ~30 across layers  
- `Instrument` class: 3 production homes  
- Exact duplicate pairs: aggregates, scanner models, OMS tests  
- Domain prod → infrastructure: 0  
- Domain → plugins: 4 (indicators)  
- Cross-layer import scan + graphify order/MD neighborhoods: 2026-07-09
