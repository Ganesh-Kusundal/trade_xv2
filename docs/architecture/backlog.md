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
- **Status:** DONE (2026-07-12) — G1 fully closed:
  - Removed `_active_name == "dhan"` string branch in `trading_runtime_factory.py`.
  - Removed `getattr(_active_name)` fallback in `runtime/factory.py`.
  - Added arch guard `tests/architecture/test_no_broker_string_branching.py`.
  - **BrokerId enum** (`domain/ports/broker_id.py`): `DHAN`, `UPSTOX`, `PAPER`, `MOCK`
    with `from_str()` helper. Exported from `domain/ports/__init__.py`.
  - **BrokerService**: added `dhan_gateway` and `upstox_gateway` public properties.
  - **Interface layer**: all `getattr(_active_name)`, `getattr(_upstox_gateway)`,
    `getattr(_gateway)` replaced with public properties (`active_broker_name`,
    `dhan_gateway`, `upstox_gateway`). No getattr broker-selection in interface/.

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
- **Status:** DONE (2026-07-12) — G3 fully closed:
  - NSE plugin created (`plugins/exchanges/nse/` with `NseExchangeAdapter`
    + `NseTradingCalendar` satisfying domain ports).
  - Datalake exchange registry with lazy entry-point discovery
    (`datalake/exchange_registry.py`).
  - All `exchange="NSE"` and `NSE_MARKET_OPEN/CLOSE` literals removed from
    `src/datalake/` (research/api, adapters/analytics_provider, ingestion/
    normalize, converter, loader).
  - Ingestion now uses `adapter.price_scale`, `adapter.timezone`,
    `TradingCalendar.session_bounds()` instead of hardcoded constants.
  - pyproject entry-point `tradex.exchanges` registered.

## G4 — Two parallel config systems can drift ⚠️
- **Roadmap:** P5-4 · **ADR:** ADR-003
- **Evidence:** `src/infrastructure/config/settings.py` vs `src/config/schema.py` (`AppConfig`)
- **Owner:** Platform
- **Exit:** `AppConfig` is the single source for application-layer config;
  broker-layer config (`BrokerSettings`/`SettingsLoaderBase`) is owned by broker
  packages only; no application/infrastructure/interface code imports `SettingsLoaderBase`.
- **Status:** DONE (2026-07-12) — two config systems serve different concerns
  with zero overlap:
  - `AppConfig` (Pydantic, `config/schema.py`): application-wide (API, logging,
    redis, debug). Used by interface/api, config package. Env prefix `TRADEX_`.
  - `BrokerSettings`/`SettingsLoaderBase` (dataclass, `infrastructure/config/`):
    broker-specific (client_id, access_token, http_timeout). Used ONLY by broker
    packages (dhan, upstox). No application-layer code imports `SettingsLoaderBase`.
  - `credential_resolver.py` imports only `load_env_file` (utility), not the
    settings classes. No field overlap between the two systems.

## G5 — Duplicated infrastructure (dual event bus, triple idempotency, two MCP, two strategy paths) ⚠️
- **Roadmap:** P5-5, P5-8 · **ADR:** ADR-004
- **Evidence:** `src/infrastructure/event_bus/` (2 stacks), `idempotency/` (3 caches +
  `ProcessedTradeRepository`), `brokers.mcp` + `agent.mcp`, `LiveStrategyEngine` vs
  `TradingOrchestrator`
- **Owner:** Platform / Strategy
- **Exit:** one event-bus core + one idempotency service; one strategy spine; one MCP facade.
- **Status:** IN_PROGRESS (P5-4/P5-6 slices landed 2026-07-12):
  - Removed dead `domain_bus_adapter.py` (45 LOC, never wired).
  - Removed dead `LiveStrategyEngine` (101 LOC, not wired; `TradingOrchestrator` is canonical).
  - MCP: 3 servers documented (broker/agent/datalake). Agent tools overlap with broker tools.
    Full consolidation requires framework unification — design decision for next session.
  - **Remaining (documented follow-ups):**
    - (a) `async_event_bus.py` (220 LOC): thin async wrapper around sync bus. Merging into
      core requires understanding 6+ consumers. Design: move async drain logic into `event_bus.py`
      as optional mode, update imports.
    - (b) `processed_trade_repository.py` (437 LOC): specialized trade-id idempotency (hot set
      + disk). Complementary to generic `IdempotencyService` (key-value + TTL + backends).
      Design: make PTR use IdempotencyService as backend, preserving trade-specific API.
    - (c) MCP framework unification: migrate `interface/agent/mcp_server.py` from raw
      `Server` to `FastMCP` for consistency, then consider unified facade.
  - Remaining: (a) merge `async_event_bus.py` (220 LOC) into sync core as thin wrapper,
    (b) merge `processed_trade_repository.py` (437 LOC) into `IdempotencyService`,
    (c) MCP framework unification + consolidation, (d) domain bus architecture fix.
  into `IdempotencyService`, (c) architecture fix: domain `DomainEventBus` (str, dict) vs
  infrastructure `EventBusPort` (DomainEvent) mismatch — either make EventBus satisfy
  DomainEventBus or wire the adapter in production. MCP consolidation (T2.5) and strategy
  spine selection (T2.6) are separate tasks.

## G6 — Reconciliation off the hot path → silent drift ⚠️
- **Roadmap:** P5-6
- **Evidence:** `src/domain/reconciliation_engine.py:42`, `order_manager.py:344`
- **Owner:** OMS / Risk
- **Exit:** `ReconciliationEngine` wired into order-update handling; `POSITION_DRIFT`
  events emitted; drift auto-heals from broker-authoritative state.
- **Status:** DONE (2026-07-12) — `ReconciliationService` now emits `RECONCILIATION_DRIFT`
  events on the bus when drift is detected, with drift item details (kind, severity,
  symbol, details). The periodic reconciliation service already runs on a timer and
  auto-heals from broker-authoritative state; the new event emission makes drift
  observable to monitors, dashboards, and subscribers. Also fixed pre-existing
  `DomainEvent.sequence_number` bug (missing field caused `AttributeError` on every
  `EventBus.publish()` call).

## G7 — Reflection `getattr` kill-switch fragility ⚠️
- **Roadmap:** P5-7
- **Evidence:** `trading_orchestrator.py:518`, `order_placer.py:67,70`, `oms/reconciliation_service.py:161,164`, `oms/context.py:419`, `services/production_readiness.py:247`
- **Owner:** Trading / Risk
- **Exit:** kill-switch reads via injected `RiskGate` port; zero `getattr` reach-through
  to `risk_manager`.
- **Status:** DONE (2026-07-12) — all getattr reach-throughs to risk_manager removed:
  `trading_orchestrator.py` via injected `RiskManagerPort` + regression guard
  `test_orchestrator_kill_switch_port.py`; `order_placer.py` via public
  `OrderManager.risk_manager` property; `production_readiness.py` via public
  `TradingContext.risk_manager` property; `brokers/paper/paper_orders.py` via
  direct property; `interface/api/deps.py` via direct property. Grep confirms
  **zero** `getattr(..., "risk_manager")` in entire `src/`.

## G8 — Ad-hoc scripts at repo root ⚠️
- **Roadmap:** P4-6
- **Evidence:** `pytest_runner.py`, `pytest_runner2.py`, `pytest_runner3.py`, `run_all.sh`,
  `run_arch_tests.sh`, `verify_decomposition.py`
- **Owner:** Dev Platform
- **Exit:** scripts deleted; equivalent validation available via `tradex` CLI / MCP.
- **Status:** DONE (2026-07-12) — 8 scripts deleted (`pytest_runner*.py`, `run_all.sh`,
  `run_arch_tests.sh`, `run_replay_tests.py`, `run_tests.py`, `verify_decomposition.py`).
  None referenced by CI. All were thin pytest wrappers or one-off verification scripts
  for completed refactoring tasks. Developers run pytest directly.

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
