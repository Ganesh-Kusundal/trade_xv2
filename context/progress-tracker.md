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

## Next Up

- Resume roadmap phases; pick the next unit from `docs/architecture/roadmap.md` and write a
  spec under `context/specs/` before implementing.
- Consider M6 scoping: SettingsLoaderBase serves broker config (not app config) — either
  accept the dual pattern or refactor broker loaders to use AppConfig directly.

## Open Questions

- Is `web/styles.css` the intended single source of truth for theme, or will a design
  system be adopted? (tokens in `web/DESIGN.md` are placeholders until confirmed.)
- Final `broker_id` enum shape for the `tradex.exchanges` plugin group.

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
