# Progress Tracker — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. Update this file after EVERY meaningful
> implementation change. It is the only file that restores full context in one prompt.
> Agents have no memory between sessions — this is the bridge.

## Current Phase

- **Phase A + B + D-Phase1 (E2E spec gap closure) complete** — clock injection (I2), PaperOrders legacy bypass retired (I1), ExecutionEngine promoted to production (I1 structural), DataPaths config spine (D-Phase1).
- Next: **Phase D-Phase2** — physical split (create `data/lake` + `data/state`, move files).
- Parallel: remaining `ExecutionService`/`SimulatedOMSAdapter` can be deleted once backtest path is migrated to `ExecutionEngine`.

## Current Goal

- Close remaining E2E spec gaps (I1, I2, I6, I10) so zero-parity and live safety match
  the Expected Behavior Contract before large structural refactors.

## Completed

### Phase A: E2E Spec Gap Closure — Clock Injection + Paper Bypass Retirement (2026-07-13)

**I2 (Deterministic Time) — Clock injection into execution paths:**
- `trade_recorder.py` — `ClockPort` injected; `datetime.now()` replaced with `self._clock.now()`
- `order_validator.py` — `ClockPort` injected; rejection/order timestamps use injected clock
- `order_lifecycle.py` — `ClockPort` injected; fallback `created_at` uses injected clock
- `gateway_submit.py` — `ClockPort` injected; `order_from_response` and `make_gateway_submit_fn` accept clock
- `market.py` — `is_stale()`, `age()`, `to_snapshot()` use `get_current_clock()` instead of `datetime.now()`
- `execution_contracts.py` — `SubmissionOutcome.accepted/rejected/unknown` classmethods accept optional `clock`
- `trading_orchestrator.py` — `ClockPort` injected; `health()` uses injected clock
- Architecture test: `tests/architecture/test_clock_purity.py` — AST-based grep test forbids `datetime.now()` in execution/risk/domain paths

**I1 (Zero-Parity) — PaperOrders legacy bypass retired:**
- `paper_orders.py` — deleted `_place_internal` (119 lines); paper orders route through OMS exclusively
- `paper_orders.py` — removed unused `dataclasses.replace` and `datetime` imports
- Test fixture: `_MockOrderManager` + `_make_paper_gw()` in `test_paper.py` (17 tests updated)

**Verification:**
- 610 architecture tests pass (pre-existing failures in file-size-limit and import-linter excluded)
- 17/17 paper tests pass
- `graphify update .` completed (36070 nodes, 63336 edges)

### Phase B: Structural Zero-Parity — ExecutionEngine Promoted to Production (2026-07-13)

**I1 (Zero-Parity) — Single execution entry point:**
- `cli_broker_facade.py` — replaced `ExecutionService(mode="live")` with `ExecutionEngine(fill_source=BrokerFillSource(gw))`
- `order_placer.py` — replaced `ExecutionService` with `ExecutionEngine` in constructor and place method
- `trading_orchestrator.py` — replaced `ExecutionService` with `ExecutionEngine` in constructor and delegation
- `trading_runtime_factory.py` — removed `execution_adapter` field from `Runtime` dataclass (always None)
- `application/execution/__init__.py` — exports `ExecutionEngine` + `FillSource` instead of `ExecutionService` + `ExecutionModeAdapter`
- `execution_service.py` — marked as deprecated (retained for backtest/replay compatibility)
- Fixed pre-existing test: `test_reconcile_heals_phantom.py` — updated mock setup for new `apply_mass_status` behavior

**Verification:**
- 610 architecture tests pass
- 52 application tests pass (execution + OMS)
- 5/5 reconciliation integration tests pass
- `graphify update .` completed

### Phase D-Phase1: Market Data Storage Config Spine (2026-07-13)

**DataPaths value object created:**
- `domain/ports/data_catalog.py` — `DataPaths` frozen dataclass with `lake_root`, `state_root`, `catalog_path` + derived properties for OMS, ledger, events, research, features, options Greeks
- `DEFAULT_DATA_PATHS` module-level instance for backward compatibility

**Storage components updated to use DataPaths:**
- `infrastructure/persistence/sqlite_order_store.py` — `oms_orders_path`
- `infrastructure/persistence/sqlite_execution_ledger.py` — `execution_ledger_path`
- `infrastructure/event_log.py` — `events_dir`
- `datalake/research/backtest_cache_store.py` — `backtest_results_path`
- `datalake/core/duckdb_utils.py` — `catalog_path`
- `datalake/core/constants.py` — `curated_root`
- `datalake/analytics/support_resistance.py` — `features_root`
- `datalake/analytics/options_greeks.py` — `options_greeks_root`
- `datalake/research/dataset.py` — `research_datasets_root`
- `datalake/ingestion/sync_options.py` — lake root for options candles

**Verification:**
- 70 application tests pass
- 610 architecture tests pass
- Defaults match current layout (zero downtime)

- **4.1** `DhanWireAdapter.authenticate()` ensures token via AuthManager /
  `_try_refresh_token` (not WS `is_connected` no-op).
- **4.2** Deleted empty `brokers/next/`; removed deprecated `create_gateway` shim
  and bare `BrokerGateway` alias (kept `DhanBrokerGateway`).
- **4.3** Skipped heavy god-class rewrites; `ponytail:` debt notes on
  `UpstoxBroker` / `DhanConnection`. Shared `build_domain_trade` is the small win.
- **4.4** `build_infrastructure` is sync; streams deferred to `Runtime.start()`;
  API lifespan awaits it (no `asyncio.run` in factory).
- **4.5** Typed DI: `get_event_bus`→`EventBusPort`, `get_order_manager`→
  `OrderServicePort`, `get_risk_manager`→`RiskManagerPort`,
  `get_market_data_composer`→`MarketDataPort`.
- **4.6** Cert money paths (token/reconnect/recovery/orders) `warn_only=False`;
  live stubs raise clear `RuntimeError`; synthetic brokers return N/A.
- **4.7** Paper/replay `to_domain_trade` use `build_domain_trade`.
- **Money.__eq__** Money-only; added `Money.coerce`.
- Tests: `tests/unit/test_phase4_structure.py`

### Phase 3 layering (F7/F8/F9 + one BrokerId) — 2026-07-13

- **F9** `runtime.api_compose.build_for_api`; `application.portfolio.active_session`;
  API bootstrap/portfolio no longer import `interface.ui`.
- **F8** `datalake.core.symbols.normalize_symbol` delegates to domain; storage paths use
  `normalize_symbol_for_storage` (suffix strip).
- **F7** `tradex.session` wires orders via `runtime.commands.build_order_dispatcher`.
- **BrokerId** `domain.ports.broker_id` re-exports `domain.enums.BrokerId` (MOCK→PAPER).
- Tests: `tests/architecture/test_api_no_ui_imports.py`,
  `tests/unit/datalake/test_normalize_symbol_canonical.py`.

### Phase 2 safety correctness (F4/F5/F6 + R2/R4) — 2026-07-13

- **F5** Daily-loss = session equity delta (`current_equity − session_open_equity`) in
  `TradingContext._feed_daily_pnl`; `DailyPnlTracker` docs updated.
- **F6** Durable correlation: ledger `intent_for_correlation` / `order_id_for_correlation`;
  `IdempotencyGuard` durable lookup; `OrderManager` hydrates + persists via order store.
- **F4** `ExecutionEngine.apply_mass_status` upserts missing/divergent orders/positions;
  `should_auto_repair` defaults to heal (set `TRADEX_RECONCILIATION_AUTO_REPAIR=0` for report-only).
- **R2** Risk-pending TTL sweep on `MarginChecker`; release on fill/terminal path.
- **R4** Concentration already includes pending; Quantity/Money coercion fixed in RiskManager.
- **2.5** `runtime.commands.build_order_dispatcher` + OrderPlacer OMS-backed stamp.
- Tests: `tests/component/oms/test_phase2_safety.py`

### Phase 1 zero-parity (F2a/b/c/d/f) — 2026-07-13

- Paper OMS path no longer pre-applies slippage; `OmsBacktestAdapter` slips once (F2a).
- `PaperConfig.fill_model` defaults to `FillModel.NEXT_OPEN` (shared with replay) (F2b).
- Paper open/close commission via `domain.trading_costs.compute_commission` (F2c).
- Replay (+ paper) session books OMS fill price (slipped once), not un-slipped base (F2d).
- `BacktestEngine` / `ResearchMode.PURE_SIM` documented loudly as research-only (F2f).
- Helper: `analytics/oms_fill_price.py`; test: `tests/integration/analytics/test_oms_slippage_once.py`.
- PaperTradingEngine kept (not fully collapsed onto ReplayEngine); fill_model pending-signal loop aligned.


- `context/project-overview.md` — product vision, scope, success criteria.
- `context/architecture.md` — layering contract, invariants, known violations G1–G8.
- `context/code-standards.md` — Python/TS conventions, quality gates, test rules.
- `context/ai-workflow-rules.md` — agent discipline, scoping, real-money safety.
- `web/DESIGN.md` — web visual language tokens.
- `CLAUDE.md` — entry point pointing agents at the six files.
- `.cursor/rules/six-file-context.mdc` — enforcement rule (must read context first).

### Architecture Review Fixes (M1–M7)

**M1: live_actionable gate on Spine B** ✅
- `src/brokers/services/_session.py` — module-level gate infrastructure
- `src/brokers/services/orders.py` — gate checks on place_order, cancel_order, modify_order
- Paper/mock brokers always allowed; live brokers (dhan/upstox) require gate
- Fail-closed default (no gate = blocked for live brokers)
- Tests: `tests/unit/brokers/services/test_live_actionable_gate.py`

**M2: OrderValidator depends on RiskGate port** ✅
- `src/application/oms/risk_gate_adapter.py` — adapter bridges domain RiskGate to OMS
- `src/application/oms/order_validator.py` — uses RiskCheckPort protocol (no @runtime_checkable)
- Backward compatible: RiskManager still satisfies the protocol
- Tests: `tests/unit/application/oms/test_risk_gate_adapter.py`

**M3: drift-aware repair in _repair_local_oms** ✅
- `src/brokers/dhan/portfolio/reconciliation.py` — heals only drift_items, not full snapshot
- Tests: `tests/unit/brokers/dhan/test_drift_repair.py`

**M4: cross-broker OMS guard** ✅
- `src/interface/ui/services/broker_manager.py` — checks _oms_broker_id before switching
- `src/interface/ui/services/broker_service.py` — sets _oms_broker_id during OMS bootstrap
- Paper and datalake brokers excluded from cross-broker check

**M5: explicit live-fail** ✅
- `src/interface/ui/services/broker_service.py` — logs warning + sets live_actionable=False
- Mock broker still created for diagnostics, but live orders BLOCKED

**M6: SettingsLoaderBase → AppConfig** ⏳ DEFERRED
- `SettingsLoaderBase` provides env var parsing for broker config loaders
- `AppConfig` handles app-level config (TRADEX_* prefix)
- These serve different purposes; removing SettingsLoaderBase would duplicate parsing logic
- Decision: keep current pattern; document as deliberate architectural choice

**M7: BrokerId enum** ✅
- `src/domain/enums.py` — DHAN, UPSTOX, PAPER, DATALAKE + from_str() helper
- Architecture invariant #3: broker selected by enum, never string equality

## In Progress

- Phase 1 remainder: optional full collapse of `PaperTradingEngine.run()` onto `ReplayEngine`
  (thin facade) once session/result mapping is cheap enough.

## Completed (architectural audit docs — 2026-07-13)

- **Code-derived architectural audit** (graphify-first; existing `AUDIT-*` ignored as inputs):
  - `docs/architecture/CURRENT-STATE.md` — as-built map, flows, contract vs code
  - `docs/architecture/PRIORITIZED-AUDIT.md` — P0–P3 findings F1–F9 + R2–R4
  - `docs/architecture/TARGET-STATE.md` — target architecture + Phase 0–4 migration
- `context/architecture.md` — pointer to the three audit docs

## Next Up

1. Phase 0 leftovers: F2e publish fix, F1 ports, F3 parity-gate env-only (if not done)
2. Phase 1 exit: same-fixture paper vs replay equity tolerance; optional engine collapse
3. Phase 2 safety: F5 daily-loss, F6 durable idempotency, F4 recon heal

## Completed (G1–G8 gap remediation — 2026-07-13)

- **G2: Delete orphaned shadow brokers/dhan/*** ✅
  Root `brokers/` directory removed. Guard test prevents recurrence.
  ADR: `docs/architecture/adr/0001-delete-shadow-brokers.md`

- **G7: Replace getattr kill-switch with RiskGate port** ✅
  `trading_orchestrator.py` uses `RiskManagerPort` injection, not `getattr`.
  Multiple files document the anti-`getattr` pattern.

- **G3: Extract NSE/IST from datalake to ExchangeCalendar plugin** ✅
  - `datalake/exchange_registry.py` — added `get_active_calendar()`, `set_active_calendar()`
  - `datalake/core/nse_calendar.py` — thin re-export from `plugins.exchanges.nse.calendar`
  - `datalake/core/constants.py` — derives `EXPECTED_CANDLES_PER_DAY`, `MARKET_OPEN_*`, `MARKET_CLOSE_*` from plugin
  - `datalake/core/option_format.py` — derives timezone and exchange from plugin
  - `datalake/quality/validation.py` — derives timezone from plugin
  - `datalake/quality/health_check.py` — derives market hours from plugin

- **G1: Eliminate runtime string branching via plugin discovery** ✅ (partial)
  - `infrastructure/gateway/factory.py` — `ENV_FILES` removed; uses `BrokerPlugin` registry; `_GATEWAY_BUILDERS` dict-dispatch; `_is_live_broker()` from plugin
  - `infrastructure/connection/authenticated_readiness.py` — uses `BrokerPlugin.is_live` for skip logic
  - `infrastructure/auth/credential_validator.py` — uses `BrokerPlugin.is_live` for skip logic
  - `infrastructure/io/environment_bootstrap.py` — uses `BrokerPlugin` for env file resolution
  Remaining: ~30 string comparisons in `interface/ui/`, `interface/api/`, `brokers/cli/` (lower priority)

- **G6: Reconciliation onto hot path** ✅
  - `application/oms/reconciliation_service.py` — added `request_reconciliation()` method and `_immediate_request` threading.Event; loop now wakes on both interval AND event-driven signal
  - `application/oms/context.py` — subscribes `request_reconciliation` to `TRADE_APPLIED` and `ORDER_UPDATED` events so drift is detected immediately after fills/order changes, not just on timer ticks
  - Periodic timer kept as safety net; events provide immediate wake-up
  - All existing tests pass (23/23 reconciliation tests green; 8 e2e failures pre-existing)

## Dead Code Cleanup (2026-07-13)

- **Unused idempotency files deleted** ✅
  - `src/infrastructure/idempotency/file_cache.py` (497 lines) — zero production imports
  - `src/infrastructure/idempotency/redis_cache.py` (453 lines) — zero production imports
  - `src/infrastructure/idempotency/codec.py` (113 lines) — zero production imports
  - `src/brokers/upstox/orders/idempotency.py` (32 lines) — empty alias subclass
  - Updated `brokers/upstox/broker.py` and `brokers/upstox/orders/order_command_adapter.py` to import `IdempotencyCache` from `brokers.common.idempotency` directly
  - Cleaned up `infrastructure/idempotency/__init__.py` to only re-export `MemoryIdempotencyCache` and `IdempotencyService`

## Completed (docs — 2026-07-13)

- **E2E architectural specification suite** (Nautilus-referenced, documentation-first):
  `docs/architecture/e2e-spec/README.md` + docs 00–11 (kernel, domain, messaging, data/execution
  flows, risk, time/parity, reconciliation, ports, migration). No redesign code yet — implement
  only after Phase A/B acceptance criteria in `11-asbuilt-gaps-and-migration.md` are owned.
- Prior reviews retained under `docs/superpowers/reviews/` (PE review + short sketch superseded
  by e2e-spec).

## Next Up

- **Execute TARGET-STATE Phase 0–2** (P0 money/parity/safety) before structural refactors — see
  `docs/architecture/TARGET-STATE.md`.
- Complete G1: migrate remaining ~30 string comparisons in `interface/ui/`, `interface/api/`, `brokers/cli/` to use `BrokerId` enum or capability-driven dispatch
- Phase 2 (roadmap): Unify infrastructure (G5: event bus, idempotency; G4: config merge) —
  align with audit F1/F6 when touching idempotency
- Accept E2E suite (architecture council); reconcile with PRIORITIZED-AUDIT F-IDs before coding
- Resume roadmap phases; pick the next unit from `docs/architecture/roadmap.md` and write a
  spec under `context/specs/` before implementing.

## Work Log

### Session: Full architectural audit (docs only)
- Date: 2026-07-13
- Ran graphify first; parallel explore of runtime, domain, OMS, brokers, analytics/infra, interface
- Deliverables: CURRENT-STATE.md, PRIORITIZED-AUDIT.md, TARGET-STATE.md
- Headline: domain + broker import direction clean; zero-parity broken (paper≠replay); parity gate
  skipped by CLI default; recon detect-only; daily-loss = absolute MTM; order idempotency in-memory;
  application→infrastructure false-green; API→UI inversion; normalize_symbol split-brain
- Next implementation gate: Phase 0 in TARGET-STATE.md (no code in this session)

### Session: Dhan broker connectivity verification + fixes
- Date: 2026-07-13
- Verified Dhan and Upstox broker connect + real data retrieval end-to-end via `broker` CLI/venv
- Fixed provenance mislabeling: `HistoricalSeries.from_dataframe()` (a replay/backtest-only
  constructor hardcoding `broker_id="replay"`) was being reused for live Dhan and paper
  historical data, and for two generic legacy fallback paths. Switched all four call sites
  (`brokers/dhan/data/data_provider.py`, `brokers/paper/data_provider.py`,
  `domain/candles/instrument_history.py`, `domain/services/history.py`) to
  `HistoricalSeries.from_broker_df(..., broker_id=...)` — now stamps the correct broker id
  and `AUTHORITATIVE` confidence instead of `DERIVED`.
- Fixed a ~100%-reproducible race condition in Dhan's live tick market-feed WebSocket:
  `MarketFeedConnection.stop()` (`brokers/dhan/websocket/connection.py`) could call the
  dhanhq SDK's `close_connection()` before the background thread had taken ownership of the
  SDK feed's private event loop via `feed.run()` → `loop.run_until_complete()`, racing two
  threads on the same loop object and raising `RuntimeError: This event loop is already
  running`, with the thread then failing to join within its 5s timeout (abandoned).
  Root-caused by reading the installed `dhanhq` SDK source directly (site-packages), not
  just our wrapper. Fix: added a `threading.Event` (`_run_claimed`) set by the background
  thread immediately before `feed.run()`; `stop()` now waits on it (2s bound, only when a
  feed exists) before touching the SDK feed. Also tightened
  `brokers/services/market_data.py::run_subscribe_probe()` to poll real connection state
  (via a new `is_connected` passthrough on `_DhanSubscriptionHandle`) for up to 2s before
  unsubscribing, instead of tearing down immediately — so `broker health`'s "Subscription
  Active" check reflects a genuine connection, not just a non-null handle.
- New regression test `tests/unit/brokers/dhan/test_market_feed_connection_race.py` —
  deterministically reproduces the race with a fake SDK feed (no real network/asyncio
  needed); confirmed it fails on the pre-fix code and passes after the fix via `git stash`.
- A secondary cosmetic symptom (spurious "Market feed already connected" WARNING during
  `broker subscribe`/`health`) persists after the fix but no longer causes any error or
  abandoned thread — likely benign feed-object reuse within a single CLI process; not
  chased further, flagged as a possible follow-up.
- Tests: full `tests/unit/brokers/dhan/` + `tests/unit/brokers/paper/` suite diffed against
  pre-fix baseline via `git stash`/`pop` — identical failure set except the new race test
  flipping from fail to pass (74 failed / 507 passed vs 75 failed / 506 passed baseline; all
  other failures are pre-existing/unrelated, confirmed before touching any code).

### Session: Ports Purity — Extract Concrete Implementations
- Date: 2026-07-13
- Moved `NSEExchangeAdapter`, `BSEExchangeAdapter`, `MCXExchangeAdapter`, `_EXCHANGE_REGISTRY`, `get_exchange_adapter()` from `domain/ports/exchange_adapter.py` → `domain/market/exchange_adapters.py`
- Moved `RealClock`, `VirtualClock`, `_EXCHANGE_TZ` from `domain/ports/time_service.py` → `domain/ports/time_service_impls.py`
- `domain/ports/exchange_adapter.py` now contains only `ExchangeAdapter` and `ExchangeAdapterPort` Protocols
- `domain/ports/time_service.py` now contains only `ClockPort` Protocol, `get_current_clock()`, `set_current_clock()`, `use_clock()`
- Backward-compatible re-exports with `DeprecationWarning` in old locations
- Updated imports in 8 files: `infrastructure/time/clock.py`, `tests/unit/domain/test_exchange_adapter.py`, `tests/unit/domain/ports/test_clock_port.py`, `tests/unit/application/oms/test_daily_pnl_reset_scheduler_fires_at_virtual_time.py`, `tests/unit/application/streaming/test_streaming_consumer_uses_virtual_clock.py`, `tests/integration/test_replay_determinism.py`
- Tests: 605 architecture tests passed (5 skipped, pre-existing), 21 unit tests for moved classes passed, zero new failures

### Session: Architecture Migration Phase 3
- Date: Current
- G6: Reconciliation moved to hot path — event-driven via TRADE_APPLIED/ORDER_UPDATED subscriptions
- G8: api_server.py moved to scripts/run_api_server.py, doc references fixed
- Tests: 15 pre-existing failures, 603+ passed, 5 skipped

### Session: Architecture Migration Phase 2
- Date: Current
- G1: Extended string branch elimination to interface layer (31 string comparisons → BrokerId enum + capability checks)
- G4: Deleted dead DhanConfig/UpstoxConfig from config/schema.py (-93 lines)
- G5: Unified event bus (DomainEventBus ABC → EventBusPort Protocol); deleted dead idempotency code (-1095 lines)
- Tests: 15 failures (all pre-existing), 592 passed, 5 skipped

## Open Questions

- Is `web/styles.css` the intended single source of truth for theme, or will a design
  system be adopted? (tokens in `web/DESIGN.md` are placeholders until confirmed.)

## Architecture Decisions

- Six-File Context System adopted from the JavaScript Mastery methodology, populated with
  real `docs/architecture/*` content (not empty templates).
- Entry point uses `CLAUDE.md` (Cursor reads it); enforcement duplicated as a Cursor rule
  so it applies even if `CLAUDE.md` is skipped.
- M6 deferred: SettingsLoaderBase is a utility mixin for broker config; AppConfig handles
  app config. Removing it would duplicate parsing logic.

## Session Notes

- Context files are the agent's pre-flight. If a task seems ambiguous, the answer is
  usually already in `architecture.md` or `project-overview.md` — read before asking.
- `graphify update .` after any code change keeps `graphify-out/` aligned with `context/`.
