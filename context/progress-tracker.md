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

- Complete G1: migrate remaining ~30 string comparisons in `interface/ui/`, `interface/api/`, `brokers/cli/` to use `BrokerId` enum or capability-driven dispatch
- Phase 2: Unify infrastructure (G5: event bus, idempotency; G4: config merge)
- Accept E2E suite (architecture council); then execute Phase A (Order FSM, Clock in fills,
  fail-closed risk, daily-PnL self-heal) per `docs/architecture/e2e-spec/11-asbuilt-gaps-and-migration.md`.
- Resume roadmap phases; pick the next unit from `docs/architecture/roadmap.md` and write a
  spec under `context/specs/` before implementing.

## Work Log

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
