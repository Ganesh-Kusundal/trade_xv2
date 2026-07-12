# Architecture — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. This is the most important file: it defines
> the layering contract and invariants the codebase must never violate. Grounded in
> `docs/architecture/target-layering.md` (the enforced contract) and `baseline.md`.
> Do not change architecture without an ADR in `docs/architecture/adr/`.
>
> **End-to-end specification (Nautilus-referenced):**  
> `docs/architecture/e2e-spec/README.md` — kernel, domain, event catalog, data/execution
> flows, risk, time/parity, reconciliation, ports, and migration. Prefer that suite for
> flow-level design; this file remains the layering + invariant contract.

## 1. Stack Table (layer → technology → role)

| Layer | Technology | Role |
|---|---|---|
| Domain | Python (stdlib only) | Typed entities, ports (Protocols), domain events. No inbound imports. |
| Application | Python | Use-cases: oms, execution, trading, portfolio, strategy_engine, options. |
| Infrastructure | Python | Adapters: config, auth, persistence, resilience, idempotency, event_bus, metrics, observability. |
| Runtime | Python | Composition root — the ONLY layer touching concrete brokers/plugins. |
| Brokers | Python (plugins) | Dhan / Upstox / Paper adapters satisfying `BrokerAdapter`. |
| Datalake | Python + DuckDB | Ingestion, quality, storage, analytics, research. |
| Interface | Python (FastAPI/Textual/Click) + React/TS | Web SPA, API, TUI, CLI, two MCP servers. |
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
| `web/` | React/TS SPA (Tier 3-I Web Trading UI). |
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
2. **Single composition root** — only `runtime/` imports concrete brokers/plugins.
3. **No string broker branching** — broker selected by `broker_id` enum, once, at startup.
4. **Domain purity** — `domain/` imports nothing inward (stdlib + itself only).
5. **Risk gate is a port** — pre-trade approval/rejection flows through `RiskGate`,
   never a reflection `getattr` kill-switch.
6. **Reconciliation on hot path** — local state heals against broker truth via
   `ReconciliationPolicy`, not a detached service.
7. **No orphaned shadow copies** — the repo-root `brokers/dhan/*` duplicates are
   deleted (ADR-001/G2); `src/brokers/_bootstrap.py` path hack is a stopgap, not a pattern.
8. **No real-money mocks** — tests are integration tests against real components;
   no mock data, stubs, or placeholders in production code.
9. **Graphify stays current** — run `graphify update .` after modifying code files.

## 8. Known Architectural Violations (tracked, do not add more)

| # | Gap | Severity | Where |
|---|---|---|---|
| G1 | `runtime/` concrete-broker + string branching | 🔴 | `runtime/broker_infrastructure.py`, `trading_runtime_factory.py:105` |
| G2 | Orphaned shadow `brokers/dhan/*` | 🔴 | root `brokers/` vs `src/brokers/` |
| G3 | Datalake bakes NSE/IST | 🔴 | `nse_calendar.py`, `core/constants.py:50` |
| G4 | Two parallel config systems | ⚠️ | `infrastructure/config/settings.py` vs `config/schema.py` |
| G5 | Duplicated infra (dual event bus, triple idempotency, two MCP) | ⚠️ | `event_bus/`, `idempotency/`, `brokers.mcp`/`agent.mcp` |
| G6 | Reconciliation off hot path | ⚠️ | `reconciliation_engine.py:42` |
| G7 | Reflection `getattr` kill-switch | ⚠️ | `trading_orchestrator.py:518-524` |
| G8 | Ad-hoc scripts at repo root | ⚠️ | `pytest_runner*.py`, `run_*.sh` |
