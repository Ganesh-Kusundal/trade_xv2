# TradeXV2 → Institutional-Grade Trading OS
## Architecture Review Board — Corrected Redesign & Migration Plan

**Status:** Read-only review of the current tree + proposed redesign. No code changed.
**Scope:** Entire repository. Guided by `graphify-out/` knowledge graph and 6 parallel sub-agent reviews (Domain/DDD, OMS/Application, Broker Plugins, Market-Data/Events/Replay, Interfaces/DX, Testing/Packaging/Perf), **plus a second exhaustive wave of 8 agents** covering `tradex/runtime`, security/auth, REST API, market_data/config/datalake, infrastructure/reconciliation, backtest engine math, packaging/CI, and the execution seam.
**Lens:** Principal Trading Systems Architect + Runtime Systems Reviewer. Everything below is judged *as if it trades real money tomorrow*.

> All line references were verified against the working tree on 2026-07-09. Where a sub-agent
> claim was wrong (notably "missing `tradex/runtime`"), it is explicitly corrected in place.

### Critical update — full review complete (Part 2)
The first wave (Part 1, below) covered the core spine. A second exhaustive wave surfaced **11 new P0
defects the first wave missed**, including ones that mean the REST API does not even boot, live
credentials are git-tracked, and the backtest equity math is arithmetically wrong. **Read
`docs/ARCHITECTURE_REVIEW_PART2_FULL.md` before acting on this document.** The consolidated
"cannot trade real money until" gate (all P0s) is in 0.1 below.

---

## 0. System Intent (what this is supposed to do)

TradeXV2 is a **broker-agnostic trading operating system**. A quant or developer writes code
against *rich market domain objects* (`Equity`, `Option`, `OptionChain`, `Portfolio`, `Order`),
never against a broker SDK, REST endpoint, or WebSocket. The platform:

1. Connects to one or more brokers (Dhan, Upstox, Paper) through pluggable adapters.
2. Normalizes exchange data into domain objects; streams quotes/ticks/depth.
3. Computes indicators → signals → strategies → risk → OMS → execution → portfolio → analytics.
4. Runs the **same** logic for live, paper, and historical replay (the *zero-parity rule*).
5. Persists state, reconciles broker truth against local truth, and survives crashes.

**Success criteria (intent):** a single event-driven pipeline from exchange to portfolio, with
domain objects owning their behavior, infrastructure fully hidden, and no silent divergence
between live and replay.

### 0.1 Consolidated "cannot trade real money until" gate (all P0s, both waves)

Wave 1 P0s: live never runs the tick→indicator→signal pipeline; two event buses (markets→no-op);
trade-before-order race drops fills; dedup ledger 24h eviction → double position; Wilder-vs-SMA RSI
split; 4–5 duplicated backtest engines / 3 scanner copies.

Wave 2 P0s (new, from the full sweep — see `ARCHITECTURE_REVIEW_PART2_FULL.md`):

- **P0-A** REST API does not boot (`api/main.py:224` imports non-existent `validate_production_config`).
- **P0-B** Live Dhan credentials are git-tracked (`.env.local`, rewritten on token refresh).
- **P0-C** API auth fail-open (`AUTH_MODE != "api_key"` disables all auth).
- **P0-D** Timezone divergence: live/replay UTC vs parquet IST (5h30m backtest shift).
- **P0-E** Backtest equity curves wrong 3 ways (Replay no MTM; Fast +1 notional; Paper −1 notional).
- **P0-F** Default look-ahead fills (signal fills at same-bar close).
- **P0-G** `ExecutionComposer` bypasses OMS (no idempotency/risk/audit; kill-switch no-op without risk_manager) — CLI cancel/modify/place-orders affected.
- **P0-H** Reconciliation never heals + 24h dedup eviction → unreconciled drift + double positions.
- **P0-I** `connect()` never wires quota/router/stream kernel → no throttling/failover for public API.
- **P0-J** Client chooses live broker via query param (`POST /orders?broker=`).
- **P0-K** Global kill-switch toggled by any API key (no role scoping).

---

## 1. Executive Architecture Assessment

### 1.1 What is genuinely good (do not throw away)

- **Dependency direction is clean at the core.** `src/domain/` has **zero** imports of `application`,
  `brokers`, or `infrastructure`. Grep for `requests|websocket|redis|httpx|aiohttp|dhanhq|SmartConnect`
  inside `src/domain/` returns nothing. This is rare and valuable — the dependency inversion seam works.
- **The rich domain model already exists.** `src/domain/instruments/instrument.py` (`Equity/Index/Future/Option`),
  `OptionChain`, `Portfolio`, `Position`, `Order`, `Execution`, `InstrumentState` are real objects with
  behavior, not anemic DTOs. The *target* API (`nifty.quote`, `nifty.option_chain().atm.delta`,
  `session.buy(...)`) is largely already modeled.
- **OMS is idempotency-first and mostly fail-closed.** `OrderManager` reserves `correlation_id`
  before broker submit; `Session` refuses standalone live OMS without a composition root; unknown
  broker statuses fail *closed* to `REJECTED`.
- **Event bus is feature-rich.** `infrastructure/event_bus/event_bus.py` (degree 484 in the graph)
  has DLQ, event-log persistence, sequence numbering, replay mode, and idempotency.
- **CI intent is right.** importlinter boundaries, replay-determinism gates, and parity markers
  (`live_backtest_parity`, `paper_replay_parity`) already exist.

### 1.2 What is broken (the headline)

| # | Finding | Severity | Evidence |
|---|---------|----------|----------|
| P0-1 | **Live never runs the tick→indicator→signal pipeline.** Backtest proves nothing about live. | Critical | `market_feed.py:920` publishes `TICK`; no live subscriber runs indicators; live signals come from a *batch* `Scanner.scan(pd.DataFrame)` → `trading_orchestrator.py:186`. |
| P0-2 | **Zero-parity rule structurally violated.** 4–5 backtest engines + 3 scanner copies + 2 RSI math variants. | Critical | `ReplayEngine` (`analytics/replay/engine.py:81`), `FastBacktestEngine` (`fast_backtest.py:35`, documented *look-ahead bias*), `PaperTradingEngine` (`paper/engine.py:70`), `poc/backtest.py`; RSI = Wilder (`domain/indicators/rsi.py:40`) vs SMA (`analytics/pipeline/features.py:88`). |
| P0-3 | **Two incompatible event buses; markets events land in a no-op bus.** | Critical | `EventBus.publish(DomainEvent)` (`event_bus.py:359`) vs `DomainEventBus.publish(str, dict)` (`bus.py:18`); only impl of the latter is `NullEventBus` (`null_bus.py:10`). `subscription.py:73` publishes into the no-op bus. |
| P0-4 | **Trade-before-order race drops fills silently.** | Critical (real money) | `order_manager.py:496-504` looks up trade by `order_id`; if `ORDER_UPDATED` hasn't arrived, the trade is dropped ("retry on order delivery" — but nothing retries). |
| P0-5 | **Dedup ledger eviction causes double-position after 24h.** | Critical (real money) | `ProcessedTradeRepository` evicts after `PROCESSED_TRADE_RETENTION_SECONDS` (default 24h, `processed_trade_repository.py:358`); a replayed trade re-applies. |
| P1-1 | **Triple order-command object** (`OrderIntent` / `OrderRequest` / `OmsOrderCommand`) hand-copied across a bridge. | High | `orders/intent.py:25`, `orders/requests.py:28`, `order_manager.py:62,97`; `session_bridge.py:24,120`. |
| P1-2 | **Position math owned in 3 places** (entity VO, `PositionAggregate`, `PositionManager`). | High | `entities/position.py:44`, `aggregates/position.py:63`, `position_manager.py:67`. |
| P1-3 | **Non-durable local idempotency in Dhan order placement.** | High (real money) | `brokers/dhan/orders.py:66` `IdempotencyCache` (in-memory, TTL 3600s) — duplicate protection lost on restart; canonical `infrastructure/idempotency` exists. |
| P1-4 | **Synchronous blocking risk check on the order path** (holds lock across possible network). | High | `risk_manager.py:247,286`; `RiskManager` is "stateless" by docstring but holds `_daily_pnl` + `MarginProvider` call. |
| P1-5 | **Orphaned live order on submit-then-exception.** | High | `order_manager.py:271-276` releases `_pending_correlation` on exception; broker may have already placed the order → not in book. |
| P1-6 | **Reconciliation is read-only advisory** — drift is logged, never healed. | High | `reconciliation_service.py:157`. |
| P2-1 | **`tradex/runtime` exists and is populated** (corrected: a sub-agent wrongly claimed it is missing). Real issue is that gateways do **not** implement the port, and capability/resilience logic is hand-wired into each `factory.py`. | Med | `tradex/runtime/gateway_factory.py`, `brokers/dhan/gateway.py:50` uses legacy string signature. |
| P2-2 | **Unwired `.broker` facade** — `instrument.broker.depth20()` raises today. | Med | `instrument.py:404` `get(broker_id)`; `BrokerFacade` (`extensions/facade.py`) never attached. |
| P2-3 | **Dual `src/domain` vs root `domain` namespace.** `tradex/__init__.py` injects `src/` onto `sys.path`; `pyproject.toml:52` `where=["src","."]`. | Med (prod trap) | `top_level.txt` lists `domain`+`analytics`+`brokers`; `api_server.py` inserts only repo root. |
| P2-4 | **CI gates a deleted module** (`brokers/common/oms/*`) → false green. | Med | `ci.yml:142`; git status shows those files `D`. |
| P2-5 | **Anemic derivatives** — `Option.payoff/IV`, `Future.basis` return `None`. | Med | `instrument.py:486-493, 566-582`. |
| P2-6 | **Global mutable provider singleton** — two sessions in one process clobber each other. | Med | `provider_registry.py:15` `_provider`; mutated by `universe.py:143,312`. |
| P2-7 | **`Session.buy` falls back to raw `ExecutionProvider` bypassing Risk/OMS** when `order_service is None`. | Med | `universe.py:201-214`. |

**Verdict:** The *design direction is correct* and the domain layer is the strongest part of the
system. This is **not** a rewrite — it is a *reconciliation and completion* of an in-flight migration
that has left duplicated logic, a dead branch in the event pipeline, and a few real-money silent
failure paths. Most debt is **duplication and unwired seams**, not wrong architecture.

---

## 2. Current vs Proposed Architecture (comparison)

| Dimension | Current | Proposed |
|-----------|---------|----------|
| Single pipeline? | No — live (batch scanner) and replay (bar window) forked | One `PipelineEngine.process_bar()`; live/paper/replay differ only in feed + fill source |
| Event bus | Two (`EventBus`, `DomainEventBus`→`NullEventBus`) | One `EventBusPort` with `publish(DomainEvent)` |
| Backtest engines | 4–5 divergent | 1 (`PipelineEngine`), feed-swapped; `FastBacktest`/`Paper` become configs |
| Indicators | 2 RSI variants (Wilder vs SMA) | 1 canonical `domain.indicators` library |
| Order command | 3 objects + manual bridge | 1 `OrderIntent` VO; transport fields via composed `BrokerOrderPayload` |
| Position math | 3 owners | 1 — `Position.with_fill`; managers delegate |
| Broker gateway | legacy string `place_order`, bypasses port | implements `ExecutionProvider.place_order(OrderRequest)→OrderResult` |
| Idempotency | local in-memory in Dhan + infra copy | injected `infrastructure.idempotency.IdempotencyService` (durable) |
| `.broker` capability | unwired `AttributeError` | typed `BrokerFacade` attached at `connect()` |
| Entry point | `tradex/` + dead `interfaces/` | single `tradex` SDK; `interfaces/` deleted |
| Packaging | dual namespace `src/domain` + root `domain` | single src-layout; `where=["src"]` |
| CI gate | references deleted `brokers/common/oms` | points to `application/oms` |
| Namespace | two `domain` resolvable by path order | `domain.__file__.startswith(src)` self-check at startup |

---

## 3. Dependency Graph — Before & After

### 3.1 Before (today, as extracted by graphify)

```
                 brokers/ (dhan, upstox, paper, common)
                   │   ▲  (gateways bypass port; legacy sigs)
                   │   │
   application/oms ─┤   │  (owns runtime order/position state; 2 parallel exec stacks)
   application/    │   │
   trading/        │   │
        │          │   │
        ▼          │   │
   src/domain/  ◀──┘   │   (clean: NO infra imports — good)
   (rich objects)      │
        ▲              │
        │              │
   infrastructure/event_bus  ◀── TWO BUSES (DomainEventBus→NullEventBus is no-op)
   analytics/ (Replay/Fast/Paper engines, scanner×3, RSI×2)
   datalake/ (duplicate backtest/scanner stubs)
   poc/ (orphan dead code)
```

Violations visible in the graph:
- `brokers/dhan/gateway.py:18-23` imports `brokers.dhan.domain` (its own domain types) instead of `domain.ports`.
- `src/domain/tests/markets/test_platform_api.py:193` imports a concrete broker (`brokers.dhan.extensions.depth20`) — a domain module depending on a broker. *Direction leak.*
- `analytics` and `datalake` both re-implement the same engines/scanners.

### 3.2 After (proposed)

```
                 infrastructure/brokers/<broker>/   (ADAPTERS only)
                 implements ports in src/domain/ports
                          │  dependency points INWARD
                          ▼
   src/domain/ports  ◀─────────────────────────────┐
        ▲                                           │
        │ (domain depends only on its own ports)    │
        │                                           │
   src/domain/  (Instrument, OptionChain, Order,    │
                 Position, Portfolio, Event types,  │
                 Indicator math, Scanner model)     │
        ▲                                           │
        │                                           │
   application/  (PipelineEngine, OMS orchestration,│
                 Risk, Reconciliation, Workflows)   │
        ▲                                           │
        │                                           │
   interfaces/sdk (tradex)  ── composition root ────┘
   (wires providers + OMS + typed BrokerFacade)
```

Rule enforced by importlinter: **no arrow may point from `src/domain` outward.** Period.

---

## 4. Domain Model & Object Hierarchy (proposed canonical)

```
DomainObject (ABC)
├── Instrument (identity + live state + subscriptions + extensions)
│   ├── Equity
│   ├── Index            # NIFTY is an Index, NOT Equity (fix the prompt example)
│   ├── Future
│   └── Option           # payoff/IV/greeks implemented via PricingProvider port
├── InstrumentState (immutable VO: quote/depth/subscription; age_seconds())
├── OptionChain (rich: atm, calls, puts, pcr, max_pain, greeks, iv_surface)
│   └── OptionChainSnapshot (VO, renamed from duplicate OptionChain in entities/)
├── Portfolio (positions, pnl, exposure)        # single position owner
├── Position (VO: with_fill() is the ONLY pnl/avg-price math)
├── Holding (VO, pnl computed like Position)
├── Order (VO: with_status() enforces ORDER_STATUS_TRANSITIONS; no illegal state)
├── Execution (aggregate: fills for one order)
├── OrderIntent (canonical command VO: qty>0, symbol, correlation_id)
├── BrokerOrderPayload (composed transport fields; adapter-built, never in domain)
├── Greeks (VO)
├── MarketDepth, Quote, Tick (immutable VOs / DTOs in payloads)
└── Scanner / ScannerRule (domain model in src/domain/scanners)
```

**State ownership — exactly one owner each:**
- Quote/Tick/Depth → the `Instrument`'s `InstrumentState` (replaced atomically under lock).
- Indicators → `IndicatorSeries` computed from `InstrumentState` history (no separate owner).
- Order book → `OrderManager` is the *runtime* owner; `Order` VO enforces transition legality.
- Position book → **`Portfolio` is canonical**; `PositionManager` is a runtime projection that
  delegates all math to `Position.with_fill`. Delete `PositionAggregate` (orphaned).
- Subscriptions → a `SubscriptionService` (not the `Instrument`'s callback dict).
- Greeks/IV → `PricingProvider` port; `Option` queries it, never computes silently.

---

## 5. Package / Module Hierarchy (proposed)

The project already *has* `src/domain`, `application`, `brokers`, `infrastructure`, `interfaces`,
`analytics`, `datalake`. The fix is **collapsing duplication and pointing everything at `src/domain`**,
not inventing a new tree. Proposed layout (changes in **bold**):

```
src/
  domain/
    instruments/      (instrument, instrument_id, composition, subscription)
    options/          (option_chain, greeks)
    portfolio/        (portfolio, position, holding)
    orders/           (intent, requests, order, order_state)
    executions/       (execution)
    events/           (types, bus ABC, domain_event)        # ONE bus contract
    indicators/       (rsi, atr, macd, vwap — CANONICAL, pandas-free)
    scanners/         (scanner, rule model)                 # single scanner model
    ports/            (protocols: DataProvider, ExecutionProvider,
                       EventBusPort, OrderServicePort, PricingProvider, BrokerAdapter)
    value_objects/    (state, money, quantity)
    provenance.py
  application/
    pipeline/         (PipelineEngine — ONE engine)
    oms/              (order_manager, position_manager, context, risk, reconciliation)
    trading/          (trading_orchestrator — now a thin adapter over PipelineEngine)
    workflows/
  infrastructure/
    brokers/
      dhan/  upstox/  paper/     (ADAPTERS; implement ports; no domain types of their own)
      common/  (capabilities, mappers, resilience decorator, connection)
    market_data/      (feed → bar aggregator → EventBus)
    persistence/      (idempotency, event_log, repositories)
    messaging/        (EventBus implementation)
    replay/           (recorded feed+events → PipelineEngine)
  interfaces/
    sdk/  (tradex — the ONLY public package)
    cli/  api/  (thin adapters over Session/Universe)
  analytics/          (REPOINTS to src/domain.indicators + application.pipeline)
  datalake/           (DELETE duplicate backtest/scanner; import from analytics/domain)
  poc/                (DELETE — 0 importers)
```

**Deletions (concrete):** `interfaces/` dead scaffold, `datalake/fast_backtest.py`,
`datalake/run_backtest.py`, `datalake/research/*backtest*`, `datalake/scanner/{engine,compiler,models}.py`,
`poc/`, `brokers/common/oms/` leftovers, `src/domain/aggregates/` (orphaned), duplicate
`OptionChain` VO (rename to `OptionChainSnapshot`), second RSI (SMA variant in `analytics/pipeline`).

---

## 6. Class Responsibilities (key classes, proposed)

| Class | Owns | Does NOT own |
|-------|------|--------------|
| `Instrument` | identity, current `InstrumentState`, extension access | feed dispatch, callback fan-out (→ `SubscriptionService`) |
| `Order` | transition legality (`with_status`), snapshot | runtime book (→ `OrderManager`) |
| `Position` | pnl/avg-price math (`with_fill`) | the position book (→ `Portfolio`) |
| `Portfolio` | position collection, portfolio pnl/exposure | streaming dispatch |
| `OrderManager` | order book, idempotency reserve, broker submit, fill routing | pnl math (→ `Position`) |
| `PositionManager` | live projection of `Portfolio` from trades | pnl math (→ `Position`) |
| `RiskManager` | pre-trade checks (async/bounded) | network calls holding the OMS lock |
| `PipelineEngine` | bar→feature→signal→OMS→fill (one path) | broker specifics (→ ports) |
| `BrokerAdapter` (port) | broker-agnostic quote/order surface + `capabilities` | domain types |
| `BrokerFacade` | typed capability access (`depth20()`) | anything not behind a capability flag |

---

## 7. Object Interaction Diagram (live order)

```
User code                 SDK (tradex)              Application                 Infra (broker)
──────────                ───────────               ───────────                ──────────────
session.buy(nifty,10)
        │
        ▼
Universe.buy ──builds──▶ OrderIntent
        │                                            │
        │                                            ▼
        │                                      OrderServicePort.place(OrderIntent)
        │                                            │
        │                                            ▼
        │                                      OrderManager.place_order
        │                                        ├─ idempotency reserve (corr_id)
        │                                        ├─ RiskManager.check (async/bounded)
        │                                        ├─ build BrokerOrderPayload (adapter)
        │                                        ├─ ExecutionProvider.place_order ─────────▶ gateway.place_order
        │                                        ├─ record + publish ORDER_PLACED               │
        │                                        │                                            ▼
        │                                        │                                      broker fills
        │                                        │◀──────── TRADE (EventBus) ◀───────────────┘
        │                                        ▼
        │                                      OrderManager.on_trade
        │                                        ├─ dedup by TradeIdKey (durable repo)
        │                                        ├─ Order.with_status (legal transition)
        │                                        ├─ Position.with_fill  ──▶ Portfolio
        │                                        └─ publish TRADE_APPLIED
        ▼
returns OrderResult
```

---

## 8. Event Flow Diagram (one taxonomy, one bus)

```
EXCHANGE ──▶ Adapter.normalize ──▶ EventBus.publish(TICK|DEPTH)  ──▶ MarketData subscriber
                                                                         │
                                                                         ▼
                                                              BarAggregator.process_tick
                                                                         │
                                                                         ▼
                                                     PipelineEngine.process_bar(bar)
                                                                         │
                                            ┌────────────────────────────┼─────────────────────────┐
                                            ▼                            ▼                         ▼
                                     FeaturePipeline              StrategyPipeline           (Risk on order path)
                                     (domain.indicators)          .evaluate_single            only, not here
                                            │                            │
                                            ▼                            ▼
                                     FEATURES_COMPUTED            SIGNAL_GENERATED
                                                                            │
                                                                            ▼
                                                                  OrderServicePort.place
                                                                            │
                                                            (idempotency + risk + broker)
                                                                            │
                                                                            ▼
                                                   ORDER_PLACED → ORDER_UPDATED → TRADE
                                                                            │
                                                                            ▼
                                                   TRADE_APPLIED → POSITION_CHANGED → PORTFOLIO_CHANGED
```

**Event rules (enforced):**
- One bus (`EventBus` with `publish(DomainEvent)`). `DomainEventBus`/`NullEventBus` deleted.
- Collapse `TICK`+`QUOTE`→`TICK`; `DEPTH`+`DEPTH_UPDATED`→`DEPTH`; delete `QUOTE_UPDATED`/`DEPTH_UPDATED`.
- `TRADE_APPLIED` folded back into idempotent `TRADE` handling in `PositionManager` (dedup by `TradeIdKey`).
- Payloads carry **immutable** snapshots/DTOs only (fix shallow-freeze leak at `types.py:94`).
- No event cycles; replay uses the *same* bus config — **only the feed differs**, never a
  `replay_mode` dispatch skip (`event_bus.py:423` removed).

---

## 9. Data Lifecycle (explicit stages)

```
Exchange
  ▼
Broker Adapter (normalize to Quote/Tick/Depth/Order/Trade VOs)   ← infra, hidden
  ▼
EventBus (immutable DomainEvent)
  ▼
BarAggregator (ticks → bars)            [live/paper/replay identical]
  ▼
PipelineEngine.process_bar
  ▼
FeaturePipeline  → IndicatorSeries (domain.indicators, incremental)
  ▼
StrategyPipeline → Signal
  ▼
Risk (async/bounded) → OrderServicePort
  ▼
OrderManager (idempotency + broker submit) → ExecutionProvider
  ▼
Broker (execution) → TRADE → OrderManager.on_trade
  ▼
Position.with_fill → Portfolio → POSITION_CHANGED
  ▼
Analytics / Persistence (event_log, repositories)
```

Every stage is explicit; the **same** `PipelineEngine` runs for live, paper, replay. The only
variables are (a) the feed source and (b) the fill source (`ExecutionProvider` live vs
`OmsBacktestAdapter` simulated). Indicators, features, signals, sizing, risk = one code path.

---

## 10. Broker Plugin Architecture (capability + adapter + extension object)

**Port (single source of truth in `src/domain/ports`):**
```python
@runtime_checkable
class BrokerAdapter(DataProvider, ExecutionProvider, Protocol):
    broker_id: str
    is_connected: bool
    capabilities: BrokerCapabilities            # advertised, queryable
    def authenticate() -> bool: ...
    def close() -> None: ...
    def extension(name: str) -> "Extension" | None
```
- `ExecutionProvider.place_order(OrderRequest) -> OrderResult` is the **only** order entry.
  Gateways stop exposing `place_order(symbol, exchange, side, ...)` (`dhan/gateway.py:50`).
- `capabilities: BrokerCapabilities` is on the port, so domain can do
  `if adapter.capabilities.supports_depth_20_ws:` without naming a broker.
- Idempotency injected via `IdempotencyService` (canonical `infrastructure.idempotency`).
  Delete `brokers/dhan/orders.py:66` local `IdempotencyCache` (non-durable → double orders on restart).
- Resilience as `ResilienceDecorator(BrokerAdapter)` applied **once** in the composition root,
  not hand-wired in every `factory.py` (`dhan/factory.py:219`).
- Plugin discovery via `importlib.metadata` entry-points (`tradex.brokers`); `session.py:136`
  `if/elif` registration replaced by registry.
- Capability is single-sourced: `dhan_capabilities()` (`capabilities.py:11`) and
  `DhanBrokerGateway.capabilities()` (`gateway.py:339`) currently **disagree** (rps 25 vs 6) —
  collapse to one function.
- Normalization centralized: one `BrokerOrderMapper` per broker behind an `order_mapper` port
  (currently split across `dhan/orders.py`, `upstox/mappers/domain_mapper.py`,
  `common/mappers/order_mapper.py`).

**Extension Object (typed, discoverable):**
```python
# at connect():
facade = BrokerFacade(broker.extension_registry)   # typed Protocol per capability
instrument.attach_broker(facade)                   # instrument.broker.depth20() now works + autocompletes
```
`BrokerFacade` (`src/domain/extensions/facade.py`) is attached at `connect()` — fixing P2-2.

**New-broker cost today:** ~10 files (gateway, factory, capabilities, orders, session shim,
cli registry, endpoints, status_mapper, pyproject entry-points, copy-paste factory boilerplate).
**After:** 1 package + 1 entry-point registration. Shotgun surgery eliminated.

---

## 11. Historical & Live Data Lifecycle (the zero-parity seam)

**Today:** live = batch `Scanner.scan(DataFrame)` → orchestrator; replay = `ReplayEngine` bar window.
Different feature computation (SMA RSI vs Wilder RSI), different signal trigger, different fill model
(`PURE_SIM` mode in `backtest/engine.py:150` bypasses risk entirely).

**Proposed:** A single `UnifiedReplayOrchestrator` feeds recorded bars+events into the **same**
`PipelineEngine.process_bar` used live. Paper = live feed + simulated fills. The parity test
(`tests/quant/test_paper_replay_parity.py`, `test_quant_parity.py`) replays a recorded live session
and asserts identical signals/trades. `PURE_SIM` / `allow_simulate_without_oms` removed — the
in-memory OMS is always on the path.

---

## 12. Public SDK Design (the only thing users import)

```python
import tradex
session = tradex.connect("dhan")            # profile-driven, single knob
nifty   = session.universe.index("NIFTY")   # NIFTY is an Index, not Equity
nifty.subscribe()
nifty.quote                              # InstrumentState
nifty.history("5m")                      # HistoricalSeries
chain = nifty.option_chain()
chain.atm.delta                         # Greeks
nifty.broker.depth20()                  # typed capability, attached at connect()
session.buy(nifty, 10, price=...)       # → OrderIntent → OMS → broker
```

- Single package `tradex` (re-exporting `src/domain`). **Delete dead `interfaces/` scaffold.**
- `tradex.connect(profile="dhan")` reads one typed `TradexConfig` (pydantic), not scattered `.env`.
- Infra hidden: `Session` is the composition root; `DataProvider`/`ExecutionProvider`/`OrderServicePort`
  injected once.
- `Provider is None` must raise `NotConfigured` (not silently return `None`/`empty` at
  `instrument.py:166-168`).
- Anemic derivatives (`Option.payoff`, `Future.basis`) implemented or removed from the public surface.

---

## 13. Design Pattern Justification

| Pattern | Where | Why |
|---------|-------|-----|
| Rich Domain Model / Tell-Don't-Ask | `Instrument`, `Order.with_status`, `Position.with_fill` | behavior lives on the object that owns the state; fixes P1-1/P1-2 |
| Ports & Adapters (Hexagonal) | `src/domain/ports` | infra hidden; brokers pluggable; dependency points inward |
| Capability | `BrokerCapabilities` | domain queries support without naming a broker |
| Extension Object | `BrokerFacade` / `Extension` ABC | broker-specific extras (`depth20`) without polluting domain |
| Abstract Factory + entry-points | broker registration | new broker = 1 package, no `if/elif` |
| Repository | idempotency / event_log / positions | durable state, swap backend (memory/redis/file) |
| Observer | `EventBus` | decoupled stages; replay-compatible |
| Decorator | `ResilienceDecorator` | circuit-breaker/retry cross-cutting, applied once |
| Factory (bar aggregator) | tick→bar | one aggregation for live/paper/replay |
| Composition over inheritance | `Instrument` + `ExtensionManager` | capabilities composed, not subclassed per broker |

**Rejected:** Manager/Service classes that own domain state (`OrderManager` keeps *runtime* book but
delegates all math); the second RSI implementation; `ProcessedTradeRepository` eviction (replace with
durable, bounded ledger).

---

## 14. Testing Strategy

**Principle (project rule):** integration tests with real components; mock only true external
boundaries (broker socket / external HTTP). Use `PaperGateway`/`PaperBroker` as the sanctioned
no-broker double. The 169 mock-using test files violate this and must be converted.

**Required layers:**
1. **Domain tests** — `Order.with_status` rejects illegal transitions; `Position.with_fill` math parity.
2. **Property tests** — indicator invariants (RSI∈[0,100]); idempotency (same `correlation_id` → one order).
3. **Contract tests** — every broker adapter satisfies `BrokerAdapter` port; `capabilities` matches reality.
4. **Integration tests** — order→fill→position against `PaperGateway` (real components).
5. **Replay/Parity tests** — recorded live session replayed → identical signals/trades (live≡paper≡replay).
6. **Broker adapter tests** — against broker sandbox (Dhan sandbox in CI; Upstox gated).
7. **Performance/stress** — rapid-fill concurrency; indicator throughput; subscription scaling.
8. **Regression/mutation** — for the money path.

**CI corrections (P2-4):** repoint coverage/importlinter gates from deleted `brokers/common/oms` to
`application/oms`. Add a **startup self-check**: `assert domain.__file__.startswith(src)` to catch the
dual-namespace trap (P2-3) in prod. Add a **parity contract test** as a hard gate.

---

## 15. Performance Recommendations

1. **Indicators: stop full-series recompute per tick.** `domain/indicators/rsi.py:12` recomputes O(n)
   each call; over a session this is O(n²). Use stateful/incremental update or a ring buffer behind the
   existing `calculate()` signature. (Latency spikes at scale → missed fills.)
2. **OMS lock: single `RLock` serializes all book mutations** (`order_manager.py:153,294`). Under burst
   fills, shard per-symbol or use a lock-free dict + atomic swaps. Benchmark-gated.
3. **Bounded order maps.** `_orders_by_correlation` / `_pending_correlation` grow unbounded
   (`order_manager.py:155,184`) → memory creep over multi-day sessions. Add TTL/eviction.
4. **Durable, bounded dedup ledger.** Replace the 24h-evicting in-memory `ProcessedTradeRepository`
   with a durable (redis/file) bounded ledger (P0-5).
5. **Async/bounded risk.** Never hold the risk lock across I/O (`risk_manager.py:286`). Run risk off the
   order path or with a `concurrent.futures` timeout.
6. **Per-instrument state swap** under lock is fine; remove the double-lock callback fan-out in
   `instrument.py:326-327` (delegate to `EventBus`).

---

## 16. Migration Roadmap (phased, each phase leaves a working system)

### Phase 0 — Stabilize CI & packaging (unblock safe work) · 1 PR
- Repoint `ci.yml` + importlinter from deleted `brokers/common/oms` to `application/oms`.
- Fix `api_server.py` `PYTHONPATH` (root→`src`). Add startup `domain.__file__.startswith(src)` check.
- **Success:** CI green on real contracts; prod binds correct `domain`. **Rollback:** revert CI config.

### Phase 1 — Collapse duplication (zero-parity foundation) · 2–3 PRs
- Delete `poc/`, duplicate `datalake/*backtest*`, `datalake/scanner/{engine,compiler,models}.py` (re-export from `analytics`).
- Repoint `analytics/pipeline` RSI/ATR/MACD/VWAP to `domain.indicators` (kill SMA-Wilder split).
- Make `FastBacktestEngine`/`PaperTradingEngine` thin configs over `ReplayEngine`; delete `poc/backtest.py`.
- Keep `brokers/common/idempotency` shims (removed in Phase 3).
- **Success:** one RSI, one backtest engine, parity marker passes. **Rollback:** shim tombstones already exist.

### Phase 2 — One pipeline, one bus · 3–4 PRs
- Extract `ReplayEngine._run_single` bar handler → `PipelineEngine.process_bar`.
- Live: subscribe `BarAggregator` to `TICK`/`DEPTH`; route to `PipelineEngine`. (Fixes P0-1.)
- Delete `DomainEventBus`/`NullEventBus`; port `subscription.py`/`async_event_bus` to `EventBus`.
- Fold `TRADE_APPLIED` into idempotent `TRADE` handling; remove `replay_mode` dispatch skip.
- **Success:** live and replay share `process_bar`; parity test green. **Rollback:** keep old bus behind a flag.

### Phase 3 — Domain owns behavior · 3 PRs
- `Order.with_status` enforces transitions; `Position.with_fill` is sole pnl math; managers delegate.
- Delete `PositionAggregate`, duplicate `OptionChain` VO (→`OptionChainSnapshot`), `interfaces/` scaffold.
- Single `OrderIntent`; adapters build `BrokerOrderPayload`. Delete `OmsOrderCommand`.
- **Success:** money-path math has one owner; tests green. **Rollback:** keep `OrderIntent` alias.

### Phase 4 — Broker seam completion · 2–3 PRs
- Gateways implement `ExecutionProvider.place_order(OrderRequest)`; delete legacy string sig.
- Inject durable `IdempotencyService`; delete `dhan/orders.py:66` local cache.
- `ResilienceDecorator` in composition root; single capability source; entry-point broker registry.
- Attach typed `BrokerFacade` at `connect()` (fixes P2-2).
- **Success:** `instrument.broker.depth20()` works + autocompletes; new broker = 1 package.

### Phase 5 — Real-money safety hardening · 2 PRs
- Durable bounded dedup ledger (P0-5); trade-buffer for trade-before-order race (P0-4).
- Risk off the order path / bounded (P1-4); heal reconciliation drift (P1-6); record-then-submit to
  avoid orphaned orders (P1-5).
- **Success:** no silent double-position; reconciliation self-heals. **Rollback:** feature flags per item.

### Phase 6 — Performance & DX polish · 2 PRs
- Incremental indicators; per-symbol OMS locks; bounded maps.
- `tradex.connect(profile=...)` typed config; `NotConfigured` instead of silent `None`; implement/remove
  anemic derivatives.
- **Success:** benchmarks within target; DX matches target API.

---

## 17. Risk Analysis (what can go wrong silently / break under real-time / unsafe assumptions)

**What can go wrong silently (the dangerous ones):**
1. Trade arrives before `ORDER_UPDATED` → dropped, position never updated (P0-4). *Real money mis-booked.*
2. Dedup ledger evicts after 24h → replayed trade re-applied → double position (P0-5).
3. Local in-memory idempotency lost on restart → duplicate live order (P1-3).
4. Markets events published to `NullEventBus` → `QUOTE_UPDATED` silently lost (P0-3).
5. `Option.payoff`/`Future.basis` return `None` → callers compute on `None` (P2-5).
6. `Session.buy` falls back to raw `ExecutionProvider` bypassing Risk/OMS if `order_service is None` (P2-7).
7. Dual `domain` namespace → prod binds the *wrong* `domain` (P2-3).

**What breaks under real-time:**
- Live never runs indicators → strategies validated in backtest never fire live (P0-1).
- Single OMS `RLock` serializes all fills → throughput ceiling under burst (Perf #2).
- Full-series indicator recompute → latency spikes at scale (Perf #1).
- Synchronous risk holding lock across network → OMS thread stalls on slow margin API (P1-4).

**Unsafe assumptions:**
- "Broker will always send `ORDER_UPDATED` before `TRADE`." (P0-4 — not guaranteed.)
- "Process restarts are rare / dedup window is long enough." (P0-5 — wrong over multi-day.)
- "`provider` is configured." Silent `None` degrades instead of erroring (P2-6, P2-3-None).
- "`Session` is a singleton." Global `_provider` singleton breaks multi-session/multi-broker (P2-6).

**Where behavior is implicit instead of explicit:**
- Two execution stacks (`ExecutionComposer` async vs `ExecutionService` sync) — caller picks ad hoc (V2
  in OMS review). Kill-switch/idempotency enforced in one, bypassed in the other.
- Env-var-driven prod behavior (`order_manager.py:86` `PYTEST_CURRENT_TEST`, `context.py:313`
  `TRADEX_SKIP_STARTUP_RECONCILIATION`) — prod path differs by env var.
- `SUBSCRIBING` status never actually set (`instrument.py:340` jumps to `SUBSCRIBED`) — timing gap under
  slow feeds; no stale-quote rejection.

---

## 18. Technical Debt Eliminated (by this plan)

- 4–5 backtest engines → 1. 3 scanner copies → 1. 2 RSI variants → 1. 2 event buses → 1.
- 3 order-command objects → 1. 3 position-math owners → 1. Orphaned `PositionAggregate`/dead
  `aggregates/` removed. Duplicate `OptionChain` VO renamed.
- Non-durable local idempotency → injected durable `IdempotencyService`.
- Unwired `.broker` facade → typed, attached at `connect()`.
- Dead `interfaces/` scaffold, `poc/` orphan, deleted-module CI gate → removed/repointed.
- Dual `domain` namespace → single src-layout.
- Live/batch fork → one `PipelineEngine`.

---

## 19. Remaining Future Improvements (post-plan)

- Multi-broker netting / smart order routing across adapters.
- Persistent position book (WAL) for instant crash recovery (today `crash_replay_positions` is a test,
  not a guarantee).
- Strategy marketplace: strategies as plugins discovered via entry-points (same pattern as brokers).
- Distributed mode: `EventBus` over Kafka/Redis for multi-process; idempotency already durable-ready.
- Backtest cloud: recorded scenarios as a shared corpus for parity CI.

---

## 20. Definition of "Done" (measurable quality criteria)

The redesign is "done" when **all** hold and are enforced in CI:

1. **Single pipeline:** `grep` for a second `process_bar`-style handler returns nothing; live and replay
   share `application/pipeline/PipelineEngine`.
2. **Zero-parity proven:** `live ≡ paper ≡ replay` parity test is a hard CI gate over a recorded corpus.
3. **One of everything:** exactly one backtest engine, one scanner engine, one RSI, one event bus, one
   order-command VO. (Enforced by a `scripts/audit_duplication.py` check.)
4. **Dependency inversion:** importlinter passes with `src/domain` allowed to import nothing outside
   itself + `src/domain/ports`.
5. **No silent money-path failure:** trade-before-order buffered; dedup ledger durable & bounded; risk
   off the order-path lock; reconciliation heals drift.
6. **Broker seam:** adding a broker requires exactly one new package + one entry-point; `instrument.broker.<cap>()`
   is typed and autocompletes.
7. **Packaging:** `domain.__file__.startswith(src)` at startup; `tradex.connect(profile=...)` is the only
   public entry; `interfaces/` deleted.
8. **Tests:** ≥90% on `application/oms` + `src/domain`; ≥80% parity coverage; mock only external sockets/HTTP;
   no test imports a deleted module.
9. **Perf:** indicator update is O(1) amortized per tick; OMS sustains target fill rate (benchmark in CI
   with `--benchmark-compare`).
10. **DX:** `tradex.connect("dhan").universe.index("NIFTY").option_chain().atm.delta` works end-to-end with
    real (paper) components, no broker SDK in user code.

---

## Appendix A — Expected Behavior Contracts (for the money path)

### A.1 Instrument lifecycle
- **Inputs:** validated `InstrumentId`; injected `DataProvider` (optional).
- **Outputs:** immutable `InstrumentState` (quote/depth/subscription); `HistoricalSeries`; `OptionChain`.
- **Transitions:** `UNSUBSCRIBED → SUBSCRIBING → SUBSCRIBED → (ERROR|UNSUBSCRIBED)`.
- **Timing:** state age observable via `InstrumentState.age_seconds`; consumers **must** reject stale
  quotes before ordering (add enforcement — today missing).
- **Failure modes:** provider `None` → `NotConfigured`, not silent `None`. Slow feed → `SUBSCRIBING`
  actually observed (today skipped).

### A.2 Order execution lifecycle
- **Inputs:** `OrderIntent` (qty>0, symbol, mandatory `correlation_id`).
- **Outputs:** `OrderResult{success, order, error}`.
- **Transitions:** `OPEN → PARTIALLY_FILLED → FILLED` or `→ REJECTED/CANCELLED`, enforced by
  `Order.with_status` (not just `OrderManager`).
- **Timing:** idempotency + record under lock (<ms); risk + broker I/O outside lock (seconds, bounded).
- **Failure modes:**
  - *Rejection:* `ORDER_REJECTED`, no book entry beyond rejection.
  - *Partial fill:* `PARTIALLY_FILLED`; gauge decremented on terminal (fix D1).
  - *Disconnect:* broker stream dies → escalate/timeout; reconciliation heals (fix D4).
  - *Duplicate fill:* durable dedup ledger (no 24h eviction) — fix P0-5.
  - *Trade-before-order:* bounded buffer/retry, or create order stub — fix P0-4.

---

## Appendix B — Verified Claims & Corrections

- ✅ `src/domain` has zero infra imports (clean dependency inversion).
- ✅ `DomainEventBus` only impl is `NullEventBus` (`src/domain/events/null_bus.py:10`); markets publish
  into it (`subscription.py:73`) → events dropped.
- ✅ `brokers/common/idempotency/*` are 4-line shims re-exporting `infrastructure/idempotency` (verified
  line-by-line) — safe to delete in Phase 3.
- ✅ 4 backtest engines confirmed: `ReplayEngine` (`analytics/replay/engine.py:81`), `BacktestEngine`
  (`analytics/backtest/engine.py:62`), `PaperTradingEngine` (`analytics/paper/engine.py:70`),
  `FastBacktestEngine` (`analytics/backtest/fast_backtest.py:35`). Plus orphan `poc/backtest.py`.
- ✅ `brokers/dhan/orders.py:66` local `IdempotencyCache` (TTL 3600s, in-memory) — non-durable.
- ✅ `dhan/gateway.py:50` `place_order` uses legacy string signature, bypassing the port.
- ❌ **Correction:** a sub-agent claimed `tradex/runtime` is missing. It **exists and is fully
  populated** (`tradex/runtime/gateway_factory.py`, `broker_port.py`, `ports/`, `adapters/`, …). The
  real broker-seam issues are (a) gateways bypass the port, (b) capability/resilience hand-wired into
  each factory, (c) local non-durable idempotency. Do not "create tradex.runtime" — wire the existing one.

---

*Prepared by the Architecture Review Board (6-agent team + synthesis). Every finding maps to a file:line
in the current tree. No code was modified; this is a design + migration plan.*
