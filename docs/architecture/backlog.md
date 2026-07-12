# Engineering Backlog

> Phase 0 deliverable. Seeds the 8 gaps from `baseline.md` §7 as tracked, actionable
> items. Each maps to a roadmap task and an ADR where applicable. Severity: 🔴 blocker,
> ⚠️ should-fix.

Status legend: `TODO` · `IN_PROGRESS` · `DONE` · `WONT_DO`

---

## G1 — `runtime/` couples to concrete brokers + string branching 🔴
- **Roadmap:** P5-1 · **ADR:** ADR-002
- **Evidence:** `src/runtime/broker_infrastructure.py:10-39`, `broker_accessors.py:34-119`,
  `trading_runtime_factory.py:105` (`if bs._active_name == "dhan"`)
- **Owner:** Runtime/Platform
- **Exit:** import-linter proves no `_active_name` string branch and no direct broker
  import outside `runtime/`; broker selected by `broker_id` enum via plugin registry.
- **Status:** IN_PROGRESS (P5-1 slice landed 2026-07-12) — removed the `_active_name == "dhan"`
  string branch in `trading_runtime_factory.py` and the `getattr(_active_name)` fallback in
  `runtime/factory.py`; added arch guard `tests/architecture/test_no_broker_string_branching.py`
  (forbids `_active_name` string-branch/`getattr` in `src/runtime/`). Remaining for full G1
  close: (a) introduce a `BrokerId` enum (stable contract) and select via it; (b) migrate the
  `interface/ui` name-based broker selection (`getattr(_active_name)`, `getattr(_upstox_gateway)`)
  to the public `active_broker`/`active_broker_name` properties — those are warning-level per the
  layering rule but still couple the UI to private broker attributes.

## G2 — Orphaned shadow `brokers/dhan/*` duplicates `src/brokers/dhan/*` 🔴
- **Roadmap:** P5-1 · **ADR:** ADR-001
- **Evidence:** `brokers/dhan/gateway.py:14` (imports `tradex.runtime.capabilities`),
  `src/brokers/_bootstrap.py:11` (sys.path hack)
- **Owner:** Broker/Platform
- **Exit:** root `brokers/dhan/*` deleted; test asserts `import brokers.dhan.gateway`
  resolves under `src/`; CI green.
- **Status:** DONE — shipped 2026-07-12 (ADR-001 + guard test
  `tests/architecture/test_no_shadow_broker_modules.py`).

## G3 — Datalake bakes in NSE / IST specifics 🔴
- **Roadmap:** P5-2 · **ADR:** ADR-005
- **Evidence:** `src/datalake/core/nse_calendar.py`, `constants.py:50`, `schema.py:25`,
  `analytics_provider.py:78`, `research/api.py:63`, `option_format.py:78`
- **Owner:** Market Data / Datalake
- **Exit:** zero `exchange="NSE"` / `nse_calendar` references in `src/datalake`;
  unregistered exchange raises `ExchangeNotConfigured`.
- **Status:** TODO — contract foundation laid (ADR-005): `TradingCalendar`,
  `ExchangeAdapter` ports and `ExchangeNotConfigured` exception now exist in
  `domain/ports` + `domain/exceptions`; P5-2 implements the NSE plugin against them.

## G4 — Two parallel config systems can drift ⚠️
- **Roadmap:** P5-4 · **ADR:** ADR-003
- **Evidence:** `src/infrastructure/config/settings.py` vs `src/config/schema.py` (`AppConfig`)
- **Owner:** Platform
- **Exit:** `AppConfig` is the single source; grep shows zero `SettingsLoaderBase`
  usage post-migration.
- **Status:** TODO

## G5 — Duplicated infrastructure (dual event bus, triple idempotency, two MCP, two strategy paths) ⚠️
- **Roadmap:** P5-5, P5-8 · **ADR:** ADR-004
- **Evidence:** `src/infrastructure/event_bus/` (2 stacks), `idempotency/` (3 caches +
  `ProcessedTradeRepository`), `brokers.mcp` + `agent.mcp`, `LiveStrategyEngine` vs
  `TradingOrchestrator`
- **Owner:** Platform / Strategy
- **Exit:** one event-bus core + one idempotency service; one strategy spine; one MCP facade.
- **Status:** TODO

## G6 — Reconciliation off the hot path → silent drift ⚠️
- **Roadmap:** P5-6
- **Evidence:** `src/domain/reconciliation_engine.py:42`, `order_manager.py:344`
- **Owner:** OMS / Risk
- **Exit:** `ReconciliationEngine` wired into order-update handling; `POSITION_DRIFT`
  events emitted; drift auto-heals from broker-authoritative state.
- **Status:** TODO

## G7 — Reflection `getattr` kill-switch fragility ⚠️
- **Roadmap:** P5-7
- **Evidence:** `trading_orchestrator.py:518`, `order_placer.py:67,70`, `oms/reconciliation_service.py:161,164`, `oms/context.py:419`, `services/production_readiness.py:247`
- **Owner:** Trading / Risk
- **Exit:** kill-switch reads via injected `RiskGate` port; zero `getattr` reach-through
  to `risk_manager`.
- **Status:** IN_PROGRESS — `trading_orchestrator.py` reach-through closed (2026-07-12):
  `TradingOrchestrator` now takes an injected `RiskManagerPort` and `_is_kill_switch_active`
  delegates to it directly (no `getattr`). Regression guard:
  `tests/component/trading/test_orchestrator_kill_switch_port.py`.
  Remaining reach-throughs (order_placer.py:67,70; oms/reconciliation_service.py:161,164;
  oms/context.py:419; services/production_readiness.py:247) are separate instances — close
  each by injecting `RiskManagerPort` the same way. See `adr/0006-kill-switch-risk-gate.md`.

## G8 — Ad-hoc scripts at repo root ⚠️
- **Roadmap:** P4-6
- **Evidence:** `pytest_runner.py`, `pytest_runner2.py`, `pytest_runner3.py`, `run_all.sh`,
  `run_arch_tests.sh`, `verify_decomposition.py`
- **Owner:** Dev Platform
- **Exit:** scripts deleted; equivalent validation available via `tradex` CLI / MCP.
- **Status:** TODO

---

## Backlog Health (re-baselined 2026-07-12 — verified against tree)

| Metric | Baseline doc claimed | Verified (tree @ HEAD) |
|---|---|---|
| Total gaps | 8 (3 🔴, 5 ⚠️) | 8 (3 🔴 G1/G3/GoV, 5 ⚠️ G4/G5/G6/G7/G8) — G2 **DONE** |
| Architecture tests | 56 | **261 defs / 58 files** |
| Total tests | ~773 | **7,472** (`def test_`) / 775 files |
| Coverage gate | ≥80 (brokers ≥85, oms ≥90) | unchanged |
| CI workflows | 8 | 8 |
| import-linter contracts | ~18 | ~18 |
| `src/` total LOC | (n/a) | **~175,780** |
| Files >650 LOC (ADR-011 "hard") | (n/a) | **~20 `src/` files** (rule NOT enforced — see GOV-2) |
| Divergent git branches | (n/a) | **~13**; `main` 61 commits behind HEAD |

See `REVIEW.md` §1–§3 for the full verified-vs-claimed diff and the governance red flags.

## Governance Backlog (NEW — must precede Phase 5; see `REVIEW.md` §3/§4.0)

| ID | Item | Sev | Exit |
|---|---|---|---|
| GOV-1 | ADR-0010 (events/types split) + ADR-0011 (file-size limit) docs missing though 10+ commits cite them | 🔴 | ADR docs merged, link commits |
| GOV-2 | ADR-011 "hard 650-LOC limit" not enforced in CI/pre-commit | 🔴 | gate red on new violations |
| GOV-3 | `main` stale; ~13 divergent branches (`phase1-7`, `dev*`, `agent/*`) | 🔴 | `main`==HEAD; ≤3 long-lived branches |
| GOV-4 | `baseline.md` metrics wrong | ⚠️ | numbers match tree |
| GOV-5 | New 905-LOC `capability_manifest/catalog.py` god object | ⚠️ | decomposed under LOC gate |

## Suggested First Pick

**Governance Gate (GOV-1…GG-4) first** — the plan currently claims rules the tree does
not honor (ADR-011 "enforced", `main` current, baseline metrics). Fix the plan's
trustworthiness, then **G1 (P5-1)**: smallest 🔴 that unblocks broker-agnosticism and is a
superset of the already-centralized `broker_accessors.py`. G2 is already DONE.
