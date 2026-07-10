# TradeXV2 Production Architecture Board Review

**Date:** 2026-07-10  
**Method:** Code-only review (documentation deliberately ignored as source of truth)  
**Corpus:** ~1,800 production Python modules, ~274k LOC incl. tests; primary packages ~212k LOC  
**Assumption:** Platform will manage real capital under broker failures, network partitions, and multi-strategy expansion  

**Virtual review board:** Principal SWE · Staff Architect · Quant Trading Architect · Low-Latency Systems · Event-Driven Expert · Distributed Systems · SRE · QA/Test Architect · Security Architect · Data Platform Architect · Frontend Architect · DevOps/Cloud · Performance Engineering  

---

## 1. Executive Summary

TradeXV2 is a **serious, single-node, single-operator quantitative trading stack** with unusually strong intent: hexagonal ports, OMS idempotency, kill switch, loss circuit breaker hooks, chaos/e2e suites, import-linter contracts, and dual-broker (Dhan/Upstox) adapters with real reconnect/rate-limit work.

It is **not production-grade for unsupervised live capital**.

The architecture *reads* like an event-sourced, multi-strategy institutional platform. The implementation is closer to:

- **In-process pub/sub** with a best-effort JSONL journal  
- **Mutable OMS dictionaries** as system of record  
- **Multiple competing abstraction layers** (gateway duck-typing + DataProvider/ExecutionProvider + SPI + tradex.runtime)  
- **Research-grade paper/backtest** that will false-green strategies  

### Headline verdict

| Question | Answer |
|----------|--------|
| Can it place/cancel orders through Dhan/Upstox? | Yes, with material parity gaps |
| Can it safely auto-trade overnight unsupervised? | **No** |
| Is crash recovery trustworthy? | **No** (P0 serialize/store/ledger gaps) |
| Is risk management production-grade? | **No** (dead daily-PnL feed, market notional hole, phantom capital) |
| Multi-strategy portfolio? | **Shell only** |
| Multi-instance / HA API? | **Not designed** |
| Production deploy model? | **Missing** (no Docker/k8s) |

### Production Readiness Score: **4.6 / 10**

**Recommendation:** Freeze feature sprawl. Close P0 capital-safety and recovery gaps before any live auto-execution. Treat current system as **research + supervised paper + carefully gated manual live**, not institutional auto-trade.

---

## 2. Architecture Review Report

### 2.1 Observed topology (from code + package layout)

```
Presentation:   api/ (FastAPI)  ·  cli/ (Textual TUI + argparse)
Application:    application/{oms,execution,trading,composer,streaming,data}
Domain:         src/domain/  (importable as `domain` via pythonpath=["src","."])
Infrastructure: infrastructure/  +  tradex/runtime/ (partially duplicated)
Adapters:       brokers/{dhan,upstox,paper,common}
Capabilities:   analytics/  ·  datalake/  ·  config/
Composition:    runtime/, tradex/session.py, cli/services, api lifecycle
```

**Hybrid layout is intentional but incomplete:** only `domain` lives under `src/`; other layers are root packages. Dual package roots (`src` + `.`) increase import confusion and allow shadowing risks (import-linter even warns about PYTHONPATH).

### 2.2 Bounded contexts (as-is)

| Context | Location | Cohesion | Notes |
|---------|----------|----------|-------|
| Domain trading core | `src/domain` | Medium-High | Entities, ports, instruments; some god modules |
| OMS / risk | `application/oms` | High intent | Still façade gods (OrderManager, TradingContext) |
| Broker transport | `brokers/*` | Low cohesion | Largest surface (~66k LOC); uneven maturity |
| Platform kernel | `tradex/runtime` + `infrastructure` | Low | **Duplicated resilience packages** |
| Analytics / scanners | `analytics` | Medium | Scanner→strategy path real; paper engine forked |
| Data lake | `datalake` | Medium | Research-quality; local DuckDB/Parquet |
| API / CLI | `api`, `cli` | Medium | CLI is primary UI; no web frontend in tree |

### 2.3 Architectural strengths

1. **Domain independence contract** (`import-linter`: domain forbidden from brokers/infra/application) — largely held in production code.  
2. **OMS single-writer intent**: process registry (`application/oms/process_context.py`), correlation_id required, trade ledger design.  
3. **TRADE → TRADE_APPLIED separation**: positions only after OMS accepts trade — correct live double-fill defense.  
4. **Capability-oriented broker design** (partial): ports for DataProvider/ExecutionProvider/MarginProvider.  
5. **Operational hooks exist**: health, metrics, DLQ, lifecycle manager, kill switch API.  
6. **Test investment is real**: ~600 test files, chaos/, e2e/, quant/, stress/.

### 2.4 Architectural failures (board consensus)

#### A. Abstraction sprawl without convergence

Three+ order placement surfaces coexist:

1. Flat `*BrokerGateway.place_order(symbol=...)`  
2. `ExecutionProvider` / `OrderTransportPort`  
3. `OrderManager.place_order` + `submit_fn`  
4. `ExtendedOrderService` (super/forever/GTT) — **bypasses full risk**  
5. Composer / `ExecutionService` / `TradingOrchestrator` entry paths  

**Staff Architect:** Migration is incomplete; drift is structural, not incidental.

#### B. Dual runtime / dual resilience

`infrastructure/resilience/*` and `tradex/runtime/resilience/*` both exist; brokers (esp. Upstox/Dhan) import **tradex.runtime.resilience**. This splits the operational kernel and blocks single SRE ownership of circuit breakers/rate limits.

#### C. Pseudo event-driven / pseudo CQRS

- Mutable in-memory aggregates are system of record.  
- JSONL event log is optional audit, not rebuild authority.  
- No transactional outbox, no distributed bus, no schema evolution.  
- Analytics “replay” ≠ OMS crash recovery (same word, different systems).

#### D. Single-process hard assumption

Documented and coded: one OMS writer per SQLite store; in-process rate limits; process-local EventBus. **There is no multi-replica trading API design.** Scaling out API instances without sticky external OMS will corrupt state.

#### E. Dead durable order store

`OrderManager` accepts `order_store` and only assigns `self._order_store` — **never upserts or hydrates**. `SqliteOrderStore` + writer-lock tests exist; production path does not use them. False confidence in “durable OMS.”

### 2.5 Dependency direction issues

| Edge | Severity |
|------|----------|
| Brokers → `tradex.runtime` | High coupling |
| Paper → `application.oms` paths | Layer inversion risk |
| Application composer → tradex.runtime (import-linter ignores) | Acknowledged leak |
| Domain risk policy **not wired** to app RiskManager | Dual models |

### 2.6 Recommended target architecture (superior alternative)

```
┌─────────────────────────────────────────────────────────┐
│  CLI / API / TUI  (presentation only; no OMS logic)     │
└───────────────────────────┬─────────────────────────────┘
                            │ commands/queries
┌───────────────────────────▼─────────────────────────────┐
│  Application services (one command path per use case)   │
│  PlaceOrder · Modify · Cancel · Reconcile · SquareOff   │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  Domain: Instrument, Order, Position, RiskPolicy        │
│  Ports only: Execution, MarketData, Margin, Clock       │
└───────────────────────────┬─────────────────────────────┘
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
   Broker adapters    Persistence       Market data
   (thin mappers)     (orders+trades    (WS + lake)
                      + event log)
```

**Rules:**

1. One composition root per process; one OMS.  
2. One resilience library (delete the other).  
3. One risk engine (delete domain orphan or make it the only gate).  
4. Durable store is SoR for orders; event log is audit + rebuild aid.  
5. Paper fills go through same OMS cancel/modify state machine as live.

---

## 3. Quant Platform Review Report

### 3.1 Capability matrix

| Capability | Status | Evidence |
|------------|--------|----------|
| Multi-strategy execution | **Shell** | `MultiStrategyRuntime` builds pipeline only (~46 lines); no capital partitions |
| Multi-broker execution | **Partial** | Dhan/Upstox/Paper; parity gaps (get_order, modify, slice) |
| Scanner development | **Present** | `analytics/scanner/*` |
| Signal generation | **Present** | `StrategyPipeline` + builtins |
| Scanner→OMS path | **Present** | `TradingOrchestrator` |
| Portfolio management | **Weak** | Positions exist; no multi-strategy book / attribution |
| Risk management | **Broken for live** | Gates coded; daily PnL never fed; market notional understated |
| Position sizing | **Partial** | `domain.execution.sizing` used by orchestrator |
| Order routing | **Partial** | Composer/router in tradex.runtime; smart routing flag-gated |
| Event replay (OMS) | **Untrustworthy** | Deserialize/store/ledger P0s |
| Backtesting | **Present** | `analytics/replay`, walk_forward |
| Walk-forward | **Present** | `analytics/walk_forward` |
| Paper trading | **False-green risk** | Instant fills; random history; no stream |
| Live trading | **Manual/supervised only** | Gates exist; recovery/risk not safe for unsupervised |
| Performance analytics | **Partial** | Views, reports; PnL missing fees/multipliers |

### 3.2 Critical quant design flaws

#### Q1 — Daily loss / loss CB inert (P0)

`RiskManager.update_daily_pnl` has **no production callers**. Only definition + comments in `_internal/risk_manager.py`. Daily loss % and rolling loss circuit breaker never observe live fills/MTM.

#### Q2 — Market order notional hole (P0)

```python
notional = Decimal(order.quantity) * order.price if order.price > 0 else Decimal(order.quantity)
```

MARKET orders with `price=0` → notional ≈ share count → position/gross checks effectively disabled.

#### Q3 — Phantom capital default (P0)

`TradingContext` defaults `capital_fn` to `PHANTOM_CAPITAL_INR` (₹1,000,000). Mis-wired live contexts size risk against fiction.

#### Q4 — Position PnL ignores contract multiplier (P0)

`Position.with_fill` / `with_ltp` use linear `qty * (price - avg)`. Options/futures lot multipliers not applied → **PnL and risk understated by lot size** (often 15–75× on Indian index options).

#### Q5 — Extended orders bypass risk (P0)

`ExtendedOrderService` only checks kill switch, not concentration/margin/daily loss.

#### Q6 — Paper is not a sim exchange (P0)

`PaperGateway.history` random walk; streams stubbed; instant full fills; synthetic chains. Using paper as pre-prod F&O validation will greenlight broken strategies.

#### Q7 — Mode parity gaps (P1)

Backtest cancel/modify stubs; costs centralized in `domain.trading_costs` but live OMS PnL ignores fees; composer vs ExecutionService concurrency models differ.

#### Q8 — Multi-strategy double-fire (P1)

Orchestrator executes all actionable signals for a candidate; no netting / per-strategy budget.

### 3.3 Quant readiness score: **4.0 / 10**

Suitable for research, scanner prototyping, and carefully supervised single-strategy paper. Unsuitable for multi-strategy live capital without P0 closure.

---

## 4. Event-Driven Design Review

### 4.1 What works

- Frozen `DomainEvent` + timezone-aware timestamps  
- EventType catalogue + optional payload contracts  
- Handler isolation + metrics + DLQ capture  
- Persist-before-dispatch **intent** on EventBus  
- TRADE_APPLIED as downstream of OMS ledger  

### 4.2 What fails for production recovery

| ID | Severity | Finding |
|----|----------|---------|
| E1 | P0 | `SqliteOrderStore` never written/read by OMS |
| E2 | P0 | Trade ledger **mark-before-position-apply** → crash = ledger advanced, position missing; restart skips re-apply |
| E3 | P0 | Cold-start domain type registry for JSONL deserialization is empty until serialize runs in-process |
| E4 | P0 | `BufferedEventLog` buffers 100 events / 1s; bus never forces `sync_mode` for TRADE/ORDER; missing `event_id` in buffered records |
| E5 | P0 | `AsyncEventBus` critical set omits `TRADE` and `ORDER_UPDATED` (can drop) |
| E6 | P1 | DLQ has no redrive; persistent DLQ stores thin metadata, not full payloads |
| E7 | P1 | Bus marks event_id processed before handlers succeed |
| E8 | P1 | Recovery only replays ORDER_UPDATED + TRADE; ORDER_PLACED/CANCELLED excluded |

### 4.3 CQRS/ES verdict

**Pseudo.** Mutable books + optional journal. Do not claim event sourcing until:

1. Closed-world codecs for Order/Trade  
2. Store write-on-mutation + hydrate-before-trade  
3. Apply-then-mark or snapshot checkpoints  
4. Forced fsync for capital events  
5. Multi-process cold-start chaos tests  

### 4.4 Event design score: **4.5 / 10**

---

## 5. Code Smell Report

### 5.1 God classes / modules (static analysis)

| File | Symbol | Signal |
|------|--------|--------|
| `brokers/dhan/websocket/market_feed.py` | DhanMarketFeed | 34 methods, ~953 mloc |
| `analytics/views/manager.py` | ViewManager | 39 methods |
| `brokers/dhan/data/depth_feed_base.py` | BinaryDepthFeed | 29 methods |
| `brokers/upstox/auth/token_manager.py` | UpstoxTokenManager | 36 methods |
| `analytics/replay/engine.py` | ReplayEngine | ~740 mloc |
| `src/domain/instruments/instrument.py` | multi-class file | 824 LOC |
| `application/oms/context.py` | TradingContext | composition + recon + replay + lifecycle |
| `application/oms/order_manager.py` | OrderManager | graph hub; place/cancel/modify/trade façade |
| `src/domain/capability_manifest.py` | — | 1280 LOC |
| `brokers/upstox/mappers/domain_mapper.py` | UpstoxDomainMapper | 35 methods |

### 5.2 Structural smells

| Smell | Location | Severity | Recommendation |
|-------|----------|----------|----------------|
| Dual resilience | `infrastructure/resilience` vs `tradex/runtime/resilience` | Critical | Delete one; re-export shim |
| Dual paper engines | `analytics/paper` + `brokers/paper` | High | One sim path through OMS |
| Dual indicators | `src/domain/indicators` + `analytics/indicators` | Medium | Domain pure math; analytics orchestration only |
| Orphan domain risk | `src/domain/risk/policy.py` unused by OMS | High | Wire or delete |
| Dead order_store field | `OrderManager._order_store` | Critical | Wire or remove API |
| Shotgun surgery | Broker feature → gateway + provider + capability + transport + tests | High | Single SPI + adapter tests |
| Primitive obsession | Event payloads as dicts | Medium | Typed events bus-wide |
| Feature envy | Gateways vs DataProviders | Medium | Thin gateways; providers own API |
| Over-engineering | Capability manifest, multi buses, dual factories | Medium | YAGNI pass |
| Under-engineering | Paper streams, recovery codecs, daily PnL feed | Critical | Fix money path first |
| SOLID: DIP violated | Application must not construct infra (good rule) but composers ignore into tradex | Medium | One composition root |
| DRY violated | Fee models historically duplicated (partially consolidated in `domain.trading_costs`) | Medium | Force all consumers |

### 5.3 Code quality score: **5.5 / 10**

Strong engineering awareness (extractions, locks, guards) mixed with incomplete migrations and god modules.

---

## 6. Broker Integration Review

### 6.1 Parity matrix (code-verified)

| Capability | Dhan | Upstox | Paper |
|------------|------|--------|-------|
| place / cancel | Yes | Yes | Yes |
| modify | Yes (transport drops SL fields) | Yes | Yes |
| get_order | **Missing on gateway** (exists on orders adapter) | Yes | Yes |
| positions / holdings / funds | Yes | Yes | Yes |
| margin | Adapter exists | Adapter exists | No |
| native slice | Server | **Client-side 100ms loop** | No |
| WS reconnect | Mature | Mature | N/A stubs |
| stream via DataProvider | Correct kwargs | **Wrong kwargs + swallow** | Stubs |

### 6.2 P0 broker issues

1. **DhanBrokerGateway lacks `get_order`** — status poll / cancel confirm incomplete via gateway.  
2. **UpstoxDataProvider.subscribe** calls `stream(underlying, exchange, callback, depth=...)` but gateway expects `(symbol, exchange, mode, on_tick)` — silent failure.  
3. **Upstox slice client-side** — process death mid-slice = partial exposure; capability may claim native.  
4. **Paper false green** — random history, no real streams.  

### 6.3 Broker score: **5.5 / 10** (Dhan stronger than Upstox; paper unsuitable for sign-off)

---

## 7. Market Data Layer Review

| Concern | Assessment |
|---------|------------|
| Tick ingestion | Broker WS feeds large and real (Dhan ~1k LOC feed) |
| Reconnect / stale | Present (activity thresholds, ping/pong) |
| Duplicate ticks | **No robust source-level dedup** |
| Out-of-order | Synthetic sequence on Dhan only; no exchange seq |
| OHLC generation | Lake + candle aggregation paths |
| Time sync | Exchange calendars; **no NTP discipline** |
| Storage | Parquet + DuckDB catalog; local filesystem |
| Quality | `datalake/quality/*` gap/duplicate/OHLC checks — research-grade |
| Memory | Bounded queues on API WS (drop-oldest); feed complexity high |

**Risks:** tick gaps after reconnect (REST bar backfill ≠ tick continuity); drop-oldest under slow WS clients; single-node lake not multi-writer.

**Market data score: 5.5 / 10**

---

## 8. Testing Gap Analysis

### 8.1 Pyramid reality

| Layer | Reality |
|-------|---------|
| Unit / contract | Large; package-local + `tests/` |
| OMS-focused | Strong: idempotency, partial fills, kill switch, recon gates |
| Integration | Broker-gated; many markers exclude default CI |
| Chaos | ~12 modules — **in-process mock chaos**, not real network |
| E2E | Substantial files; **CI references missing `test_multi_broker_failover.py`** |
| Performance | Present |
| Mutation | Configured (mutmut); nightly workflows |
| Coverage config | fail_under 80; production_gate claims higher for OMS |

### 8.2 Critical testing gaps

1. **Cold-start multi-process recovery** (disk only → empty process) — chaos suite does not adequately cover.  
2. **Daily PnL feed wiring** — risk limits unit-tested with manual `update_daily_pnl`; production path untested.  
3. **Upstox subscribe signature** — would have failed a contract test.  
4. **Order store integration** — store unit-tested; not OMS-wired.  
5. **CI broken jobs**: `frontend/` directory missing; e2e failover file missing.  
6. **Security tools soft-fail** in main CI (`bandit || true`).  
7. **Live path vs paper path parity** insufficient for F&O.  

### 8.3 Testing score: **7.0 / 10** (breadth high; fidelity of critical money-path tests incomplete)

---

## 9. Reliability Assessment

### Present

- Circuit breakers, retry, rate limiters (esp. Dhan HTTP)  
- DLQ (in-memory + SQLite)  
- Lifecycle start/stop  
- Health/ready endpoints  
- Reconciliation gate before order placement post-restart  
- Idempotent correlation_id placement  

### SPOFs and production incidents waiting to happen

| Incident | Why |
|----------|-----|
| Restart with wrong positions | Ledger + dead store + deserialize |
| Risk thinks capital is ₹10L | Phantom default |
| MARKET blows size limits | Notional = qty |
| Upstox “subscribed” but no ticks | Silent subscribe bug |
| Mid-slice crash | Upstox client slicer |
| Dual process OMS | SQLite corruption if second writer |
| DLQ full of mysteries | No redrive / thin payload |
| Feature flag flip mid-session | Not admin-gated |

### Reliability score: **5.0 / 10** for live money / **7.0** for offline research tooling

---

## 10. Security Assessment

### Strengths

- Fail-closed `AUTH_MODE=api_key`  
- `secrets.compare_digest`  
- Live order env flags default off  
- Admin key intended for kill-switch  
- Production config forbids fail-open risk flags  
- SSL hardening helpers  

### Weaknesses

| Issue | Severity |
|-------|----------|
| Single shared API key = full trading power | P0 |
| Feature flags use `require_auth` not admin | P0 |
| `APP_ENV` vs `TRADEX_ENV` dualism can skip prod guards | P0 |
| No MFA / rotation API / IP allowlist | P1 |
| X-Forwarded-For trusted without proxy allowlist | P1 |
| Unauthenticated metrics endpoints | P1 |
| Secrets via env/files only (no vault) | P1 |
| Extended live routes accept raw dict payloads | P1 |
| Audit actor identity weak | P2 |

**Security score: 5.5 / 10** (good local defaults; weak multi-user / ops security)

---

## 11. Performance Assessment

| Area | Finding |
|------|---------|
| Order path | Synchronous bus + locks; acceptable single-strategy retail latency, not HFT |
| WS | Drop-oldest under load; max connections capped |
| Analytics | Pandas/DuckDB heavy; precompute helps |
| Hot gods | Market feeds, replay engine, historical coordinator |
| Scaling | Vertical only; no worker pool / multi-process design |
| Capacity | Fine for dozens of symbols single-node; not proven for universe-wide live streaming + multi-strategy |

**Bottlenecks to optimize later (after correctness):**

1. Sync EventBus on publisher thread  
2. Per-request broker connect amortization  
3. DuckDB/pandas on hot scans  
4. God WS feed modules  

**Performance score: 5.0 / 10** (adequate for supervised single-node; not low-latency institutional)

---

## 12. Frontend Review

| Surface | Status |
|---------|--------|
| Web SPA | **Not in repo** (CI still references `frontend/`) |
| CLI + Textual TUI | Primary operator UI (`cli/views/tui_app.py`, widgets) |
| API WebSocket | Market bridge + drop-oldest queues |

**Issues:** no component library / shared SPA state; browser CORS omits `X-API-Key`; WS header auth awkward for browsers; TUI is fine for single operator.

**Frontend score: 4.0 / 10** (CLI/TUI usable; no production web frontend)

---

## 13. Repository Organization Review

### Problems

1. Hybrid `src/domain` vs root packages without full convergence  
2. Duplicate resilience, paper, indicators  
3. Brokers package oversized (~66k LOC) — needs vertical slices + thin adapters  
4. `tradex.runtime` as second platform kernel  
5. Docs claim more readiness than code delivers  
6. Runtime artifacts (`runtime/*`, `market_data/*`) mixed with source tree  

### Cleaner structure (target)

```
packages/
  domain/           # pure
  application/      # use cases + OMS
  infrastructure/   # bus, persistence, resilience (ONE copy)
  brokers/
    dhan/
    upstox/
    paper/
  analytics/
  datalake/
  interfaces/
    api/
    cli/
apps/               # composition roots only
deploy/             # Docker, k8s, runbooks
tests/              # cross-cutting only; package tests co-located
```

---

## 14. Production Readiness Scorecard

| Area | Score (1–10) | Notes |
|------|-------------:|-------|
| Architecture | 5.0 | Good intent; incomplete migration; dual kernels |
| Quant Design | 4.0 | Path exists; risk/PnL/parity broken for money |
| Code Quality | 5.5 | Strong patterns + gods + dead wiring |
| Testing | 7.0 | Breadth high; critical path fidelity gaps; CI drift |
| Reliability | 5.0 | Components present; recovery not trustworthy |
| Scalability | 3.5 | Single-process assumption |
| Security | 5.5 | Local fail-closed; single-key / flag gaps |
| Performance | 5.0 | Retail single-node OK; not HFT |
| Maintainability | 4.5 | Sprawl + dualisms |
| Operational Readiness | 3.5 | No containers/HA; env dualism; soft security CI |

### **Overall Production Readiness: 4.6 / 10**

---

## 15. Top 20 Risks (ordered)

1. **Crash recovery rebuilds wrong/empty books** (deserialize + ledger + dead store)  
2. **Daily loss / loss CB never fires** (no `update_daily_pnl` wiring)  
3. **MARKET notional understates risk**  
4. **Phantom ₹1M capital default**  
5. **F&O PnL/risk without lot multiplier**  
6. **Extended orders bypass full risk**  
7. **Upstox subscribe silent failure**  
8. **Dhan get_order missing on gateway**  
9. **Buffered event log loss window without critical fsync**  
10. **Mark-before-apply trade ledger atomicity**  
11. **Upstox client-side slice crash exposure**  
12. **Paper false-greens strategies**  
13. **Feature flags not admin-gated**  
14. **APP_ENV vs TRADEX_ENV disables prod guards**  
15. **Multi-process / multi-instance OMS corruption**  
16. **Cancel/fill skip state machine; overfill accepted**  
17. **Async bus can drop TRADE/ORDER_UPDATED**  
18. **Single API key = total order authority**  
19. **CI references missing frontend/e2e artifacts**  
20. **No deploy topology / HA / ops runbooks as code**  

---

## 16. Top 20 Improvements

1. Wire daily PnL from positions/fills into RiskManager  
2. Notional from LTP/ref price; lot×multiplier for derivatives  
3. Fail-closed capital: ban phantom capital unless `paper` mode  
4. Integrate SqliteOrderStore write + hydrate  
5. Fix trade commit order (apply → mark) + recovery semantics  
6. Closed-world event codecs; forced fsync for capital events  
7. Fix Upstox subscribe signature + contract test  
8. Expose Dhan `get_order` on gateway  
9. Extended orders through full `check_order`  
10. Cancel/fill through OrderStateValidator; PARTIALLY_CANCELLED  
11. Unify resilience into one package  
12. Admin-gate feature flags; fix env naming  
13. Capability truth table + boot validator expansion  
14. Realistic paper = datalake/replay feeds, not random walk  
15. Per-strategy risk budgets before multi-strategy live  
16. Delete dead dual paths (orphan domain risk or wire it)  
17. Multi-process cold-start chaos suite as release gate  
18. Harden API identity (scopes, admin, rotation)  
19. Docker + single-node production compose with health probes  
20. Repair CI (remove ghost frontend job or restore app; fix e2e path)  

---

## 17. Refactoring Roadmap

### Phase 0 — Capital safety freeze (1–2 weeks) — **STOP-SHIP for auto live**

- P0 risk: daily PnL feed, notional, capital, multiplier, extended risk  
- P0 recovery: order store, ledger semantics, codecs, fsync  
- P0 broker: Upstox subscribe, Dhan get_order  
- P0 security: flags admin, env name single source  
- Fix CI ghosts  

**Exit criteria:** Chaos multi-process restart with only disk artifacts restores orders/positions; risk trips on simulated loss; MARKET blocked by size limits; Upstox stream ticks on SDK path.

### Phase 1 — Single money path (2–4 weeks)

- One place/modify/cancel path through OMS  
- Extended orders join OMS book  
- Paper/live/backtest share state machine  
- Capability validator matrix for all three brokers  
- Delete or thin dead dual risk policies  

### Phase 2 — Platform kernel consolidation (3–6 weeks)

- Merge `tradex.runtime.resilience` → `infrastructure.resilience`  
- Thin brokers to mappers + transports  
- Single composition root documentation as code tests  
- Event schema versioning + DLQ redrive  

### Phase 3 — Quant expansion (1–3 months)

- Multi-strategy capital partitions  
- Options Greeks risk, sector/underlying netting  
- Realistic paper from lake/replay  
- Walk-forward + live parity gates mandatory  

### Phase 4 — Ops / scale (parallel after Phase 1)

- Docker/k8s single-replica first  
- External secrets  
- Metrics auth / scrape network policy  
- Only then consider multi-replica with external OMS store  

---

## 18. Prioritized Action Plan

### Quick wins (1–2 days)

| # | Action | Owner lens |
|---|--------|------------|
| 1 | Fix `UpstoxDataProvider.subscribe` kwargs + unit test | Broker |
| 2 | Add `DhanBrokerGateway.get_order` delegate | Broker |
| 3 | Admin dependency on feature_flags router | Security |
| 4 | Standardize on `TRADEX_ENV` only; alias `APP_ENV` | SRE |
| 5 | Remove/fix CI `frontend/` job and missing e2e path | DevOps |
| 6 | Force `sync_mode=True` for TRADE/ORDER on EventLog append | Events |
| 7 | Fail closed if capital_fn is phantom in non-paper mode | Risk |

### Medium-term (1–4 weeks)

| # | Action |
|---|--------|
| 1 | Wire position/MTM → `update_daily_pnl` |
| 2 | MARKET notional from LTP; F&O multiplier |
| 3 | Order store persist + boot hydrate |
| 4 | Trade apply-then-mark + recovery tests multi-process |
| 5 | Extended orders full risk |
| 6 | Cancel/fill state machine correctness |
| 7 | Expand broker contract matrix in CI |
| 8 | One resilience package |
| 9 | DLQ redrive tool + full payload persist |
| 10 | Paper uses lake/replay data only |

### Long-term (1–6 months)

| # | Action |
|---|--------|
| 1 | Multi-strategy risk silos + attribution |
| 2 | Options risk engine |
| 3 | Containerized single-node prod + runbooks |
| 4 | Secrets manager integration |
| 5 | Optional external bus only if multi-process required |
| 6 | Thin broker packages; capability-driven plugins only |
| 7 | Web UI only after API auth scopes exist |
| 8 | Institutional observability (SLO/error budgets) |

---

## 19. Board Member One-Liners

| Expert | Verdict |
|--------|---------|
| Principal SWE | Stop adding surfaces; finish the money path. |
| Staff Architect | Dual kernels and incomplete ports will outpace any feature. |
| Quant Architect | Risk and PnL are not trustworthy for F&O or auto-size. |
| Low-Latency | Sync bus + Python GIL fine for retail; not for HFT claims. |
| Event Expert | This is pub/sub + journal, not event sourcing — fix recovery. |
| Distributed Systems | Single-writer SQLite + in-process bus = single node only. |
| SRE | No deploy model; env dualism; metrics open; recovery opaque. |
| QA Architect | Tests are many; CI ghosts and cold-start gaps undermine trust. |
| Security | One key owns the account; flags are not control-plane safe. |
| Data Platform | Lake quality tools exist; tick SoR and multi-writer not solved. |
| Frontend | CLI/TUI only; dead CI frontend job is a smell. |
| DevOps | Ship Docker + one-node prod before multi-broker marketing. |
| Performance | Optimize after correctness; god feeds are the main risk. |

---

## 20. Final Recommendation

**Do not run unsupervised live strategies on this codebase until Phase 0 exit criteria pass.**

Use today for:

- Research / scanners / backtests (with known cost model caveats)  
- Supervised paper **only after** paper data source is real market history  
- Manual live with tight broker-side limits and human kill-switch  

Treat Phase 0 as a **capital-safety program**, not a feature sprint.

---

*End of code-only board review. All severity rankings assume real-money exposure.*
