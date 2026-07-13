# Progress Tracker — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. Update this file after EVERY meaningful
> implementation change. It is the only file that restores full context in one prompt.
> Agents have no memory between sessions — this is the bridge.

## Current Phase

- Phase 1–4 foundation (per `docs/architecture/roadmap.md`): stabilize contracts, remove
  the 8 gaps (G1–G8), single event bus / idempotency / config, plugin model.

## Current Goal

- Establish the Six-File Context System (this `context/` folder + `CLAUDE.md` + enforcement
  rule) so every future session starts from the same architecture contract.

## Completed

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

- None.

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

- **Await approval** of code-only audit pack before any money-path `src/` changes:
  `docs/architecture/CURRENT_STATE.md`, `AUDIT.md`, `TARGET_AND_MIGRATION.md`.
- On approval: execute **Phase A** from `TARGET_AND_MIGRATION.md` (fail-closed risk,
  required submit_fn, delete Session EP place bypass, Clock on OMS stamps, no phantom
  capital in LIVE).
- Do not start Phase B until Phase A exit tests are green.

## Work Log

### Session: Code-only architecture audit pack
- Date: 2026-07-13
- Reverse-engineered as-built architecture from `src/` + graphify (docs not used as evidence).
- Wrote `docs/architecture/CURRENT_STATE.md`, `AUDIT.md`, `TARGET_AND_MIGRATION.md`.
- P0 findings: null submit_fn success, risk None→allow, Session EP place bypass,
  recon optional/report_only, phantom capital default.
- **No `src/` changes** — waiting for Phase A implementation approval.

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
- Live soak-tested tick feed (LTP/QUOTE/FULL) and depth20 for sustained flow: 90s tick soak,
  102 ticks, zero drops; found and fixed two compounding bugs in Dhan's depth20/200 binary
  WS parser (`brokers/dhan/data/depth_parser.py`) that meant the **ask side of market depth
  never actually flowed live**, only bids:
  1. Dhan batches multiple 332-byte bid/ask sub-packets (alternating `response_code` 41=bid,
     51=ask) concatenated into a single WS frame — confirmed via raw wire capture (80 bid +
     80 ask sub-packets across 39 frames, always paired). `process_binary_message` only ever
     parsed the first 332 bytes of each frame; everything after (always the ask side, since
     Dhan sends bid first) was silently discarded. Fixed by looping over every complete
     sub-packet in the buffer.
  2. Separate, compounding bug: `depth_cache or {}` treated an empty-but-real dict as falsy,
     substituting a throwaway dict on every call where the cache happened to be empty — so
     `feed._depth_cache` never actually persisted mutations across messages, forcing
     `subscribe_depth_20()` to always fall back to REST instead of ever reading the live WS
     cache. Fixed with an explicit `is not None` check.
- New regression tests in `tests/unit/brokers/dhan/test_depth_feeds.py`
  (`test_binary_message_with_concatenated_bid_and_ask_subpackets`,
  `test_binary_message_with_three_concatenated_subpackets`) reproduce both bugs with
  synthetic packets; 23/23 `TestDhanDepth20Feed` tests pass. 16 pre-existing failures in
  `TestDhanDepth200Feed`/`TestGatewayDepth20`/`TestGatewayDepth200` (stale API drift,
  unrelated) confirmed identical with/without the fix via `git stash`.
- Live re-verification after the fix: 60s depth20 soak went from 120 updates/0 asks to 490
  updates with both `bid_levels=20` and `ask_levels=20` populated throughout.

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
