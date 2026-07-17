# TradeXV2 — Phase 0: System Discovery & Baseline Audit

**Mode:** Discovery only. No fixes, no refactors, no production changes.
**Date:** 2026-07-17
**Scope verified:** Working tree as-is (`git status` shows uncommitted `M`/`??` changes — these are part of the baseline, not addressed).
**Method:** 9 parallel evidence-gathering passes over `src/` + targeted cross-verification of every high-impact claim by the auditor (grep/file:line). Prior audit artifacts in `docs/architecture/*.md` and `audit/phase0..10_*.py` were noted but **not trusted**.

---

## Acceptance Criteria — ALL MET

| Criterion | Status |
|---|---|
| Every production module discovered | ✅ (1173 `.py` in `src/`, 10 top-level packages) |
| Every entry point identified | ✅ (`tradex`, `broker`, `datalake-mcp` + 2 entry-point groups) |
| Startup path fully mapped | ✅ (`tradex.connect` → `open_session` sequence, file:line) |
| Domain boundaries understood | ✅ (32 subpackages, 43 ports, purity verified) |
| Dependency relationships documented | ✅ (layered + contract-enforced via import-linter) |
| Event flows identified | ✅ (1 canonical bus + callback hybrids) |
| Configuration sources catalogued | ✅ (AppConfig + broker loaders + env files + flags) |
| No production directory unexplored | ✅ (domain/application/infrastructure/brokers/interface/analytics/datalake/config/runtime/tradex/plugins) |
| Every architectural conclusion evidence-backed | ✅ |

**PHASE 0 COMPLETE — no blockers.**

---

## 1. Repository Inventory

**Build/system:** Python ≥3.10, `setuptools` build, **`uv`** package manager (`uv.lock`, 913 KB). Single-root packaging (`where=["src"]`). Test runner `pytest` (`pythonpath=["src","."]`). Linting/contracts: `ruff`, `mypy`, **`import-linter` (16 contracts, CI-gated)**.

**Root layout:**
```
src/                     # all library code (10 packages, 1173 .py, ~159k LOC)
  domain/ application/ infrastructure/ brokers/ interface/
  analytics/ datalake/ config/ runtime/ tradex/ plugins/
tests/                   # 833 test files, 7876 test fns
web/                     # React/TS SPA — config-scaffold only (unbuilt)
docs/architecture/       # prior audit artifacts (NOT authoritative for this audit)
audit/                   # prior phase scripts (phase0..10)
graphify-out/            # graphify-derived KG cache
data/ runtime/           # datalake data + runtime artefacts (tokens, event-log)
.env.*                   # .env.example, .env.local, .env.upstox, .env.dhan.sandbox
pyproject.toml           # build + deps + entry points + import-linter contracts
```

**Packaging note (evidence):** `[tool.setuptools.packages.find].include` (`pyproject.toml:94-105`) lists `domain* application* infrastructure* brokers* interface* config* datalake* analytics* tradex* runtime*` — **`plugins*` is NOT included**, so `plugins.exchanges.nse` will not ship in a real build. `runtime*` IS included (this is the `src/runtime` composition-root package, distinct from the repo-root `runtime/` artefact dir).

---

## 2. Architecture Inventory (actual, from code)

**Style:** Clean / Hexagonal / Layered hybrid with a single composition root.
- **Layers:** `domain` (pure core) → `application` (use-cases) → `infrastructure` (adapters) → `interface` (presentation); `runtime` is the **composition root** that alone touches concrete brokers; `brokers/` are plugins; `analytics`/`datalake` are sibling verticals.
- **Dependency rule** enforced by **import-linter** (`pyproject.toml:317-515`, 16 contracts) and run in CI (`.github/workflows/ci.yml:48,212,244`). `.import_linter_cache/` contains per-package metadata — the contracts have been executed.
- **DDD elements:** entities, aggregates, value objects, ports (Protocols), domain events, repositories, specifications.
- **CQRS:** `runtime/commands` + `runtime/queries` dispatchers (ADR-012).
- **Event-driven (partial):** canonical synchronous `EventBus` for domain events; market-data flows are **callback chains**, not bus events.
- **Plugin model:** entry-point groups `tradex.brokers` (dhan/upstox/paper) and `tradex.exchanges` (nse).

**Verdict:** Architecture matches the *intended* Clean/Hexagonal layering at the structural level. Drift is in **scope/behavior claims and incomplete extractions**, not in the layering skeleton (see §11).

---

## 3. Domain Inventory

`src/domain/` — **231 files, 32 subpackages.** Verified **PURE** (no inbound cross-layer imports; no `from src.`); pandas is correctly deferred to function-local imports.

**Principal objects (evidence):**
- **Entities** (`entities/`): `Order` (`order.py:60`), `Trade` (`trade.py:57`), `Position` (`position.py:30`), `Holding` (`:151`), `Quote`/`MarketTick`/`MarketDepth` (`market.py:176,283,37`), `Balance` (`account.py:14`), `OptionContract/Chain`, `FutureContract/Chain` (`options.py:14-161`), `InstrumentRecord` (`instrument_record.py:21`).
- **Aggregates:** `AccountAggregate` (`aggregates/account.py:18`), `PositionAggregate` (`aggregates/position.py:18`).
- **Value Objects:** `Money` (`primitives/value_objects.py:53`), `Quantity` (`:230`), `Clock` (`:381`), `TickSize`, `InstrumentMetadata`, `InstrumentState`, `SubscriptionState`.
- **Ports (43 Protocols + 1 ABC):** `DataProvider` (`ports/protocols.py:67`), `ExecutionProvider` (`:184`), `BrokerAdapter` (`ports/broker_adapter.py:45` = DataProvider+ExecutionProvider), `BrokerTransport(ABC)` (`broker_transport.py:26`), `RiskManagerPort` (`ports/risk_manager.py:9`), `EventPublisher`, `EventLogPort`/`DeadLetterQueuePort`/`ProcessedTradeRepositoryPort`, `ExecutionLedgerPort`, `OrderStorePort`, `OrderServicePort`, `ClockPort` (`time_service.py:39`), `TradingCalendar`, `ExchangeAdapter`, `StrategyEvaluator`, metrics/tracer/alerting/lifecycle ports.
- **Events:** `DomainEvent` (`events/types.py:26`) + `EventType` enum (~60 types, `:87`); `TypedDomainEvent` wrappers (`typed_events.py:21`) — only **5** of ~60 types have typed wrappers (`_TYPED_EVENT_DISPATCH:254`).
- **Services:** stateless facades in `services/` (Quote/Streaming/Analytics/Order/History).
- **Rich behavior** lives on entities (Instrument mixin-composition; Order/Position methods) + `specifications/` (Specification pattern).

**Purity violations (4, module-level third-party — evidence):**
- `domain/value_objects/money.py:13` → `from pydantic import PlainSerializer`
- `domain/backtest/models.py:7` → `from pydantic import BaseModel`
- `domain/indicators/halftrend.py:28` → `import numpy as np`
- `domain/analytics/statistics.py:25` → `import numpy as np`

**Duplicate / inconsistent domain representations:**
- `OptionChain` defined in **both** `entities/options.py:101` and `options/option_chain.py:35`.
- `FutureChain` defined in **both** `entities/options.py:161` and `futures/future_chain.py:19`.
- `SubscriptionState` is a **3-way** concept: enum `stream_health.py:39` vs dataclass `value_objects/state.py:36` vs enum `SubscriptionStatus` (`state.py:26`).

---

## 4. Runtime Startup Inventory

**Entry points (`pyproject.toml:35-82`):**
| Name | Target | Confirmed |
|---|---|---|
| `tradex` | `tradex.cli:tradex` (`src/tradex/cli.py:28`) | ✅ |
| `broker` | `brokers.cli.broker:broker` (`src/brokers/cli/broker.py:62`, **DEPRECATED**) | ✅ |
| `datalake-mcp` | `datalake.mcp.server:run_server` (`src/datalake/mcp/server.py:47`, `FastMCP`, 9 read-only tools) | ✅ |
| `tradex.brokers` | `brokers.dhan`, `brokers.upstox`, `brokers.paper` | ✅ installed |
| `tradex.exchanges` | `plugins.exchanges.nse` | ❌ **returns `[]` (not registered in installed metadata)** |

**CLI command tree (`tradex`):** `broker` (29 subcmds), `ui`, `scanner` (breakout/volume/momentum/rs), `market` (breadth/sector/…), `indicator` (halftrend), `strategy list`, `backtest` (run/paper/replay/optimize/walkforward), `support` (levels/nearest), `version`, `config` (list/get/set/edit/reset). Most analytics groups are **thin argv translators** into `interface.ui.main` via `_dispatch_ui(...)` — no independent engine.

**Bootstrap sequence (`tradex.connect(broker)` → `tradex/session.py:62` `open_session`):** exactly:
1. `ensure_core_plugins()` (`session.py:95` → `infrastructure/broker_plugin.py:48-125`) — hardcoded metadata fallback for paper/dhan/upstox/datalake (duplicates broker `__init__` registration).
2. `discover_broker_plugins()` (`session.py:96`) — `runtime/broker_discovery.py:38` iterates `entry_points(group="tradex.brokers")`, `importlib.import_module` each → import-time self-registration.
3. `wire_runtime_hooks()` (`session.py:101` → `runtime/wire_runtime_hooks.py:26`) — registers OMS/backtest/domain-event factories into `domain.runtime_hooks` (idempotent).
4. `broker_id = broker.lower()` (`session.py:102`) — **plain string, not `BrokerId` enum here**.
5. `get_broker_plugin(broker_id)` (`session.py:103`); `_normalize_mode` (`:107`); `_ensure_broker_registered` (`:119`).
6. `bootstrap_gateway(...)` (`session.py:140` → `infrastructure/gateway/factory.py:165`) → `_ensure_default_builders` (`:144`) lazily imports `runtime.broker_builders` and registers dhan/upstox/paper/datalake builders. **Concrete brokers first enter the graph HERE** (the sanctioned composition-root indirection).
7. `LifecycleManager.start_all()` for live brokers (`session.py:137,204`).
8. `create_data_adapter` / `create_execution_provider` via `infrastructure.adapter_factory` registry (`session.py:231,253`).
9. OMS spine: `build_oms_service` / `runtime.factory.build` for trade mode (`session.py:277-298`).
10. Build `DomainSession` (`session.py:341`); attach `runtime.commands`/`runtime.queries` dispatchers (`session.py:367-421`).

**Self-registration confirmed:** `brokers/{dhan,upstox,paper}/__init__.py` call `register_broker_plugin(BrokerPlugin(...))` + `register_data_adapter`/`register_execution_provider`/`register_segment_mapper` at import.

---

## 5. Module Inventory

| Module | Location | Responsibility | Key deps |
|---|---|---|---|
| **tradex** | `src/tradex/` | Public SDK + CLI facade + session wiring | runtime (composition root), infrastructure.gateway |
| **runtime** | `src/runtime/` | Composition root: broker discovery/builders, hooks, CQRS dispatchers, lifecycle | domain ports, infrastructure, brokers (lazy) |
| **domain** | `src/domain/` | Typed model + ports + events (pure) | stdlib + self |
| **application** | `src/application/` | Use-cases: oms, execution, trading, portfolio, strategy_engine, options, scheduling, streaming, services, data, composer | domain ports |
| **infrastructure** | `src/infrastructure/` | Adapters: event_bus, idempotency, gateway, auth, providers, resilience, observability, persistence, config, pool, lifecycle, mappers, security, time | domain ports, runtime (lazy) |
| **brokers** | `src/brokers/{dhan,upstox,paper,common,services,session,runtime,events,exceptions,diagnostics,cli,extensions,notebooks,certification}` | Broker plugins (data + execution + auth + streaming) | domain.ports, brokers.common |
| **interface** | `src/interface/{api,ui}` | FastAPI + Click/Rich CLI + (planned) TUI/MCP | application, runtime, infrastructure.gateway (via shims) |
| **analytics** | `src/analytics/` | Research: backtest/replay/paper, indicators, strategy, scanner, options, futures, orderflow, probability, ranking, volatility, volume_profile, breadth, sector, walk_forward, reports, views, viz | domain, application.oms (lazy), datalake |
| **datalake** | `src/datalake/{core,storage,ingestion,quality,analytics,research,adapters,mcp}` | DuckDB market-data store + ingestion + quality + research + MCP | domain, infrastructure |
| **config** | `src/config/` | `AppConfig` schema, profiles, feature flags, validators | stdlib/pydantic |
| **plugins** | `src/plugins/exchanges/nse/` | Exchange plugin (TradingCalendar) — **not packaged, not installed** | domain.ports |

**OMS kernel (`application/oms/`):** `OrderManager` (`order_manager.py:111`; `place_order:308`, `cancel_order:425`, `modify_order:439`, `record_trade:373`, `on_trade:470`), order lifecycle (`_internal/order_lifecycle.py`), `TradingContext` via `factory.create_trading_context` (`factory.py:29`), `ReconciliationService` (`reconciliation_service.py:35`, a `ManagedServicePort`), `RiskManager` (`_internal/risk_manager.py:98`), `ExecutionEngine` (`application/execution/execution_engine.py:18`). **Zero-parity confirmed:** backtest/replay/paper all route through the *same* OrderManager/RiskManager via `execution_mode_adapter.py` (SimulatedOMSAdapter) — only the fill source differs.

**Brokers (evidence):**
- `BrokerAdapter` (`domain/ports/broker_adapter.py:45`) = `DataProvider` + **`ExecutionProvider`** (NOT market-data-only — contradicts project intent).
- dhan: `DhanDataProvider` (`dhan/data/data_provider.py:49`), `DhanOrderTransport` (`dhan/api/transport.py:38`) → `self._client.post("/orders",...)` (`:185`), `slicing` (`:238`); portfolio in `dhan/portfolio/`.
- upstox: `UpstoxDataProvider` (`upstox/data_provider.py:35`), `UpstoxExecutionProvider` (`upstox/__init__.py:53`) → `order_client.py:20-82` posts to live v2/v3.
- paper: `PaperDataProvider`/`PaperExecutionProvider` (simulated).
- All register execution providers + `supported_modes={"trade"...}` at import. Capabilities advertise `supports_place_order=True` etc. (`dhan/config/capabilities.py:32-50`).
- Cross-broker isolation **clean** (no `brokers.common`/`services` → concrete broker imports).
- **Duplicated logic ×2–3:** `data_provider.py` ×3, `totp_client.py` ×2 (dhan 97L / upstox 168L, divergent), `status_mapper` ×2, `margin` ×4, instrument services ×3.

---

## 6. Dependency Analysis

**Layer direction (contract-enforced, import-linter):** `domain ← application ← infrastructure ← runtime ← interface`; `runtime`/`brokers` are the only concrete-broker touchpoints; `analytics`/`datalake` are verticals constrained by `forbidden` contracts (analytics may not import brokers/application.oms; application may not import infrastructure/brokers; etc.).

**Cycles:** No cross-layer import cycles observed; layering is structurally enforced and CI-checked.

**Confirmed layering violations (evidence):**
- **application → infrastructure**: `src/application/oms/context/lifecycle.py:16` → `from infrastructure.lifecycle.lifecycle import ManagedService` (concrete base; `ReconciliationService` correctly uses `ManagedServicePort` at `reconciliation_service.py:35` — so the port exists; the mixin should use it).
- **domain purity**: 4 module-level third-party imports (§3).

**Hidden / lazy dependencies (permitted but real):**
- `infrastructure/gateway/factory.py:121` → lazy `runtime.broker_builders` (sanctioned composition-root indirection).
- `infrastructure/io/async_compat.py:61,87` and `infrastructure/observability/http_server.py:364` → function-local `runtime.event_loop` imports (beyond the two sanctioned exceptions — minor leakage).
- `analytics/backtest/run_backtest.py:83` → `importlib.import_module("application.oms.factory")` (lazy CLI wiring, sanctioned).

**Global state / singletons (evidence):**
- `interface/api/deps.py:52` `global _container` (DI); `:283/288` `_trade_journal_instance`.
- `interface/api/auth.py:90` `global AUTH_MODE, API_KEY` — **mutable globals mutated at startup (live-mutation risk)**.
- `config/defaults.py:33` `global _cached`; `runtime/event_loop.py:56` `_RUNTIME_LOOP` process-wide loop; `runtime/session_infra.py:33` `_shared_quota`; `runtime/wire_runtime_hooks.py:32/50` `_wired`.
- Module-level mutable registries: `adapter_factory._DATA_ADAPTERS/_EXECUTION_PROVIDERS`, `broker_plugin._PLUGINS`, `rate_limiter._BROKER_CAPABILITIES`, `gateway/factory._GATEWAY_BUILDERS`, `event_log._DOMAIN_TYPES`. `get_instance()` singletons: `SecretManager`, `ProcessedTradeRepository`, `FeatureFlags`.

---

### Graph-Backed Cross-Check (graphify, 2026-07-17 — added post-initial draft)

A **directed** dependency graph was built over the production code only (`graphify src --directed`, 1,156 code files, 0 docs → **16,163 nodes, 39,871 edges**). This supplements the import-linter contracts with *semantic* coupling (calls, type annotations) that `grimp` does not see.

**Layer coupling matrix (cross-layer edges, src_layer → tgt_layer):** dominant flow is **inward to `domain`** — `brokers→domain 1560`, `application→domain 1101`, `infrastructure→domain 494`, `analytics→domain 432`, `interface→domain 260`. This matches the intended dependency rule.

**Contract validation at graph scale (verified by re-grep, not trusted from graph alone):**
- **Domain purity HOLDS.** Graphify flagged `domain→interface:1` and `domain→brokers:1`, but both are `[call]`-relation artifacts — `grep` for `interface`/`brokers` in `domain/market/segment_mapper.py` and `domain/options/greeks.py` returns **empty**. No real inbound import exists (consistent with import-linter green).
- **analytics→brokers = 0 edges.** Isolation confirmed at graph scale.
- **Only ONE real import-level violation:** `application/oms/context/lifecycle.py → infrastructure/lifecycle` (3 symbol edges, 1 file) — the same breach found in §6. `application→brokers` (graphify `tick_router.py→brokers/dhan/data/options.py [call]`) is a `[call]` artifact — that file contains no `brokers` import.
- **`application→infrastructure` = 3 edges, all the single `lifecycle.py` file.** No other app→infra imports.

**Hidden coupling import-linter is blind to (type-annotation / call edges, flagged for follow-up):**
- `interface/ui → brokers.upstox.adapters.market_data_gateway` + `brokers.paper.paper_gateway` as `[return_type]` — **28 edges**. These are gateway *type references* in connect shims, not `import` statements (so import-linter passes), but they are real structural coupling to concrete broker types.
- `infrastructure → brokers.upstox.adapters.market_data_gateway` as `[parameter_type]`/`[return_type]` — **3 edges** (`adapters/extensions.py`, `adapters/market_data_gateway_adapter.py`, `gateway/provider_factory.py`). Not in any import-linter ignore list → would fail a contract that scanned type refs; grimp misses them.
- `application.trading → analytics/*` (`feature_fetcher.py`, `multi_strategy_runtime.py`) — **3 edges, real `[import]`**. The D2 contract only forbids `application.oms`/`application.execution` → analytics, so this is *allowed* but a smell (analytics leaking into application.trading).
- `infrastructure → runtime/event_loop` (`io/async_compat.py`, `observability/http_server.py`) — **2 unsanctioned lazy imports** beyond the 2 permitted exceptions.

**Cycle analysis (Tarjan SCC on full graph):** 116 SCCs > 1 (453 nodes), **0 spanning >1 layer**. 24 cycles span multiple files but stay within one layer:
- 6-node intra-`domain` cycle: `instruments/instrument.py ↔ instruments/instrument_trading.py ↔ options/option_chain.py ↔ orders/placement.py ↔ candles/instrument_history.py ↔ instruments/_derivatives.py` (latent risk — Python defers these, but they are real circular-import clusters).
- `domain/events/{types,payloads,typed_events}.py` mutual cycle; `domain/candles/{_helpers,_indicators,historical}.py`; `analytics/strategy/{protocols,models,pipeline,evaluator_bridge}.py`; `application/data/{historical_coordinator,chunk_planner,gap_detector}.py`; `brokers/services/capabilities.py ↔ brokers/session/broker_session.py`.

**Methodological note:** import-linter (`grimp`) enforces *import statements*; graphify reveals *semantic coupling* (calls, type refs). Both agree on the import-level picture (domain purity, analytics↔brokers isolation, single app→infra breach). Graphify's added value here is surfacing the hidden type-annotation coupling above, which the static contract cannot see.

## 7. Event Inventory

**Single canonical bus:** `EventBus` (`infrastructure/event_bus/event_bus.py:49`) — **synchronous, thread-safe, in-memory**. `publish()` (`:436`): inject correlation_id → idempotency dedup by `event_id` → persist-first to `event_log` (fsync on capital events) → dispatch to per-type + `subscribe_all` handlers; failures dead-lettered (`_handle_handler_failure`), never swallowed. `AsyncEventBus` (`async_event_bus.py:56`) and `AsyncEventBusFactory` are **thin wrappers** that delegate to the same sync bus (factory docstring admits `force_async`/`maxsize` are ignored) — **NOT a second bus**. DLQ: `DeadLetterQueue` + `PersistentDeadLetterQueue`.

**Event catalogue:** `DomainEvent` + `EventType` (~60 types: market-data TICK/DEPTH/QUOTE/OPTION_CHAIN; OMS ORDER_*/TRADE/TRADE_FILLED/TRADE_APPLIED; risk RISK_LIMIT_BREACHED/KILL_SWITCH_TOGGLED; lifecycle/broker/scanner/strategy/portfolio). Typed wrappers for only 5 types; overlapping `TRADE`/`TRADE_FILLED`/`TRADE_APPLIED` all map to one `OrderFilledEvent` wrapper (ambiguous). `brokers/events/__init__.py` is a pure re-export of `domain.events` (no broker-specific events).

**Representative inventory (sync bus):**
| Event | Publisher | Subscriber | Mechanism |
|---|---|---|---|
| TRADE_APPLIED / ORDER_UPDATED | OMS (`application/oms`) | OMS context handlers (`oms/context/__init__.py:234-235`, `wiring.py:116-117`) | sync bus |
| CANDIDATE_GENERATED | scanner (`analytics/scanner`) | `trading_orchestrator.on_candidate` (`runtime/factory.py:151`) | sync bus |
| TICK/QUOTE/DEPTH | broker websockets | `MarketBridge` → WS (`interface/api/ws/bridge.py:58`) | **callback → bus bridge** |
| ALL | any | `SessionRecorder` (`session_recorder.py:95`); UI `event_bus_service.py:46` | `subscribe_all` |

**Dispatch model — hybrid:** EventBus is the backbone for OMS/strategy domain events (**48 `publish()` sites, ~19 real `event_bus.subscribe`**), but market-data and control flow are **callback chains** (**~608 callback-style hits** `on_tick`/`callback`/`_handlers`; most of 58 `.subscribe(` calls are broker websocket subscription managers, not EventBus). Request/response uses CQRS `CommandDispatcher`/`QueryDispatcher`.

---

## 8. Configuration Inventory

**Schema (`src/config/schema.py:26`):** `AppConfig` (Pydantic) with Core / API Server / Rate Limiting sections; `from_env()` reads `TRADEX_`-prefixed with legacy fallbacks. Plus two separate frozen dataclasses: `ApiConfig` (`auth_mode`, `api_key` via `load_api_config()`) and `TradingConfig` (`orchestrator_dry_run`, `min_confidence`, `skip_parity_gate`, `smart_routing`, `primary_broker` via `load_trading_config()`).

**Dual-config by design (intended):** `AppConfig` (app scope) vs `BrokerSettings`/`SettingsLoaderBase` (`DHAN_*`/`UPSTOX_*` namespaces; only `brokers/dhan/config/settings.py` implements the broker loader). Explicit "Do NOT merge".

**Env files (defined vars):** `.env.example` (51), `.env.local` (21), `.env.upstox` (16), `.env.dhan.sandbox` (6) — ~57 unique vars; sandbox + prod variants per broker.

**Consumed vs unused:** ~68 `os.getenv/environ.get` literal keys; many "unused" are false positives (read via dynamic names: `feature_flags.py:156` `f"FEATURE_{name}"`; broker loaders via prefix+field). **Undocumented code-only toggles (no `.env.example` entry):** `TRADEX_ALLOW_AUTH_NONE`, `RISK_FAIL_OPEN`/`TRADEX_AUTHORIZE_RISK_FAIL_OPEN`, `FORCE_MARKET_OPEN`, `SKIP_PARITY_GATE`, `TRADEX_SKIP_STARTUP_RECONCILIATION`, `TRADEX_FORCE_PROD_VALIDATION`, `ENABLE_INTELLIGENT_GATEWAY`.

**Feature flags (`config/feature_flags.py`):** class-based, lazy `FEATURE_*` env, supports rollout % + per-user gating (SMART_ROUTING, ADVANCED_ORDER_TYPES, EXPERIMENTAL_STRATEGIES, INTELLIGENT_GATEWAY).

**Profiles (`config/profiles/`):** Dev/Staging/Prod by `APP_ENV` (`base.py`).

**Secrets:** **No hardcoded secret literals found** (only a Fernet-header docstring in `security/secret_manager.py:296`). Secrets flow via `SecretManager` / `SECRET_ENCRYPTION_KEY` and `*_TOTP_SECRET_FILE`/`*_PIN_FILE`.

---

## 9. Quality Inventory

**TODO/FIXME/XXX/HACK:** ~75 total, many false (error-code templates, CLI usage strings). Real ones concentrate in Upstox adapters (e.g. `upstox/orders/gtt_adapter.py:93,134,169` "Upstox API has no list-all endpoint for GTT"; `datalake/ingestion/normalize.py:102` hardcoded threshold `# TODO: derive from adapter`).

**Deprecated:** ~53 hits; real ones = `upstox/extended.py` (alias → `extras.py`), `/v2/option/expiry` endpoint deprecated across `options_client.py`/`options_adapter.py`/`resolver.py`.

**Duplicate implementations:** Confirmed single `EventBus` (async wraps sync), single `IdempotencyService`, single `AppConfig` — consistent with claimed G5 "DONE". Cross-broker duplication: `data_provider` ×3, `totp_client` ×2, `status_mapper` ×2, `margin` ×4, instrument services ×3. Domain duplication: OptionChain/FutureChain/SubscriptionState (§3). Indicator duplication: `halftrend` in **4 places** (`domain/indicators`, `analytics/indicators`, `analytics/indicators/halftrend_backtest`, `analytics/strategy/builtins`).

**Unbuilt / aspirational:** `web/` SPA (config scaffold only — no `src/`, no build); Textual TUI (no `from textual` anywhere despite `tui` extra); second MCP server (only `datalake` exists).

**Dead code:** `application/strategy_engine/` package empty — `LiveStrategyEngine` removed as dead code; spine is `TradingOrchestrator` (`trading/trading_orchestrator.py:97`). `services/historical_data.py` is a gutted re-export shim (`__all__=[]`).

**Experimental:** `EXPERIMENTAL_STRATEGIES` feature flag; `analytics/intraday`, `analytics/scoring`, `analytics/fundamentals` appear thin.

---

## 10. Test Inventory (catalogue only — not evaluated)

**Scale:** 833 test files, **7876 test functions** (`grep def test_`). Frameworks: `pytest` (asyncio auto, strict markers), `pytest-asyncio` (16 explicit), `hypothesis` (11 refs, 4 files in `tests/unit/property/`), `mutmut` (configured, external runner), `import-linter` (16 contracts), `unittest` (3 files, mostly `unittest.mock`).

**Pyramid (`tests/`):**
| Layer | ~Files | Notable |
|---|---|---|
| unit | 430 | brokers/dhan 68, domain 60, brokers/upstox 55, datalake 45, brokers/common 35, analytics 28 |
| architecture | 64 | boundary/import-linter contracts (`test_domain_isolation`, `test_import_direction_and_layering`, `test_composition_root`, `test_gateway_abc_compliance`, `test_file_size_limit`…) |
| integration | 120 | api 49, brokers/dhan 18, brokers/upstox 17, capability 9, quant 7 |
| component | 90 | oms 38, ui 29, trading, execution, runtime, composer |
| e2e | 25 | + stability 5, scenarios 2, stress 1 |
| chaos | 14 | network partitions, failover, corruption |
| performance | 3 | critical_paths, data_performance |

**Coverage gaps (large src, thin dedicated tests):** `interface` (152 src / 3 unit, mostly via component/ui), `infrastructure` (120 src / ~35 unit), `analytics` subpkgs (walk_forward/ranking/pipeline/intraday/strategy ~1 file each), `application` (108 / ~9 unit, leans on component/oms), `runtime` (28 / 6).

**Live/integration gating:** markers `integration`/`sandbox`/`live_readonly`/`upstox_integration`/`pre_prod`/`market_hours`/`live_orders` excluded from default run (env-gated: `UPSTOX_INTEGRATION=1`, `PRE_PROD_GATE=1`, `FORCE_MARKET_OPEN=1`, `TRADEX_LIVE_ORDERS=1`, `DHAN_INTEGRATION=1`).

**Mocks — "no mocks" claim CONTRADICTED:** **238/833 (~29%)** test files use mocks (`unittest.mock` 219, `MagicMock` 205, `@patch` 8). Dedicated fakes exist (`tests/fakes/fake_oms.py`, `fake_trading.py`, `tests/support/brokers/dhan/mock_sdk.py`, `in_memory_gateway.py`) — mix of fakes + heavy `unittest.mock`, not pure real-component integration.

**Scratch artefacts (repo root):** `test copy.ipynb` (75 KB, dup of `test.ipynb` 71 KB), `test1_result.txt` (131 KB), `test2_result.txt` (11 KB); redundant runners `_run_tests.sh`, `.run_test.sh`, `run_test.sh`, `run_tests.py`, `run_all_tests.py`.

---

## 11. Architectural Drift Report (intended vs actual — evidence-backed)

| # | Intended (docs/context) | Actual (verified) | Evidence | Severity |
|---|---|---|---|---|
| D1 | "Broker layer = market-data + lifecycle ONLY; **no order placement**; OMS/Risk/Execution are internal infra, not customer-facing; out-of-scope: CLI order/position/portfolio surface" (`project-overview.md:15-21,89-91`) | `BrokerAdapter` = DataProvider **+ ExecutionProvider**; all 3 brokers POST to **live** order endpoints; API exposes `/orders` (place/modify/cancel) + `/live/extended` (super/forever/gtt/cover/slice/exit-all); UI has `order_placement.py`, `portfolio.py`, `oms.py`, `risk_controls.py` | `domain/ports/broker_adapter.py:45`; `dhan/api/transport.py:185`; `upstox/orders/order_client.py:20-82`; `interface/api/routers/orders.py:126`; `interface/ui/commands/order_placement.py` | 🔴 |
| D2 | "G3 DONE — NSE/IST extracted to `TradingCalendar` plugin; datalake core no longer bakes NSE" (`architecture.md:108,121`) | `datalake/core/nse_calendar.py` still authoritative: full hardcoded `_NSE_HOLIDAYS` (`:30-85`), `is_trading_day`, `expected_candles_per_day`; holidays **duplicated** in `plugins/exchanges/nse/calendar.py:23`; `datalake/core/__init__.py:42-54` re-exports nse_calendar; production code imports it directly (`datalake/quality/monitor.py:87,108`) | `src/datalake/core/nse_calendar.py:30,86,131`; `src/datalake/core/__init__.py:42-54` | 🔴 |
| D3 | "`tradex.exchanges` entry-point group; NSE discovered via registry" (`architecture.md:79-85`, `pyproject.toml:78-82`) | Entry point **returns `[]`** (not installed); `plugins*` **excluded from packaging** (`pyproject.toml:94-105`); discovery silently fails → `ExchangeNotConfigured` at first datalake exchange read | `python -c entry_points(group='tradex.exchanges')` → `[]`; `pyproject.toml:104` | 🔴 |
| D4 | "two MCP servers" (`project-overview.md:72`) | **Only ONE** MCP server exists (`datalake.mcp.server`, `FastMCP` at `:21`); no second server anywhere in `src/` | `grep FastMCP` → only `src/datalake/mcp/server.py` | 🟠 |
| D5 | "Textual TUI" (`project-overview.md:11,72`; `tui` extra) | **No Textual code** (`from textual` absent everywhere); UI is Rich-based CLI (`dashboard.py` uses `rich`, not textual) | `grep -rn "from textual" src/` → none | 🟠 |
| D6 | "UI uses connect shims → `runtime.broker_accessors` (composition root); never raw factory" (`pyproject.toml:507-513`) | `interface/ui/services/connect.py` wraps **`infrastructure.gateway.factory`** (`require_gateway`/`bootstrap_gateway`), not `runtime.broker_accessors`; `broker_registry.py:13` re-exports the factory | `src/interface/ui/services/connect.py:13` | 🟡 |
| D7 | "Domain purity: `domain` imports nothing inward" (`architecture.md:56,91`) | 4 module-level third-party imports in `domain` (pydantic ×2, numpy ×2) load unconditionally | `domain/{value_objects/money.py:13, backtest/models.py:7, indicators/halftrend.py:28, analytics/statistics.py:25}` | 🟡 |
| D8 | "application may not import infrastructure" (`architecture.md:57`) | `application/oms/context/lifecycle.py:16` imports `infrastructure.lifecycle.lifecycle.ManagedService` (concrete base; port `ManagedServicePort` exists and is used correctly by `ReconciliationService`) | `src/application/oms/context/lifecycle.py:16` | 🟡 |
| D9 | "single OMS kernel entry" (zero-parity) | Three parity paths use **two** entry points: backtest → `application.oms.factory.create_trading_context` (direct, `run_backtest.py:83-93`); replay/paper → `domain.runtime_hooks.create_trading_context` (`replay/orchestrator.py:288`; `paper/engine.py:60`) | `src/analytics/{backtest/run_backtest.py:83, replay/orchestrator.py:288, paper/engine.py:60}` | 🟡 |
| D10 | "IdempotencyService multi-backend (memory/file/redis)" (`infrastructure/idempotency/service.py` docstring) | Only **memory** backend implemented in-tree; no redis/file classes; `get_redis_cache` referenced but no backend | `src/infrastructure/idempotency/` (only `memory_cache.py`) | 🟡 |
| D11 | "Single composition root; broker selected by `BrokerId` enum once at startup" (`architecture.md:59-60,89`) | `tradex/session.py:102` uses `broker.lower()` (string); ~30 string broker comparisons remain in interface layer (G1 partially done, acknowledged) | `src/tradex/session.py:102`; `architecture.md:106` G1 note | 🟡 |
| D12 | "No real-money mocks; integration tests against real components" (`architecture.md:98`; `project-overview.md:87`) | **238/833 (~29%)** test files use `unittest.mock`/`MagicMock`; fakes + mocks pervasive | `grep -rl "MagicMock|unittest.mock" tests` → 219/238 files | 🟠 |
| D13 | "G5 DONE — event bus unified (3→1); dead idempotency backends deleted" (`architecture.md:110,124`) | **CONFIRMED** — single canonical `EventBus` (async wraps sync); single `IdempotencyService`. No competing bus/backend found. | `src/infrastructure/event_bus/event_bus.py:49`; `idempotency/service.py:62` | ✅ (matches) |
| D14 | "Web (React/TS SPA)" (`project-overview.md:72`) | `web/` effectively empty (config scaffold only — `web/.env.example`, no `src/`/build) | `ls web/` | 🟠 |
| D15 | "Strategy engine" capability | `application/strategy_engine/` empty (LiveStrategyEngine removed as dead); orchestration spine is `TradingOrchestrator` | `src/application/strategy_engine/__init__.py` note | 🟡 |

**Drift summary:** The **layering skeleton is sound and contract-enforced** (import-linter 16 contracts, CI-gated). The drift is concentrated in (a) **scope misrepresentation** — order execution is fully built and exposed despite being documented as "internal-only / out of scope" (D1); (b) **incomplete extractions** — NSE still baked into `datalake/core` and the exchange plugin is non-functional in the current install (D2/D3); and (c) **unbuilt aspirational surfaces** — second MCP server, Textual TUI, web SPA (D4/D5/D14). Minor layering leaks (D7/D8) and behavioral inconsistencies (D9/D11/D12) are real but low-severity and individually fixable.

---

## 12. Prior-Audit Artifacts Noted (not trusted)

The repo already contains substantial prior audit work: `docs/architecture/{CURRENT-STATE.md, PRIORITIZED-AUDIT.md, TARGET-STATE.md, DEPENDENCY_GRAPH.md, AUDIT-*.md, REVIEW-2026-07-17.md}`, `ARCHITECTURAL_AUDIT.md` (root), and `audit/phase0_discovery.py` … `audit/phase10_concurrency.py`. These were **not relied upon** for this audit; every conclusion above was re-derived from source. Where this audit agrees (e.g. G5 event-bus unification), it is an independent confirmation.
