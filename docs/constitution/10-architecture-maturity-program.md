# 10 — Architecture Maturity Program

**Status:** Canonical addendum (2026-07-20)  
**Authority:** Extends `01-architecture-constitution.md`, `08-incremental-implementation.md`  
**Scope:** Blueprint-phase mapping, hybrid integration model, logical packages, exit criteria

---

## 1. Purpose

This document ratifies the **construction-blueprint** program model: plan by architecture
maturity, not feature milestones. Each phase produces a complete, testable slice; the
repository stays deployable; downstream phases do not start until exit criteria pass.

TradeXV2 does **not** adopt a physical `apps/` + `packages/` monorepo split. Import-linter
contracts on [`src/`](../../src/) already encode the dependency graph. Blueprint package
names map to **logical bounded contexts** (existing top-level folders).

---

## 2. Hybrid Integration Model (constitutional)

The aspirational rule “modules communicate via events only” is **amended** for money paths:

| Path | Pattern | Rationale |
|---|---|---|
| OMS place/modify/cancel | **Direct call** via `place_order_spine` | Sync risk under OMS lock (P4, QA-latency-2) |
| Cross-context notification | **EventBus pub/sub** | Decouple producers from consumers |
| Market-data fan-out | **StreamOrchestrator → EventBus TICK** | Single tick authority; bus is fan-out |
| Capital audit trail | **Mandatory events** | Every ORDER_*/TRADE_*/RISK_* mutation emits on bus |

Pure event choreography for OMS is **forbidden** — it adds latency and race surface without
money-safety gain. See `02a-runtime-execution-model.md` §3.

---

## 3. Logical Package Map

| Blueprint package | TradeXV2 path | Notes |
|---|---|---|
| kernel | `src/runtime/`, `src/config/` | Composition root + config |
| domain | `src/domain/` | Pure entities, ports, events |
| events / messaging | `src/domain/events/`, `src/infrastructure/event_bus/` | Split by layer |
| market-data | `src/datalake/`, `src/application/streaming/`, `src/brokers/*/streaming/` | Tick authority in `runtime/tick_authority.py` |
| brokers | `src/brokers/` | Plugins via `tradex.brokers` |
| analytics | `src/analytics/` | Independent of strategies import direction |
| oms / risk / execution | `src/application/oms/`, `execution/`, `trading/` | OMS owns risk orchestration |
| backtest / replay / paper | `src/analytics/backtest|replay|paper/`, `src/runtime/paper_session.py` | PARITY via composition root |
| storage | `src/datalake/storage/`, `src/infrastructure/persistence/` | DuckDB + adapters |
| telemetry | `src/infrastructure/metrics/`, `observability/` | EventMetrics + OTel |
| apps (presentation) | `src/interface/`, `src/tradex/`, `src/brokers/cli/` | Compose packages; never imported inward |

**Rule:** No physical `packages/` wheels until Live ADR lift **and** PRE-DEPLOY paper score ≥ 7.5.

---

## 4. Blueprint Phase → Phase H Context

| Blueprint phase | Phase H context | Exit criteria (all required) |
|---|---|---|
| Foundation | Context 0 (constitution) | P1–P12 documented; import-linter green; gap analysis ranked |
| Kernel | Context 6 | `ServiceRegistry` + single OMS composition in `runtime/`; boot-order arch test |
| Market Data | Context 5 | Tick authority wired; `async_dropped` metric; live→lake SLO documented |
| Analytics | Ongoing | Analytics↔Trading import-linter; scan→feature acceptance |
| Strategy Runtime | Context 7 (complete) | One evaluator port for replay/paper/live orchestrator boundary |
| Risk Engine | Phase A + Context 6 | Fail-closed; no prod fail-open capital |
| OMS | Contexts 1–4 + Context 8 | Spine + acceptance tests; chaos weekly blocking |
| Broker Integrations | Broker cert CI | Capability contracts; sandbox on main |
| Portfolio | Context 9 (deferred) | PORTFOLIO_UPDATED on all capital mutations |
| Research | Context 10 | PURE_SIM labeled; `capital_metrics_valid=False` in summaries |
| Backtesting | Context 2 + 10 | Direct ctor PARITY default; research bypass labeled |
| Paper Trading | ADR-0012 workstreams | PRE-DEPLOY paper ≥ 7.5 |
| Live Trading | **Blocked** | ADR-0012 lift only after paper gate + weekly chaos green |
| Observability | Context 11 | Capital metrics; deploy-profile auth |
| Production Hardening | Context 8 | Weekly chaos/memory/stability on `main` |

Contexts 6–11 are defined in [`08-incremental-implementation.md`](08-incremental-implementation.md).

---

## 5. Research vs Capital Metrics

| Mode | OMS | `capital_metrics_valid` | Use |
|---|---|---|---|
| `ResearchMode.PARITY` | Required | `True` | Operator backtest/replay/paper |
| `ResearchMode.PURE_SIM` | Skipped | `False` | Grid search, walk-forward inner loops |
| `FastBacktestEngine` | Skipped | `False` | Universe scan pre-filter only |

**Rule:** Any API/CLI output presenting Sharpe, drawdown, or equity as “production” MUST
set `capital_metrics_valid=True`. Architecture ratchet: `tests/architecture/test_research_mode_gating.py`.

---

## 6. PRE-DEPLOY Score Gate

| Surface | Minimum score | Live money |
|---|---|---|
| Paper / research | **7.5 / 10** | N/A |
| Live (future) | **8.5 / 10** | Requires ADR-0012 lift |

Progress tracker “Done” markers require PRE-DEPLOY dimension lift, not feature checklist alone.

---

## 7. CI Maturity Targets

| Gate | Per-commit | Weekly (`weekly-hardening.yml`) |
|---|---|---|
| Architecture tests | ✅ | ✅ |
| OMS acceptance (real PaperFillSource) | — | ✅ blocking |
| Chaos + memory | Release only → | ✅ blocking on `main` |
| Docs validation | Planned | — |

See `.github/workflows/weekly-hardening.yml`.
