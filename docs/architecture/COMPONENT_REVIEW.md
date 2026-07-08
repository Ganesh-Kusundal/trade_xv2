# Trade_XV2 — Per-Component Architecture Review (re-review, current state)

> Re-review of the **current** repo state after `domain/` relocated to `src/domain/`
> with finer sub-packages. Companion to `docs/architecture/ASSESSMENT_AND_ROADMAP.md`
> (that doc's Phase 0/1 must now target `src/` layout). Every finding below was
> re-verified against files that currently exist.

---

## 0. What changed since the first assessment (delta)

| # | Earlier finding | Current state |
|---|-----------------|--------------|
| — | `domain/` at repo root | **Moved to `src/domain/`**; new packages `instruments, options, orders, executions, candles, indicators` |
| — | `application → brokers` direct imports (violation) | **FIXED** — `application/` no longer imports `brokers`/`plugins` directly |
| — | No rich `Instrument` object | **NOW EXISTS** — `src/domain/instruments/instrument.py` (`Instrument`/`Equity`/`Index`/`Future`/`Option`), broker-free, emits events |
| — | `Greeks` only a `dict` | **NOW a frozen VO** — `src/domain/options/greeks.py` |
| P1 | Gateway facades | **UNCHANGED** — still fat (see §3) |
| P2 | Business rules in `application/` | **UNCHANGED** — risk/PnL/sizing still in `application/` (see §4) |
| P3 | `infrastructure → brokers` | **UNCHANGED** — `infrastructure/retry.py`, `observability/alerting.py`, `global_exception_handler.py` still import `brokers.common` |
| P5 | Redundant `domain/trading/` | **UNCHANGED** — still present & anemic |
| P7 | Missing target sub-packages | **WORSE in naming** — `src/domain` still a monolith; 12 target sub-packages absent (see §2) |
| P8 | Domain unit tests weak | **UNCHANGED** — `Instrument`/`Order`/`OptionChain` still thinly tested |
| P9 | Suite not runnable | **UNCHANGED** — markers + pre-commit bugs persist |

**Net:** the *surface* improved (richer `Instrument`, eventing begins, app layer
cleaned of broker imports) but the *structural* debt is intact. This review
focuses on the components that still need work.

---

## 1. Layer-health dashboard (current)

| Check | Status | Evidence |
|-------|--------|----------|
| `src/domain` → `brokers`/`application`/`infrastructure` (runtime) | ✅ clean | grep: none |
| `src/domain/indicators` → `plugins.indicators` | ❌ violation | `src/domain/indicators/indicators.py:1-4` |
| `src/domain/tests` → `brokers` | ❌ test violation | `src/domain/tests/markets/test_dhan_adapter.py:52`, `test_platform_api.py:193` |
| `application` → `brokers`/`plugins` | ✅ clean (fixed) | grep: none |
| `application` → concrete `infrastructure` (not `src/domain` ports) | ❌ violation | `oms/context.py:13-29`, `order_manager.py:33-47`, `position_manager.py:18-21` |
| `infrastructure` → `brokers.common` | ❌ violation | `infrastructure/retry.py:42`, `observability/alerting.py:19`, `global_exception_handler.py:23` |
| `infrastructure` → `src/domain` ports | ❌ absent (0 refs) | grep: none — infra depends on `brokers.common`, not domain |
| Domain events emitted by aggregates | ⚠️ partial | `instruments/instrument.py:178-234` only; `OrderAggregate`/`OptionChainAggregate` silent |
| Immutable VOs | ⚠️ partial | frozen: Quote/Tick/Trade/Candle/Money/Greeks; **mutable**: MarketDepth, HistoricalSeries, SubscriptionState, DateRange, OrderLifecycle, Portfolio, PositionLifecycle |

---

## 2. Structural gap vs target layout (missing sub-packages)

`src/domain` currently has: `aggregates, candles, constants, entities, events,
execution, executions, extensions, indicators, instruments, market, models,
options, orders, ports, providers, repositories, serialization, trading, utils,
value_objects`.

**Target sub-packages from the refactoring directive that are ENTIRELY MISSING:**
`scanners, exchanges, sessions, risk, analytics, accounts, portfolio, positions,
futures, quotes, factories, specifications`.

Also missing: `src/__init__.py` public facade; `application/infrastructure/plugins/api/cli`
still at repo root (partial migration — only `domain` moved under `src/`).

---

## 3. Per-component 13-point reviews — BROKER layer

### 3.1 `brokers/upstox/gateway.py` — `UpstoxBrokerGateway` (923 lines, 41 methods)
1. **Current responsibility:** unified market-data / order / stream facade (HTTP+WS+auth+decode).
2. **Correct?** Partially — works, but conflates transport, mapping, auth, retry.
3. **Problems:** 923 lines; `symbol:str` API; inline `_resolve_instrument_key`, `_translate_tick_to_depth`; mixes sync/async; holds auth/token/pkg state.
4. **SOLID:** SRP violated (≥6 roles); OCP violated (broker branching inside); ISP bloated.
5. **DDD:** leaks transport into a domain-facing gateway; no value objects.
6. **Arch smells:** fat facade, feature envy, shotgun surgery on broker changes.
7. **Code smells:** long methods, primitive obsession (`symbol` str), duplicated `_*_normalize_exchange`.
8. **Action:** **SPLIT + REDESIGN** into `ports` (interfaces) + `adapters` (transport) + `mappers` + `services`.
9. **New package:** `src/domain/ports` (interfaces) + `plugins/upstox/{adapters,transport,mapping}`.
10. **Collaborators:** `MarketDataPort`, `OrderPort`, `StreamPort`, `token_manager`, `domain_mapper`, `resilience`.
11. **Public API:** domain-object methods `get_quote(Instrument)` — **no symbol strings**.
12. **Internal:** HTTP/WS/cache delegated out; class orchestrates only.
13. **Tests:** contract tests vs `ports`; adapter unit tests; decode round-trips.

### 3.2 `brokers/common/stream_orchestrator.py` — `StreamOrchestrator` (872 lines, 25 methods)
1. **Responsibility:** multiplex WS sessions, fan-out ticks/orders, failover, heartbeat, health.
2. **Correct?** Functional but too large to evolve safely.
3. **Problems:** 25 methods spanning session-lifecycle, frame-normalization, failover, broker-selection (`_select_broker` at 812 — conditional smell), reconnect, health.
4. **SOLID:** SRP violated (session mgmt + delivery + failover + health).
5. **DDD:** orchestration is infra, not domain; broker selection conditional `if broker==`.
6. **Arch smells:** god object, conditional broker dispatch, temporal coupling.
7. **Code smells:** long class, switch-like broker branches, mixed abstraction levels.
8. **Action:** **SPLIT** into `SessionManager`, `FrameRouter`, `FailoverPolicy`, `HealthSupervisor`.
9. **New package:** `brokers/common/streaming/{session,router,failover,health}`.
10. **Collaborators:** `StreamPort`, `BrokerHealthMonitor`, `StreamConsumer` protocol, `resilience`.
11. **Public API:** `subscribe(req)->id`, `on_tick` callback, `session_health`.
12. **Internal:** each sub-component owns one concern; broker choice via strategy, not `if`.
13. **Tests:** session lifecycle, failover, freshness/heartbeat, fan-out.

### 3.3 `brokers/dhan/gateway.py` — `BrokerGateway` (715 lines, 48 methods)
Same shape as 3.1 (Dhan flavor). **Action: SPLIT+REDESIGN** into `plugins/dhan/{adapters,transport,mapping}` behind `src/domain/ports`. Remove `symbol`-string surface.

### 3.4 `brokers/common/intelligent_market_gateway.py` — `IntelligentMarketDataGateway` (600 lines, 34 methods)
Quota/cache/intelligent-routing logic. **Action: REDESIGN** as a **decorator** over a `BrokerTransport` (per `brokers/OBJECT_MODEL_PLAN.md §4`), not a gateway subclass.

### 3.5 Broker conditionals (~15 real sites in `brokers/common`)
`bootstrap.py:25-27`, `connection/authenticated_readiness.py:45-50,63,180-182`,
`auth/credential_validator.py:33,54,56`, etc. `capabilities.py:97` *forbids* these
yet they persist. **Action: REPLACE** with capability dispatch / strategy objects.

---

## 4. Per-component 13-point reviews — APPLICATION / INFRASTRUCTURE

### 4.1 `application/oms/_internal/risk_manager.py` (453 lines) — business rules leak
1. **Responsibility:** enforce margin, exposure, daily-loss, kill-switch.
2. **Correct?** No — domain policy lives in `application`, not `src/domain`.
3. **Problems:** couples margin math + circuit-breaker + kill-switch + daily-PnL in one class.
4. **SOLID:** SRP broken (4 concerns); OCP weak (thresholds hardcoded).
5. **DDD:** risk policy should be domain `Policy` objects / `Account` aggregate behavior.
6. **Arch smells:** god module, feature envy on `Order`/`Decimal`.
7. **Code smells:** long methods, magic thresholds.
8. **Action:** **MOVE** to `src/domain/risk/` (Policy objects) behind `src/domain/ports/risk_manager.py`.
9. **New package:** `src/domain/risk/`.
10. **Collaborators:** `Money`, `Account` aggregate, `Order`, `EventPublisher`.
11. **Public API:** `check_order(Order)->RiskResult`, `update_daily_pnl`, `set_kill_switch`.
12. **Internal:** `_check_margin`, breaker delegate, config.
13. **Tests:** margin/exposure/kill-switch/concurrency property tests.

### 4.2 `application/oms/order_manager.py` (709 lines) — god class
1. **Responsibility:** order placement, idempotency, broker submit, trade recording, event publish, reconciliation.
2. **Correct?** Partially — orchestration ok, but absorbs domain + infra concerns.
3. **Problems:** 709 lines, 30+ methods spanning place/cancel/persist/publish/reentrancy.
4. **SOLID:** SRP/LSP broken; DIP violated (imports concrete infra).
5. **DDD:** application service doing repo + event + infra work.
6. **Arch smells:** god class, long methods, mixed levels.
7. **Code smells:** feature envy, duplicated ordering logic.
8. **Action:** **SPLIT** into `place_order`, `cancel_order`, `order_query`, `trade_recorder` workflows; keep only orchestration.
9. **New package:** `src/application/oms/` (thin) — or `src/application/workflows/`.
10. **Collaborators:** `src/domain/ports` (event_publisher, order_repository, risk_manager), `OrderAggregate`.
11. **Public API:** `place_order`, `cancel_order`, `get_order`.
12. **Internal:** idempotency, reentrancy, state transitions via `OrderAggregate`.
13. **Tests:** idempotency, partial-fill, concurrency, event emission.

### 4.3 `infrastructure/retry.py:42` — infra → brokers violation
1. **Responsibility:** retry/backoff decorator + `TradeXV2RecoverableError` classification.
2. **Correct?** No — imports `brokers.common.resilience.errors`.
3. **Problems:** couples cross-cutting infra to a broker package.
4. **SOLID:** DIP violated; SRP ok.
5. **DDD:** wrong layer dependency direction (infra must depend on domain, not brokers).
6. **Arch smells:** layer leak.
7. **Code smells:** import of sibling package's internals.
8. **Action:** **MOVE** `TradeXV2RecoverableError` to `src/domain/errors.py`; `retry.py` imports `src.domain`.
9. **New package:** `src/infrastructure/retries` (imports `src/domain`).
10. **Collaborators:** `src/domain/errors`.
11. **Public API:** `retry(...)`, `RetryPolicy`.
12. **Internal:** backoff math, classification.
13. **Tests:** error-classification, backoff schedule.

### 4.4 `infrastructure/observability/alerting.py:19` & `global_exception_handler.py:23` — same violation
Import `brokers.common.observability.alerting` / `brokers.common.resilience.errors`.
**Action:** depend on `src/domain` ports/errors; lift shared error types into `src/domain/errors.py`.

> **Headline infra problem:** `infrastructure/` has **zero** `src.domain` references and depends on `brokers.common` instead of the domain ports it is supposed to implement. This inverts Clean Architecture. Fix by repointing infra to `src/domain/ports`.

---

## 5. Per-component 13-point reviews — DOMAIN (current state)

### 5.1 `Instrument / Equity / Option / Future` family
`src/domain/instruments/instrument.py` (`Instrument:50`, `Equity:251`, `Index:271`, `Future:291`, `Option:327`); `src/domain/aggregates/instrument.py:38` `InstrumentAggregate`; `src/domain/entities/instrument.py:22` `InstrumentRecord`.
1. **Responsibility:** public instrument facade + aggregate owning identity/state, delegating data to injected provider; subclasses for asset types.
2. **Correct?** Yes — rich, broker-free, Tell-Don't-Ask. **This is the target shape — preserve and extend.**
3. **Problems:** `Future.basis/cost_of_carry` return `None` stubs; `Option.greeks` forces lazy import; two instrument models (facade vs `InstrumentRecord`).
4. **SOLID:** mostly fine; `Option.from_leg` couples to raw leg dict (O/C weak).
5. **DDD:** aggregate root well-formed; `InstrumentRecord` (entity) is an anemic adapter artifact — belongs in adapters, not domain core.
6. **Arch smells:** `get_default_provider()` import inside ctor (`instruments/instrument.py:65`) hides composition root; stubs.
7. **Code smells:** stub methods; dual instrument models.
8. **Action:** **KEEP + extend**; **MOVE** `InstrumentRecord` to broker-adapter layer; delete stubs or document as extension points; inject provider at construction (composition root).
9. **New package:** `src/domain/instruments/`.
10. **Collaborators:** `InstrumentAggregate`, `DataProvider` port, `DomainEventBus`, `Indicators`, `OptionChain`.
11. **Public API:** `Equity/Index/Future/Option`; `refresh/history/depth/subscribe/option_chain/greeks`.
12. **Internal:** state replacement under lock; extension lookup.
13. **Tests:** facade-vs-aggregate parity; event publish on subscribe/refresh; provider injection.

### 5.2 `Order / Execution`
`src/domain/aggregates/order.py:28`, `src/domain/entities/order.py:60`, `src/domain/executions/result.py:25` `GatewayResult`; anemic `src/domain/trading/order.py:26`.
1. **Responsibility:** `OrderAggregate` owns id/status/trades; frozen `Order` VO; `GatewayResult` monad.
2. **Correct?** Partly — aggregate solid; **Execution concept missing**.
3. **Problems:** no `Execution` entity/aggregate; `OrderAggregate` never emits `OrderUpdatedEvent`/`TradeFilledEvent` (`src/domain/events/types.py:570,596` defined but unused here); `trading/order.py` duplicate; dual status enums (`entities/order.OrderStatus` vs `trading/order.OrderStatus`).
4. **SOLID:** SRP ok; O violated by parallel mutable `OrderLifecycle`.
5. **DDD:** missing Execution aggregate; events defined but not raised by aggregate (anemic eventing).
6. **Arch smells:** duplicated lifecycle model; dual status enums.
7. **Code smells:** dead mirror class.
8. **Action:** **KEEP** `aggregates/order` + `entities/order`; **DELETE** `trading/order.py`; **ADD** `Execution` aggregate wrapping `Trade` fills.
9. **New package:** `src/domain/orders/` + `src/domain/executions/`.
10. **Collaborators:** `Order` VO, `Trade`, `ORDER_STATUS_TRANSITIONS`, `EventPublisher` port, repositories.
11. **Public API:** `apply_status/apply_fill/add_trade`; `Execution.place/fill`.
12. **Internal:** lock state swap; transition-table enforcement.
13. **Tests:** illegal-transition raises; fill→trade; event emission.

### 5.3 `OptionChain`
`src/domain/aggregates/option_chain.py:18`, `src/domain/entities/options.py:101`, `src/domain/options/option_chain.py`.
1. **Responsibility:** `OptionChainAggregate` wraps immutable `OptionChain` VO, adds ATM/ITM/OTM queries.
2. **Correct?** Yes — rich, query-only, immutable snapshot.
3. **Problems:** `greeks` carried as `dict` in `OptionLeg` (`entities/options.py:53`) not `Greeks` VO; `spot` may be `None` silently; `to_dict/from_dict` mixes serialization into entity.
4. **SOLID:** O — queries are pure functions (good); but `OptionLeg.greeks: dict` breaks type safety.
5. **DDD:** aggregate identity `(underlying,expiry)` correct; value stays immutable.
6. **Arch smells:** dict greeks vs `Greeks` VO dual model.
7. **Code smells:** serialization coupled to entity.
8. **Action:** **KEEP**; replace dict with `Greeks` VO; move `to_dict/from_dict` to `serialization.py`.
9. **New package:** `src/domain/options/`.
10. **Collaborators:** `OptionChain` VO, `OptionStrike/Leg`, `Greeks`, `DataProvider`.
11. **Public API:** `atm_strike/itm_calls/otm_calls`, `strikes/spot`.
12. **Internal:** pure queries over tuple.
13. **Tests:** ATM selection, ITM/OTM partitioning, immutability.

### 5.4 `src/domain/indicators/indicators.py` — domain → plugins violation (§1)
1. **Responsibility:** thin indicator facade.
2. **Correct?** No — imports `plugins.indicators.*`.
3. **Problems:** domain depends on a sibling top-level package (wrong direction).
4. **SOLID/DDD:** DIP violated; domain leaks upward.
5. **Action:** **MOVE** indicators into `src/domain/analytics/indicators/` (or fold `plugins/indicators` definitions into domain); delete `plugins/indicators` ad-hoc code.
6. **Collaborators:** `Indicator` ABC, `IndicatorRegistry`.
7. **Public API:** `IndicatorSet.compute(series)`.
8. **Tests:** each indicator vs known values; property tests for rolling windows.

---

## 6. Consolidated action table (keep / move / merge / split / delete / redesign)

| Component | Verdict | Destination |
|-----------|---------|-------------|
| `src/domain/instruments/*` (`Instrument` family) | **KEEP + extend** | `src/domain/instruments/` |
| `src/domain/options/greeks.py` (Greeks VO) | **KEEP** | `src/domain/options/` |
| `src/domain/aggregates/*` (order/position/account/option_chain) | **KEEP** | `src/domain/aggregates/` |
| `src/domain/trading/{order,position,portfolio}.py` | **DELETE** (dup of aggregates) | — |
| `src/domain/entities/instrument.py` `InstrumentRecord` | **MOVE** → broker-adapter layer | `src/infrastructure/brokers/...` |
| `src/domain/indicators/indicators.py` | **MOVE** into `src/domain/analytics/indicators` | `src/domain/analytics/` |
| `brokers/*/gateway.py` (5 facades) | **SPLIT + REDESIGN** → transports behind `src/domain/ports` | `plugins/<broker>/` |
| `brokers/common/intelligent_market_gateway.py` | **REDESIGN** → decorator | `src/domain/...` decorator |
| `brokers/common/stream_orchestrator.py` | **SPLIT** (session/router/failover/health) | `brokers/common/streaming/` |
| `brokers/common` ~15 `if broker==` sites | **REPLACE** with capability/strategy | `src/domain/capabilities` |
| `application/oms/_internal/risk_manager.py` | **MOVE** → `src/domain/risk/` | `src/domain/risk/` |
| `application/oms/order_manager.py` (709) | **SPLIT** into workflows | `src/application/oms/` (thin) |
| `application/portfolio/portfolio_service.py` (PnL) | **MOVE** → `PortfolioAggregate` | `src/domain/portfolio/` |
| `infrastructure/retry.py`, `alerting.py`, `global_exception_handler.py` | **REPOINT** to `src/domain` (lift `TradeXV2RecoverableError` → `src/domain/errors.py`) | `src/infrastructure/` |
| `plugins/indicators/*` | **DELETE** (fold into domain) | — |
| `src/__init__.py` | **ADD** public facade | `src/` |
| 12 missing target sub-packages | **ADD** (scanners, exchanges, sessions, risk, analytics, accounts, portfolio, positions, futures, quotes, factories, specifications) | `src/domain/` |

---

## 7. What is genuinely good — preserve, do not "delete everything"

- `src/domain/instruments/instrument.py` **Instrument family** — the target shape (rich, broker-free, emits events). Reuse as the template for every other aggregate.
- `src/domain/options/greeks.py` **Greeks frozen VO**.
- Frozen VOs: Quote, Tick/Trade, Candle (`HistoricalBar`), Money, OptionChain, Order.
- `src/domain/events/types.py` rich typed event catalog (wire the silent aggregates to emit).
- `src/domain/ports/*` ISP ports; `src/domain/capabilities.py` + `capability_manifest.py` (capability model — the antidote to `if broker==`).
- `src/domain/extensions/{base,registry}.py` Decorator/extension registry (seed for depth-20/30/200 decorators).
- `src/domain/repositories/*` domain ports.
- Fitness tests + import-linter (extend to enforce the new `src/` boundaries).

---

## 8. Recommended next build slice (unchanged from roadmap: Instrument object model)

Phase 1 from `ASSESSMENT_AND_ROADMAP.md` is still the right first slice — but now
build it **under `src/domain`** and add the missing `src/domain/{risk,portfolio,positions,exchanges,sessions,scanners,factories,specifications}` packages as you go. Concretely:
1. Add `Execution` aggregate + wire `OrderAggregate`/`OptionChainAggregate` to emit the already-defined events.
2. Freeze `MarketDepth`/`HistoricalSeries`/`SubscriptionState`; delete `trading/` duplication.
3. Move `risk_manager` + `portfolio_service` PnL into `src/domain` (closes P2).
4. Repoint `infrastructure` to `src/domain` ports; lift `TradeXV2RecoverableError` to `src/domain/errors.py` (closes P3).
5. Add `src/__init__.py` facade + contract tests every `plugins/<broker>` must pass.

This re-review confirms the migration started well on the domain surface; the
remaining work is structural (gateways→transports, business rules→domain, layer
repointing, missing sub-packages) — not a rewrite.
