# Architecture — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. This file summarizes the layering contract.
> **Canonical architecture:** [`docs/constitution/`](../docs/constitution/) — start with
> `01-architecture-constitution.md` (principles P1–P12) and `02a-runtime-execution-model.md`.
> **Gap analysis:** `docs/constitution/07-gap-analysis.md` (platform-wide);
> `docs/constitution/09-broker-subsystem-gap-analysis.md` (broker plugins).
> Do not change invariants without an ADR.

## 1. Stack Table (layer → technology → role)

| Layer | Technology | Role |
|---|---|---|
| Domain | Python (stdlib only) | Typed entities, ports (Protocols), domain events. No inbound imports. |
| Application | Python | Use-cases: oms, execution, trading, portfolio, strategy_engine, options. |
| Infrastructure | Python | Adapters: config, auth, persistence, resilience, idempotency, event_bus, metrics, observability. |
| Runtime | Python | Composition root — the ONLY layer touching concrete brokers/plugins. |
| Brokers | Python (plugins) | Dhan / Upstox / Paper adapters satisfying `BrokerAdapter`. |
| Datalake | Python + DuckDB | Ingestion, quality, storage, analytics, research. |
| Interface | Python (FastAPI/Textual/Click) | API, TUI, CLI, two MCP servers. (A React/TS Web SPA under `web/` is planned but not yet implemented — `web/` holds only `.env.example`.) |
| Config | Pydantic `AppConfig` | Single config schema (`src/config/schema.py`). |

## 2. System Boundaries (folder → responsibility)

| Folder | Owns |
|---|---|
| `src/domain/` | Typed model + ports/events. Depends on nothing inward. |
| `src/application/` | Use-cases. May NOT import infrastructure/runtime/brokers/interface. |
| `src/infrastructure/` | Cross-cutting adapters. Imports `domain` ports only. |
| `src/runtime/` | Composition root. Only layer permitted concrete broker/exchange imports. |
| `src/brokers/` (→ `src/plugins/brokers/`) | Broker-specific adapters as plugins. |
| `src/datalake/` | Data ingestion/quality/storage/analytics. |
| `src/interface/` | Presentation layers over the `tradex` SDK. |
| `src/config/` | Single `AppConfig` schema. |
| `web/` | Placeholder for a planned React/TS SPA — currently only `.env.example` exists. |
| `tradex/` | Public package + CLI + session wiring. |

## 3. Dependency Rule (enforced by import-linter — CI-blocking for rules 1–4)

```
interfaces/      ──▶  runtime/ (composition root ONLY touches concretes)
runtime/         ──▶  infrastructure/ (adapters)  +  application/ (use-cases)
infrastructure/  ──▶  application/  (implements domain ports)
application/     ──▶  domain/  (entities, ports, events)
domain/          ──▶  (NOTHING inward — depends only on stdlib + itself)
```

1. `domain` may not import application/infrastructure/runtime/brokers/interface.
2. `application` may not import infrastructure/runtime/brokers/interface.
3. `infrastructure` may not import runtime/interface.
4. `runtime` is the ONLY layer permitted concrete broker/plugin imports — broker
   selection via plugin discovery, **never** string `_active_name` branching elsewhere.
5. `interface` may import application + runtime; never `brokers` directly (warning).

## 4. Storage Model

- **DuckDB** (`src/datalake/`) — market data, analytics, research queries.
- **File / Memory / Redis** — idempotency caches (`IdempotencyService`).
- **Config** — `AppConfig` (Pydantic) + `.env.*` profiles (`src/config/`).
- **Typed domain model** is the contract on write; raw `pd.DataFrame` returns on the
  datalake read path are a known gap (G-ish) — prefer typed models when adding readers.

## 5. Auth & Access Model

- `infrastructure/auth` — tokens, TOTP, credential resolution.
- Broker credentials resolved from `.env.*` profiles; never hard-coded in source.
- `RiskGate` (port) is the pre-trade + kill-switch authority — NOT a `getattr` reach-through.

## 6. Plugin Model

- Broker plugins discovered via `tradex.brokers` entry-point group (`pyproject.toml`).
- A plugin returns `(broker_id, BrokerAdapter)`; selection by `broker_id` enum, never
  string equality scattered across modules.
- `runtime/` resolves once at startup, injects the adapter into application as a
  `Callable`/`Protocol`. The `ExchangeAdapter` + `TradingCalendar` plugins (NEW,
  `tradex.exchanges`) hold NSE/IST specifics currently leaking from `datalake/core`.

## 7. Invariants (rules the codebase must NEVER violate)

1. **Zero-parity rule** — backtest, replay, and live execution share identical logic.
2. **Paper-only execution (ADR-0012)** — operator paths use `ExecutionTargetKind.PAPER`;
   broker plugins supply market data only; OMS owns paper capital/orders/positions.
   Only `runtime/execution_target.py` may branch on execution target kind.
3. **Single composition root** — only `runtime/` imports concrete brokers/plugins.
4. **No string broker branching** — broker selected by `broker_id` enum, once, at startup.
5. **Domain purity** — `domain/` imports nothing inward (stdlib + itself only).
6. **Risk gate is a port** — pre-trade approval/rejection flows through `RiskGate`,
   never a reflection `getattr` kill-switch.
7. **Reconciliation on hot path** — local state heals against broker truth via
   `ReconciliationPolicy`, not a detached service.
8. **No orphaned shadow copies** — the repo-root `brokers/dhan/*` duplicates are
   deleted (ADR-001/G2); `src/brokers/_bootstrap.py` path hack is a stopgap, not a pattern.
9. **No real-money mocks** — tests are integration tests against real components;
   no mock data, stubs, or placeholders in production code.
10. **Graphify stays current** — run `graphify update src` after modifying code files under `src/` (graph lives in `src/graphify-out/`).

## 8. Known Architectural Violations (tracked, do not add more)

| # | Gap | Severity | Status |
|---|---|---|---|
| G1 | `runtime/` concrete-broker + string branching | 🔴 | ✅ DONE — infrastructure layer uses plugin registry; ~30 string comparisons remain in interface layer (lower-priority broker ID display; BrokerId enum used where possible) |
| G2 | Orphaned shadow `brokers/dhan/*` | 🔴 | ✅ DONE — root `brokers/` deleted (ADR-001) |
| G3 | Datalake bakes NSE/IST | 🔴 | ✅ DONE — NSE/IST extracted from datalake core; TradingCalendar plugin is single source of truth |
| G4 | Two parallel config systems | ⚠️ | ✅ DONE — dead DhanConfig/UpstoxConfig removed from `config/schema.py`; broker config lives in `brokers/*/config/settings.py`; full merge deferred (different purposes confirmed) |
| G5 | Duplicated infra (dual event bus, triple idempotency, two MCP) | ⚠️ | ✅ DONE — event bus unified to `EventBusPort` Protocol (3→1); dead idempotency backends deleted (~1095 lines); Upstox alias removed |
| G6 | Reconciliation off hot path | ⚠️ | ✅ DONE — `request_reconciliation()` wakes loop on TRADE_APPLIED/ORDER_UPDATED events; periodic timer retained as safety net |
| G7 | Reflection `getattr` kill-switch | ⚠️ | ✅ DONE — uses `RiskManagerPort` injection |
| G8 | Ad-hoc scripts at repo root | ⚠️ | ✅ DONE — `api_server.py` moved to `scripts/run_api_server.py`; config docs at `docs/config/README.md` |

## Views vs pipeline ownership (OE-01)

| Path | Role | Canonical for |
|---|---|---|
| `analytics/pipeline/` (`FeaturePipeline`) | In-process feature compute on DataFrames | Replay, backtest, live operator parity paths |
| `analytics/views/` (SQL) | DuckDB views — `v_feature_*`, `v_top3_candidates`, materialized `m_intraday` | Batch/API/MCP datalake-at-scale queries |
| `analytics/scanner/` (Python) | Scanner orchestration over pipeline | Replay-parity scanner paths |

**Parity gate:** `tests/integration/quant/test_views_pipeline_parity.py` — overlapping `v_feature_*` columns must match `FeaturePipeline` ± float tolerance on a fixed OHLCV window before either stack is deprecated for a use case (see `docs/architecture/OE-01-views-pipeline-ownership.md`).

Domain indicators (`domain/indicators/`) are canonical; pipeline wraps domain; views SQL may lag (document equivalence gaps in `QualityViews` materialization notes).

## Architectural Migration Progress

| Gap | What Changed | Lines Removed | Key Files |
|---|---|---|---|
| G1 | Runtime string branching eliminated; ~30 remaining in interface layer only | — | `infrastructure/gateway/factory.py`, `infrastructure/connection/authenticated_readiness.py`, `infrastructure/auth/credential_validator.py`, `infrastructure/io/environment_bootstrap.py` |
| G2 | Shadow `brokers/dhan/*` deleted | — | `docs/architecture/adr/0001-delete-shadow-brokers.md` |
| G3 | NSE/IST extracted to `TradingCalendar` plugin | — | `datalake/exchange_registry.py`, `datalake/core/constants.py`, `datalake/core/option_format.py`, `datalake/quality/validation.py`, `datalake/quality/health_check.py` |
| G4 | Dead `DhanConfig`/`UpstoxConfig` removed from `config/schema.py` | ~93 | `config/schema.py` |
| G5 | Event bus unified to `EventBusPort` Protocol; dead idempotency backends deleted | ~1095 | `infrastructure/event_bus/`, `infrastructure/idempotency/`, `brokers/upstox/orders/idempotency.py` |
| G6 | Reconciliation moved to hot path via event-driven `request_reconciliation()` | — | `application/oms/reconciliation_service.py`, `application/oms/context.py` |
| G7 | `getattr` kill-switch replaced with `RiskManagerPort` injection | — | `trading_orchestrator.py` |
