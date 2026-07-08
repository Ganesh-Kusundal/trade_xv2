# TradeXV2 → Institutional Trading Framework (v2.0) — Re-platform Plan

**Strategy:** Re-platform, do **not** delete-and-rebuild from zero. The existing
`domain/` + `markets/` already embody most of the target DDD model; we keep and
harden it, restructure it into the target `src/` package graph, and **delete**
the broker-gateway / manager / service cruft under `brokers/*` by re-expressing
it as plugins that implement domain ports.

**Sequencing:** Bottom-up, domain-first. Each phase deletes its old counterpart
in the same PR — **no transitional layers, no shims, no compat packages**.

**Tests:** Full pyramid at full depth (unit → component → integration → contract
→ e2e → property → performance → stress → mutation).

**Live scope:** Real dhan + upstox connections, including guarded real order
placement (gated by `TRADEX_LIVE_ORDERS=1`).

---

## 0. Architecture principles (hard rules)

1. **Domain does not import infrastructure.** `src/domain/**` imports nothing from
   `src/infrastructure`, `src/plugins`, `brokers`, `requests`, `websocket`, JSON.
2. **Brokers are plugins.** They implement interfaces defined in `src/domain/ports`
   and `src/domain/capabilities`. No `if broker == "dhan"` anywhere in domain/app.
3. **Behavior on objects (Tell, Don't Ask).** `Instrument.quote`, `Option.greeks`,
   `Order.cancel()`, `Position.pnl()`, `HistoricalSeries.resample()`. No
   `*Service` / `*Manager` / `*Helper` with domain behavior.
4. **Composition over inheritance.** An `Instrument` *composes* `Quote`,
   `MarketDepth`, `HistoricalSeries`, `Subscription`, `IndicatorSet`, capabilities.
5. **Immutable value objects.** `Quote`, `Tick`, `Trade`, `Candle`, `OHLC`, `Money`,
   `Price`, `Spread`, `Greeks`, `Session`, `Timeframe`, `MarketSnapshot` are frozen.
6. **Events for collaboration.** Important transitions emit domain events.
7. **Delete, don't deprecate.** Remove dead code, wrappers, facades, old interfaces.

---

## 1. Target package graph (`src/`)

```
src/
  domain/                         # pure finance model — zero infra imports
    instruments/                  # Instrument(base), Equity, Index, Future, Option, InstrumentId
    options/                      # OptionChain, OptionChainLeg, Greeks, VolatilitySurface, PricingModel
    futures/                      # FutureChain
    quotes/                       # Quote, Tick, BidAsk, MarketDepth, MarketSnapshot
    candles/                      # Candle, OHLC, HistoricalSeries (resample/indicators)
    orders/                       # Order, OrderRequest, OrderStatus, BracketOrder, OrderFactory
    executions/                   # Execution, Trade, Fill, OrderResult
    accounts/                     # Account, Balance
    portfolio/                    # Portfolio, Position, PositionPnl, Holdings
    risk/                         # RiskProfile, RiskPolicy, Margin
    analytics/                    # Analytics facade over indicators
    indicators/                   # IndicatorSet, RSI, ATR, MACD, VWAP (property-tested)
    scanners/                     # Scanner, ScannerSpecification
    exchanges/                    # Exchange
    sessions/                     # MarketSession, Session
    events/                       # DomainEvent base + catalog + EventBus
    value_objects/                # Money, Price, Spread, Greeks, Timeframe, Session, CapabilityInfo
    repositories/                 # abstractions: InstrumentRepo, OrderRepo, PortfolioRepo, HistoryRepo
    factories/                    # InstrumentFactory, OrderFactory
    specifications/               # Specification base, TradableSpec, OptionSpec
    capabilities/                 # Capability ABCs + registry (Depth, Bracket, Greeks, Basket, Streaming)
    policies/                     # Policies (order routing, risk, idempotency)
    ports/                        # MarketDataProvider, ExecutionProvider, Subscription ports (protocols)
  application/                    # workflows/commands/queries — coordinates, no business rules
    commands/  queries/  workflows/  orchestration/
  infrastructure/                 # implements domain ports only — no business logic
    brokers/  persistence/  websocket/  rest/  storage/  serialization/
    replay/  cache/  telemetry/  messaging/  auth/
  plugins/                        # concrete broker/provider packages
    dhan/  upstox/  paper/  replay/
  api/                            # FastAPI app exposing domain objects (JSON out, domain in)
  ui/                             # terminal / dashboard (consumer of api or application)
```

Repo root also keeps `tests/` (pytest against `src`), `docs/adr/`, `config/`,
`scripts/`, `datalake/` (tooling, outside `src`).

---

## 2. Domain object model (what each object owns)

| Object | State (value objects) | Behavior |
|---|---|---|
| `Instrument` (agg root) | identity(`InstrumentId`), `InstrumentState`(quote/depth/subscription/last_update/error) | `quote`, `ltp`, `bid`, `ask`, `spread`, `mid`, `history()`, `depth()`, `subscribe()`, `refresh()`, `option_chain()`, `future_chain()`, `capabilities` |
| `Equity`/`Index`/`Future`/`Option` | subtype fields (strike, expiry, right, lot_size, tick_size, underlying ref) | subtype methods (`Option.greeks`, `Future.basis`, `Future.cost_of_carry`) |
| `OptionChain` | underlying, expiry, strikes, spot | `pcr()`, `max_pain()`, `atm`, `calls`, `puts`, `nearest_otm()`, `greeks_surface()`, `subscribe()` (composes underlying + legs) |
| `Quote`/`Tick`/`Trade`/`Candle`/`OHLC` | immutable | `Quote.spread()`, `Candle.resample()`, `HistoricalSeries.indicators()` |
| `MarketDepth` | bids/asks (frozen `DepthLevel`s) | `imbalance()`, `top_of_book()`, `levels(n)` |
| `Order` | immutable id + mutable status via events | `cancel()`, `modify()`, `status` (via `OrderUpdated`) |
| `Position`/`Portfolio` | qty, avg_price, lots | `pnl()`, `realized()`, `unrealized()`, `margin()` |
| `Account` | balances, holdings | `funds()`, `holdings()` |
| `HistoricalSeries` | DataFrame-like of candles | `resample(tf)`, `indicators()`, `rolling(window)` |
| `Scanner` | spec + universe | `run(universe)` → matching instruments |
| `Subscription` | status, handle | `is_active`, `unsubscribe()` |

---

## 3. Capability model (no broker conditionals)

- Domain defines capability **ABCs** in `src/domain/capabilities/`:
  `DepthCapability`, `BracketOrderCapability`, `OptionGreeksCapability`,
  `BasketOrderCapability`, `StreamingCapability`, `OrderUpdateCapability`.
- Plugins implement them: `plugins/dhan/capabilities/depth.py::DhanDepthCapability`
  (wraps existing `DhanDepth20Feed`/`DhanDepth200Feed`), `plugins/upstox/.../depth.py::UpstoxDepth30Capability`
  (full market quote, ~20–30 levels) + `UpstoxFullCapability` (the "new" full feed /
  live greeks — maps to `brokers/upstox/market_data/client_v3.py` + `extended.py`).
- `Instrument` exposes capabilities via `instrument.capabilities` (a
  `CapabilityRegistry` lookup by instrument id) — replaces the old
  `get_extension("depth200")` string API with typed `instrument.capabilities.depth(levels=200)`.
- The existing `domain/extensions/*` code is **moved + renamed** to
  `src/domain/capabilities/*` (the design is already correct; only the package
  and naming change). Old `brokers/dhan/extensions/*` registration code is deleted
  (folded into plugin capability registration).

---

## 4. Event model

Expand `domain/events/` into a full catalog, all immutable:
`QuoteChanged`, `TickReceived`, `DepthChanged`, `TradeExecuted`, `OrderPlaced`,
`OrderFilled`, `OrderRejected`, `OrderCancelled`, `PositionOpened`,
`PositionClosed`, `MarketOpened`, `MarketClosed`, `SubscriptionStarted`,
`SubscriptionStopped`, `HistoricalLoaded`, `ReplayStarted`, `ReplayFinished`.
Objects emit via `EventBus`; UI/analytics/telemetry subscribe. No direct coupling.

---

## 5. Phase plan (each phase = self-contained PR, deletes old code)

### Phase 0 — Scaffold
- Add `src/` package, switch to `src`-layout in `pyproject.toml`, move tests to root `tests/`, update `testpaths`/`markers`.
- Add `docs/adr/` and the 7 ADRs (see §8).
- CI matrix runs unit + contract; live gated.

### Phase 1 — DOMAIN FOUNDATION (keep + harden + reshard)
- Move `domain/**` → `src/domain/**` per §1 graph (mechanical rename + imports).
- `domain/aggregates/instrument.py` → `src/domain/instruments/instrument_aggregate.py` (keep, harden thread-safety).
- `markets/instrument.py` → `src/domain/instruments/{instrument,equity,index,future,option}.py`; `markets/option_chain.py` → `src/domain/options/option_chain.py`; `markets/indicators.py`,`greeks.py` → `src/domain/indicators`, `src/domain/options/greeks.py`.
- `domain/entities/*` → `src/domain/value_objects/*` + `src/domain/quotes`, `src/domain/candles`.
- `domain/providers/protocols.py` → `src/domain/ports/{market_data,execution,subscription}.py`.
- `domain/extensions/*` → `src/domain/capabilities/*`.
- Add **missing** domain pieces: `repositories/` (abstractions), `factories/`,
  `specifications/`, `policies/`, full `events/` catalog + bus, richer value
  objects (`Money`,`Price`,`Spread`,`Greeks`,`Timeframe`,`Session`),
  `capability_registry.py`.
- **Delete** old `domain/` and `markets/` (no compat).
- **Tests:** exhaustive UNIT (real objects, no mocks) for every entity/VO/aggregate/
  spec/policy/factory/event; **property-based** for indicators, pricing, resampling,
  rolling windows, option calcs, risk, PnL.

### Phase 2 — INFRASTRUCTURE PLUGINS (brokers become plugins)
- `brokers/dhan/*` → `src/plugins/dhan/*`: implement `MarketDataProvider`,
  `ExecutionProvider`, and capabilities. Keep the genuine low-level clients
  (`http_client.py`, `websocket/*` decoders, `depth_20.py`/`depth_200.py` feeds,
  `depth_feed_base.py`) as infrastructure; **delete** `gateway.py` (27KB
  `BrokerGateway`), `connection.py`, `connection_lifecycle.py`, `factory.py`,
  `orders.py` facades — they are the manager/gateway cruft.
- `brokers/upstox/*` → `src/plugins/upstox/*`: same; `UpstoxDataAdapter` becomes the
  plugin's `MarketDataProvider`. Add `UpstoxDepth30Capability` + `UpstoxFullCapability`.
- `brokers/paper/*` → `src/plugins/paper/*`; add `src/plugins/replay/*`.
- `brokers/common/*`:
  - `gateway.py`/`gateway_interfaces.py` → **delete** (replaced by `src/domain/ports`).
  - `adapters/*` (shims wrapping gateways into `DataProvider`) → **delete** (plugins implement ports directly).
  - `extensions/*` → already moved to `src/domain/capabilities` in P1.
  - `auth/*`,`resilience/*` → `src/infrastructure/auth`, `src/infrastructure/{rest,websocket}` (rate limiter, circuit breaker, retry).
  - `options/{gateway_facade,chain_normalizer}` → **delete**; normalization lives in `src/domain/options/option_chain.py`.
  - `oms/*` → `src/application` execution workflows (or delete if domain covers).
- `infrastructure/providers/*` → `src/infrastructure/{replay,cache,...}`; `DataFrameDataProvider` kept as a test/replay double.
- **Delete** `brokers/` entirely after migration.
- **Tests:** CONTRACT (every plugin satisfies common market-data/orders/portfolio/
  historical/streaming/capabilities contracts), COMPONENT (repositories, plugins,
  providers, serialization, replay), INTEGRATION (order lifecycle, subscription
  lifecycle, historical loading, market-data sync, recovery, event propagation).

### Phase 3 — APPLICATION LAYER
- `src/application/{commands,queries,workflows,orchestration}`: `PlaceOrderWorkflow`,
  `ScannerWorkflow`, `BacktestWorkflow`, `ReplayWorkflow`, `StartupWorkflow`,
  `RecoveryWorkflow`, `SynchronizationWorkflow`. Business rules stay in domain.
- Rework `application/` → `src/application`; delete old service/manager cruft.
- **Tests:** INTEGRATION + E2E workflows (startup, login, subscription, trading,
  fill processing, portfolio updates, recovery, shutdown, replay, backtest).

### Phase 4 — API + UI + OBSERVABILITY
- `src/api` (FastAPI) exposes domain objects; `src/ui` terminal. `api/`,`cli/` reworked
  to consume `src/api` or `src/application` (remove direct `brokers.*` imports —
  enforces `cli-no-broker-impl` contract cleanly).
- Observability/telemetry → `src/infrastructure/telemetry` + `src/infrastructure/messaging`.
- **Tests:** E2E via API, PERFORMANCE (tick throughput, candle aggregation, historical
  load, scanner latency, memory, replay speed, portfolio scaling, large watchlists,
  option chains).

### Phase 5 — LIVE VALIDATION + HEAVY TESTS
- Real dhan + upstox: `TRADEX_LIVE_TESTS=1` + `CredentialValidator.broker_available()`;
  `certify_broker dhan --live` / `upstox --live` extended with `DEPTH`/`EXTENSIONS`/`LIVE_ORDERS` areas.
- Guarded real orders (`TRADEX_LIVE_ORDERS=1`): 1-lot INTRADAY, marketable→immediate
  cancel, idempotency correlation id, assert cancel before fill assertions, never in CI.
- STRESS (100k ticks/s, 1000 instruments, multiple brokers, large option chains,
  disconnect/reconnect, cache eviction, memory pressure) + MUTATION testing (tests
  verify behavior, not implementation).
- **Delete** any remaining old top-level dirs.

---

## 6. Per-component disposition (major modules)

| Current | Action | New location |
|---|---|---|
| `brokers/common/gateway.py` (`MarketDataGateway`) | **DELETE** | — (domain ports replace) |
| `brokers/common/gateway_interfaces.py` | MOVE/fold | `src/domain/ports` |
| `brokers/common/factory.py` (`BrokerProviderFactory`) | MOVE | `src/infrastructure` or startup |
| `brokers/common/adapters/*` (gateway→DataProvider shims) | **DELETE** | plugins implement ports directly |
| `brokers/common/extensions/*` | MOVE/rename | `src/domain/capabilities` |
| `brokers/common/oms/*` | MOVE | `src/application` (or delete) |
| `brokers/common/options/{gateway_facade,chain_normalizer}` | **DELETE** | normalization in `src/domain/options` |
| `brokers/common/auth`,`resilience` | MOVE | `src/infrastructure/auth`,`src/infrastructure/{rest,websocket}` |
| `brokers/dhan/gateway.py`,`connection*.py`,`factory.py`,`orders.py` | **DELETE** | re-expressed in `src/plugins/dhan` |
| `brokers/dhan/{http_client,websocket,depth_20,depth_200,depth_feed_base}` | MOVE | `src/plugins/dhan` (infra clients) |
| `brokers/dhan/adapter.py` (`DhanDataAdapter`) | MOVE/rewrite | `src/plugins/dhan/market_data.py` |
| `brokers/dhan/extensions/depth20,depth200` | MOVE | `src/plugins/dhan/capabilities` |
| `brokers/upstox/gateway.py`,`broker.py`,`factory` | **DELETE** | `src/plugins/upstox` |
| `brokers/upstox/adapter.py` (`UpstoxDataAdapter`) | MOVE | `src/plugins/upstox/market_data.py` |
| `brokers/upstox/market_data/*`,`websocket/*`,`extended.py` | MOVE | `src/plugins/upstox` (build depth30/full caps) |
| `brokers/paper/*` | MOVE | `src/plugins/paper` |
| `domain/aggregates/instrument.py` | MOVE/harden | `src/domain/instruments/instrument_aggregate.py` |
| `domain/entities/*` | MOVE | `src/domain/value_objects`,`quotes`,`candles` |
| `domain/providers/protocols.py` | MOVE | `src/domain/ports` |
| `domain/extensions/*` | MOVE/rename | `src/domain/capabilities` |
| `domain/value_objects/*` | MOVE/keep | `src/domain/value_objects` |
| `domain/events/*` | MOVE/expand | `src/domain/events` |
| `domain/instrument_id.py` | MOVE | `src/domain/instruments` |
| `domain/historical.py` | MOVE | `src/domain/candles` / `repositories` |
| `domain/requests.py`,`result.py` | MOVE | `src/domain/orders`,`src/domain/executions` |
| `domain/capability_manifest.py` (47KB smell) | **DELETE/replace** | `src/domain/capabilities/registry.py` |
| `markets/instrument.py` | MOVE | `src/domain/instruments` |
| `markets/option_chain.py` | MOVE | `src/domain/options` |
| `markets/registry.py` | MOVE | `src/domain/ports` provider registry / composition root |
| `markets/indicators.py`,`greeks.py` | MOVE | `src/domain/indicators`,`src/domain/options/greeks` |
| `infrastructure/providers/{dataframe,broker,composite}` | MOVE/keep | `src/infrastructure/{replay,cache}` |
| `application/` | REWORK | `src/application` |
| `api/`,`cli/` | REWORK | `src/api`,`src/ui` (no direct broker imports) |
| `analytics/` | MOVE | `src/domain/analytics` or `src/application/analytics` |

---

## 7. Test pyramid → phase map

| Layer | Network | Markers | Phase |
|---|---|---|---|
| Unit (largest) | none | default | P1 |
| Property-based | none | `property` | P1 |
| Component | mock/double | `component` | P2 |
| Contract (per plugin) | mock/double | `contract`,`dhan`,`upstox_integration` | P2 |
| Integration | mock adapter | `integration` | P2–P3 |
| E2E | real (gated) | `e2e`,`live_readonly`,`upstox_live_readonly`,`off_market_safe` | P3–P5 |
| E2E live orders | real (gated) | `live_orders` (needs `TRADEX_LIVE_ORDERS=1`) | P5 |
| Performance | bench | `performance` | P4–P5 |
| Stress | bench | `stress` | P5 |
| Mutation | — | `mutation` | P5 |

Reuse existing markers in `pyproject.toml`; add `live_orders`, `property`,
`component`, `contract`, `performance`, `stress`, `mutation`.

---

## 8. ADRs to author (`docs/adr/`)

1. **ADR-001** `src/` layout & package organization.
2. **ADR-002** Domain ports (`MarketDataProvider`/`ExecutionProvider`/`Subscription`) as the only broker contract.
3. **ADR-003** Capability model — no broker conditionals.
4. **ADR-004** Event-driven domain (catalog + bus).
5. **ADR-005** Brokers as plugins; domain never imports infrastructure.
6. **ADR-006** Deletion strategy — no compat/shim/transitional layers.
7. **ADR-007** Test pyramid & live gating (`TRADEX_LIVE_TESTS`, `TRADEX_LIVE_ORDERS`).

---

## 9. Validation steps

1. `pytest tests/ -m "not integration and not live"` → green unit + property suite.
2. `pytest tests/ -m contract` → every plugin satisfies common contracts.
3. `pytest tests/ -m "integration or e2e"` → order/subscription/historical/recovery flows.
4. `TRADEX_LIVE_TESTS=1 python -m brokers.common.tests.certify_broker dhan --live` and `upstox --live` → pass with DEPTH/EXTENSIONS/LIVE_ORDERS areas.
5. `TRADEX_LIVE_TESTS=1 TRADEX_LIVE_ORDERS=1 pytest tests/live -m live_orders` → real 1-lot orders placed+cancelled, no unintended fills.
6. `pytest tests/ -m "performance or stress"` → throughput/latency/memory budgets met.
7. `pytest tests/ -m mutation` → surviving mutants < threshold.
8. `import-linter` / `pylint` confirm **zero** `domain → infrastructure/plugins/brokers` imports and no `brokers.*` import outside `src/plugins` + `src/infrastructure`.

---

## 10. Risks / open questions

- **Scope:** large; execute strictly phase-by-phase, deleting old code per PR. Mechanical `domain/→src/domain` move (P1) is the highest-churn, lowest-risk step — do it in one PR + full test pass.
- **`capability_manifest.py` (47KB)** is a known smell; replace with registry/discovery in P1.
- **Upstox `depth_30`** returns ~20 levels, not literally 30 — capability id stays `depth_30`; returns what Upstox provides. **"new" feed** = confirm full market quote v3 vs live greeks during P2.
- **Live orders** carry financial/rate-limit risk despite guards — keep behind `TRADEX_LIVE_ORDERS` and document CI never sets it.
- **Import-linter contract** (`cli-no-broker-impl`) must route via `src/api`/`src/application` after P4.
- This plan **supersedes** `brokers/OBJECT_MODEL_PLAN.md` and the earlier
  `.kilo/plans/1783495826423-broker-object-model-plan.md` (those were the
  conservative "build on existing + wire upstox" plans; this is the full re-platform).
