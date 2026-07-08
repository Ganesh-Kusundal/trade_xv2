# Trade_XV2 — Architecture Assessment & Refactor Roadmap (v2.0)

> Status: **Assessment phase** (no code yet).
> Scope decision: the first *build* slice when we exit assessment will be the
> **Instrument object model** (`Instrument / Equity / Option / Future / OptionChain`
> owning `quote / history / depth / subscribe / option_chain / greeks`).
> Companion plan already on disk: `brokers/OBJECT_MODEL_PLAN.md`.

---

## 0. Executive verdict

The prompt's premise — *"this is a broker SDK / REST wrapper / manager-heavy
gateway that must be deleted wholesale"* — is **only partly accurate**. The repo
is already a ~1,500-file, layered project with a genuinely clean `domain/` layer
(108 files, **zero imports into `brokers/`**, frozen value objects, capability
model, typed events, domain ports). A literal "delete everything and rebuild"
would destroy large amounts of working, tested code and repeat the exact mistake
the in-repo `OBJECT_MODEL_PLAN.md` explicitly avoided (it chose an *additive,
non-breaking* path).

**The real, concrete debt is narrow and well-located**, not systemic:

| # | Problem | Where | Severity |
|---|---------|-------|----------|
| P1 | Gateway-centric brokers: fat facades with `history()/quote()/depth()/option_chain()` as free `symbol`-string methods | `brokers/*/gateway.py`, `brokers/common/*gateway*.py` | **High** |
| P2 | Business rules live in `application/` not domain (PnL, risk limits, exposure, loss-circuit-breaker) | `application/oms/_internal/risk_manager.py`, `portfolio_service.py`, `simulated_fill.py` | **High** |
| P3 | Layer violations: `application → brokers` and `infrastructure → brokers` direct imports | `application/composer/*`, `infrastructure/observability/alerting.py`, `state_machine.py`, `retry.py` | **High** |
| P4 | Brokers are core packages, not plugins; `plugins/` is near-empty ad-hoc code | `brokers/dhan`, `plugins/indicators/*` | **High** |
| P5 | Redundant anemic `domain/trading/` dataclasses duplicate `domain/aggregates/` | `domain/trading/{order,position,portfolio}.py` | Medium |
| P6 | Domain events defined but never emitted *by* domain objects | `domain/events/*` (0 `publish` calls in aggregates/entities) | Medium |
| P7 | No `Equity/Option/Future` subtypes; Greeks are a `dict`, not behavior; no `PortfolioAggregate`; `Subscription`/`Scanner` are only Protocols/ids | `domain/*` | Medium |
| P8 | Domain aggregates/value objects have almost **no unit tests**; contract tests cover only `paper` | `domain/tests`, `tests/contract` | **High** |
| P9 | Test suite **not runnable**: undeclared markers (`real_broker`, `golden`); pre-commit points at wrong path | `pyproject.toml`, `.pre-commit-config.yaml` | Medium |

Everything else (the layered skeleton, capability manifest, ISP gateway
interfaces, extension registry, frozen VOs, import-linter contracts) is **keep /
build on**, not delete.

---

## 1. Target domain model (the "Financial OS")

The public API consumers should see. Infrastructure is invisible behind it.

```
Account  ──owns──▶  Portfolio  ──owns──▶  Position(s)  ──ref──▶  Instrument
                                                        │
Instrument (ABC)                                        ├── Quote            (frozen VO)
  ├─ Equity  ──owns──▶ Quote, MarketDepth,              ├── MarketDepth      (frozen VO)
  │                  HistoricalSeries, Subscription,    ├── HistoricalSeries
  │                  IndicatorSet, Statistics,          ├── Execution(s)
  │                  CorporateActions, Cache            └── PnL()
  ├─ Future  ──owns──▶ (same + expiry/contract specs)
  ├─ Option  ──owns──▶ Greeks (VO), PricingModel,      Order  ──lifecycle──▶  Execution
  │                  VolatilitySurface, Underlying     (place→pending→filled/
  └─ Spot                                                partial→rejected/cancelled)
        ▲  OptionChain ──composes──▶ [Option], Underlying, strikes
        ▲  FutureChain ──composes──▶ [Future]
Exchange, MarketSession, Watchlist, Universe, Scanner, RiskProfile, Analytics
```

**Tell, don't ask.** Behavior lives on the object:

```python
reliance = universe.equity("RELIANCE")      # returns Instrument (Equity)
q = reliance.quote                           # frozen Quote VO
series = reliance.history(interval="1d", days=200)
chain = reliance.option_chain("2026-07-31") # OptionChain aggregate
atm_calls = chain.atm_strike().calls
greeks = atm_calls[0].greeks                 # frozen Greeks VO
sub = reliance.subscribe(on_tick=my_handler) # Subscription object, emits TickReceived
order = reliance.buy(qty=10).market().submit()  # returns Order, emits OrderFilled
```

No `gateway.quote("RELIANCE")`, no `if broker == "dhan"`, no JSON, no REST.

---

## 2. Layer-by-layer assessment

Notation: **KEEP / MOVE / MERGE / SPLIT / RENAME / REDESIGN / DELETE**.

### 2.1 `domain/`  (clean — mostly keep, tighten)

| Item | State | Action | Evidence |
|------|-------|--------|----------|
| `aggregates/instrument.py` (`InstrumentAggregate`) | already owns `get_quote/history/depth/option_chain/subscribe` | **KEEP + promote** to the public `Instrument` | `:189-312` |
| `aggregates/{order,position,account,option_chain}.py` | rich, thread-safe, wrap frozen VOs | **KEEP** | — |
| `entities/*` (frozen VOs: Quote, Trade, Order, Position, Money, Exchange, Option*) | immutable | **KEEP** | — |
| `trading/{order,position,portfolio}.py` | anemic `frozen=False` dataclasses, mutated via `object.__setattr__` | **DELETE** (behavior already in `aggregates/`) | `:15,:25,:11` |
| `value_objects/money.py`, `capability.py`, `state.py` | good | **KEEP + add unit tests** | untested |
| `events/types.py`, `events/bus.py` | typed events + port, **never emitted by objects** | **KEEP + wire emission into aggregates** | 0 `publish` in domain |
| `capabilities.py`, `capability_manifest.py` | capability enum + broker→method manifest | **KEEP** (becomes decorator selector) | `:92` manifest |
| `ports/*` (broker_gateway, market_data, execution_context, margin, risk) | good ISP ports | **KEEP** | — |
| `repositories/order_repository.py`, `position_repository.py` | domain ports | **KEEP** | — |
| Missing: `Equity/Option/Future` subtypes, `Greeks` VO, `PortfolioAggregate`, `Subscription` obj, `Scanner` obj, `Specification` pattern | absent | **ADD** | — |

**SOLID/DDD violations in domain:** only the `trading/` duplication (SRP — two
models of the same concept) and missing Specification pattern (OCP — filters are
inline). Fixing P5 + P7 closes both.

### 2.2 `brokers/`  (the core debt — P1 gateway facade)

| Item | State | Action | Evidence |
|------|-------|--------|----------|
| `MarketDataGateway` ABC (`common/gateway.py`) | 26-method fat facade | **REDESIGN → `BrokerTransport` port** | `:57` |
| `dhan/gateway.py` `BrokerGateway` | 44 methods / 715 lines | **DEMOLISH → `DhanTransport`** (thin session over existing `adapter.py`, `orders.py`, `websocket/`, `depth_20/200.py`) | `:47` |
| `upstox/gateway.py` `UpstoxBrokerGateway` | 36 methods / 923 lines | **DEMOLISH → `UpstoxTransport`** | `:68` |
| `paper/paper_gateway.py` `PaperGateway` | 33 methods / 525 lines | **DEMOLISH → `PaperTransport`** | `:36` |
| `common/intelligent_market_gateway.py` | 34 methods / 600 lines | **REDESIGN → quota/cache decorator**, not a gateway | `:95` |
| `common/capabilities.py`, `upstox/capabilities/*`, `upstox/adapter.py` | clean ISP adapters | **KEEP** (reuse as transport internals) | `:92` |
| `common/extensions/` (decorator/extension registry) | existing Decorator seed | **KEEP + extend** for `Depth20/30/200` decorators | `super_order`, `forever_order` |
| `common/*` broker-name conditionals (`if broker=="dhan"`) | ~20 sites | **REPLACE** with capability dispatch (`common/bootstrap.py:25`, `authenticated_readiness.py:45`) | — |
| `dhan/websocket/market_feed.py` (1028), `http_client.py`, `token_manager.py`, resilience, caching | transport internals | **MOVE** into transport objects / `infrastructure/` | — |

**Anti-pattern to remove:** `gateway.quote("RELIANCE")` (free method on a god
facade, takes a string). **Replacement:** `universe.equity("RELIANCE").quote`.

### 2.3 `application/`  (P2 business rules, P3 violations)

| Item | State | Action | Evidence |
|------|-------|--------|----------|
| `oms/_internal/risk_manager.py` (notional, per-symbol concentration, gross-exposure, default limits) | **domain risk policy** | **MOVE** to `domain/risk/*` (Policy objects) | `:82,:264,:290` |
| `oms/_internal/loss_circuit_breaker.py` (cumulative-loss % trip) | domain rule | **MOVE** to `domain/risk/*` | `:131` |
| `portfolio/portfolio_service.py` (unrealized+realized PnL, pnl_pct) | domain math | **MOVE** to `PortfolioAggregate`/`PositionAggregate.pnl()` | `:105` |
| `execution/simulated_fill.py` (`trade_value = price*qty`) | domain pricing | **MOVE** to domain `Execution`/pricing VO | `:86` |
| `oms/order_manager.py` (709), `position_manager.py` (359), `trading_orchestrator.py` (613) | god classes with mixed concerns | **SPLIT**: workflow orchestration stays, business rules move to domain | — |
| `composer/{execution,market_data,factory}.py` | import `brokers.common.*` directly | **REPOINT** through `domain/ports/broker_gateway.py` | `:13-16,:20-28` |
| `oms/oms_gateway_proxy.py` | imports `brokers.common` + concrete infra | **REPOINT** through ports/repositories | `:46` |
| Workflows (`place_order_use_case`, `cancel_order_use_case`, `gateway_submit`, reconciliation) | correct shape | **KEEP** (thin coordinators) | — |

**Rule:** Application coordinates *workflows*; it must not compute PnL, risk, or
pricing. Those are domain aggregate behavior.

### 2.4 `infrastructure/`  (P3 violation: → brokers)

| Item | State | Action | Evidence |
|------|-------|--------|----------|
| `observability/alerting.py`, `state_machine.py`, `retry.py`, `global_exception_handler.py` | import `brokers` | **FIX**: depend only on `domain` ports, not broker code | — |
| `cache.py`, `cache_redis.py`, `metrics/*`, `db/duckdb_pool.py`, `io/parquet.py`, `persistence/sqlite_order_store.py` | correct (depend on domain) | **KEEP** | — |
| `providers/` (csv/dataframe/broker/composite), `di.py` | correct | **KEEP** | — |

### 2.5 `plugins/`  (P4 — not a real plugin system)

| Item | State | Action |
|------|-------|--------|
| `plugins/indicators/{rsi,atr,vwap,macd}.py` | plain classes, no base/registry/contract | **REPLACE** with `Indicator` ABC + `IndicatorRegistry` (or fold into `domain/analytics/indicators`) |
| `brokers/dhan`, `brokers/upstox`, `brokers/paper` | core top-level, not plugins | **MOVE → `plugins/dhan`, `plugins/upstox`, `plugins/paper`** behind `domain/ports/broker_gateway.py` |

After this, `brokers/` (common transport contracts) and `plugins/<broker>/` are
the only broker code; `application/` and `api/`/`cli/` never name a broker.

### 2.6 `api/` + `cli/`  (broker-shaped surface — P-rewrite)

| Item | State | Action | Evidence |
|------|-------|--------|----------|
| `api/routers/live/*` (7 files: `orders.py`, `market.py`, `extended.py`…) | raw broker verbs (`place_super_order`, `get_ledger`, `_require_broker("dhan")`) | **REWRITE** against domain objects / capability-gated ports | `live/orders.py:23`, `extended.py:216,335` |
| `cli/commands/market_handlers.py` (`gw.quote(symbol)`, `gw.depth(symbol)`) | gateway calls | **REWRITE** to `instrument.quote` | `:37,:73` |
| `cli/main.py` (`--broker dhan\|upstox`) | forces broker choice | **REMOVE** broker flag; broker chosen at session bootstrap | `:78,:242` |
| No top-level facade (`from tradexv2 import …`) | absent | **ADD** `src/tradexv2/__init__.py` exposing domain + a `Session` | — |
| api/ vs cli/ duplicate orchestration (orders, market, portfolio) | duplicated | **COLLAPSE** into shared application workflows behind the facade | — |

Est. blast radius: **~18 api files + ~40 cli command/service files** need to
move from gateway-calls to object-calls. Domain layer itself is fine.

---

## 3. Refactor roadmap (sequenced, additive, non-breaking)

Each phase is independently shippable and keeps the test suite green. Phases are
ordered by leverage and by dependency (later phases need earlier ones).

### Phase 0 — Make the suite trustworthy (prerequisite for everything)
- Declare `real_broker` / `golden` markers in `pyproject.toml`; fix pre-commit
  path bug (`tests/brokers/...` → `brokers/*/tests/...`).
- Get `pytest -m unit` collecting clean. Add a CI gate on the architecture
  fitness + import-linter suites.
- **Owner:** tooling. **No behavior change.**

### Phase 1 — **Instrument object model** (the chosen first build slice)
*This is where we start writing code after assessment.*
1. Add domain subtypes: `Instrument(ABC)` ← `Equity`, `Future`, `Option`, `Spot`
   (composition over inheritance; `Option` composes `Underlying`, `Greeks`,
   `VolatilitySurface`; `Equity` composes `Quote/Depth/Historical/Subscription/Stats`).
2. Promote `InstrumentAggregate` (`aggregates/instrument.py`) to the public
   `Instrument`; ensure `quote/history/depth/option_chain/subscribe` are real,
   capability-aware methods.
3. Introduce `Greeks` frozen VO + `option.greeks()`; `OptionChainAggregate`
   `atm_strike()/itm_calls()` already exist — keep, add per-strike greeks accessor.
4. Add `Subscription` as a tracked object (not just a Protocol) that owns the
   handle and emits `TickReceived` / `DepthChanged`.
5. **Capability-driven transport:** `Instrument` receives a `BrokerTransport`
   (port). Broker depth-20/30/200 become **Decorator** objects wrapping the
   instrument, selected by `BrokerCapabilities` — no `if broker==`.
6. **Wire events:** `InstrumentAggregate`/`OrderAggregate`/`PositionAggregate`
   publish domain events through the injected `EventBus` port.
7. Build `Universe` / `Session` facade: `session.universe.equity("RELIANCE")`.
8. **Tests:** exhaustive unit tests for `Instrument`, `Equity`, `Option`,
   `OptionChain`, `Greeks`, `Subscription`; property tests for resample/indicators;
   **contract tests** every transport must pass (market data surface).

*Outcome:* consumers can do `reliance.quote` / `reliance.option_chain(...)` with
zero broker/REST/JSON knowledge. Brokers still work via the old gateway path in
parallel (additive).

### Phase 2 — Broker → invisible plugin
- Rename `BrokerGateway` → `DhanTransport`/`UpstoxTransport`/`PaperTransport`;
  implement `domain/ports/broker_gateway.py`. Move `brokers/dhan` → `plugins/dhan`.
- Collapse `intelligent_market_gateway` into a quota/cache **decorator**.
- Replace ~20 `if broker==` conditionals in `brokers/common` with capability
  dispatch.
- **Contract tests** for all six surfaces (market/orders/portfolio/historical/
  streaming/capabilities) — one abstract suite every plugin subclasses.

### Phase 3 — Business rules back into domain (P2)
- Move PnL math → `PortfolioAggregate`/`PositionAggregate.pnl()`.
- Move risk policy (notional, concentration, exposure, loss-circuit-breaker) →
  `domain/risk/*` Policy objects; `OrderAggregate.apply_status` enforces pre-trade
  via injected `RiskManager` port.
- Move pricing (`trade_value`) → domain `Execution`/pricing VO.
- Delete the now-empty `application/oms/_internal/{risk_manager,loss_circuit_breaker}` logic.

### Phase 4 — Kill redundant `domain/trading/` (P5)
- Behavior already in `aggregates/`; delete `domain/trading/{order,position,portfolio}.py`
  and repoint internal references. Add missing `PortfolioAggregate`.

### Phase 5 — Fix layer violations (P3)
- Repoint `application/composer/*` and `oms_gateway_proxy` through domain ports.
- Fix `infrastructure/observability/alerting.py`, `state_machine.py`, `retry.py`,
  `global_exception_handler.py` to depend only on `domain`, not `brokers`.

### Phase 6 — Re-surface api/ + cli/ on objects (P-rewrite)
- Rewrite `api/routers/live/*` and broker-shaped CLI handlers against domain
  objects; capability-gate broker-specific verbs instead of `_require_broker`.
- Add `src/tradexv2/__init__.py` facade. Collapse api/cli orchestration
  duplication into shared workflows.

### Phase 7 — Hardening
- `Scanner` as a real object; `Specification` pattern for filtering.
- Plugin indicators (`plugins/indicators` → `Indicator` ABC + registry).
- Performance/stress tests (100k ticks/s, 1000 instruments, large option chains).
- ADRs + diagrams (see §4) finalized; architecture fitness extended to enforce
  Phase 1–6 invariants.

---

## 4. Architecture Decision Records (key decisions)

> Full ADRs live under `docs/adr/`. Summary of the load-bearing choices:

- **ADR-1 Additive, non-breaking refactor.** We layer objects *over* the existing
  gateway (per `OBJECT_MODEL_PLAN.md`), not delete it. Rationale: 1,500 files of
  tested code; risk of untraceable breakage; matches the in-repo plan.
- **ADR-2 Composition over inheritance for instrument family.** `Instrument` is an
  ABC; `Equity/Option/Future/Spot` are subtypes; broker depth superpowers are
  **Decorator** objects, not subclasses. (OCP: new broker power = new decorator.)
- **ADR-3 Capability model, never `if broker==`.** `BrokerCapabilities` selects
  transports/decorators. Domain is broker-conditional-free (already true today).
- **ADR-4 Domain owns behavior + emits events.** Aggregates publish through an
  injected `EventBus` port; `application/` orchestrates only.
- **ADR-5 Brokers are plugins.** `brokers/common` = transport contracts;
  `plugins/<broker>` = implementations behind `domain/ports/broker_gateway.py`.
- **ADR-6 Immutable value objects.** Quote/Tick/Trade/Candle/Money/Greeks frozen;
  mutations replace objects.

---

## 5. Testing strategy (pyramid)

| Tier | Today | Target after roadmap |
|------|-------|----------------------|
| Unit (largest) | weak on aggregates/VOs | exhaustive for `Instrument/Equity/Option/OptionChain/Greeks/Subscription/Order/Position/Portfolio` + property tests (resample, indicators, PnL, greeks) |
| Component | partial | repositories, transports, historical/streaming providers, persistence, cache |
| Integration | good (~70) | broker integration, order lifecycle, market-data sync, historical load, subscription lifecycle, recovery |
| **Contract** | only `paper` | **all six surfaces, every plugin** (abstract suite) |
| E2E | ~16 | startup→login→subscribe→trade→fill→portfolio→recover→shutdown |
| Perf/Stress | thin | 100k ticks/s, 1000 instruments, large chains, disconnect/reconnect |

**First testing investment (Phase 1):** unit + property + contract tests for the
Instrument object model. This is also the gate that makes later phases safe.

---

## 6. Success criteria (measurable)

- `grep -rn "if broker ==" brokers/common` → 0 results.
- `application/` and `api/`/`cli/` contain 0 imports of `brokers/<name>` or
  `plugins/<name>` concrete modules (only `domain.ports`).
- `pytest -m unit` runs clean; contract suite green for dhan/upstox/paper.
- A consumer script using only `Instrument`/`Order`/`Portfolio`/`OptionChain`
  (no `gateway`, no `requests`, no JSON) compiles and runs.
- Domain aggregates/value objects: unit coverage ≥ 90%; no `mutmut` score < 80
  on the instrument/order/position aggregates.
- Import-linter + architecture fitness enforce Phases 1–6 invariants in CI.

---

## 7. Recommended next action

Exit assessment and **start Phase 1 (Instrument object model)** as an
additive slice on a new branch off `main`, with its unit + contract tests, then
return for Phase 2 review. Say the word and I'll scaffold `Instrument`/`Equity`/
`Option`/`OptionChain` + `Greeks` VO + `Subscription` + the `BrokerTransport`
port and the first contract test.
