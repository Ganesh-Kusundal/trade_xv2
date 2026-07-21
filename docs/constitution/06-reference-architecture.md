# 06 — Reference Architecture

**Status:** Canonical  
**Target layout** — design for convergence, not rubber-stamp of drift.

---

## Layer → Directory Map

| Layer | Directory | Notes |
|---|---|---|
| Domain | `src/domain/` | entities, VOs, ports, events, FSMs |
| Application | `src/application/` | oms, execution, trading, risk use cases |
| Infrastructure | `src/infrastructure/` | bus, auth, idempotency, resilience, observability |
| Runtime | `src/runtime/` | **single composition root** |
| Brokers | `src/brokers/` | plugins (future: `src/plugins/brokers/`) |
| Datalake | `src/datalake/` | ingestion, quality, storage, analytics SQL |
| Analytics | `src/analytics/` | indicators, replay, backtest, strategies |
| Interface | `src/interface/` | api, ui (CLI/TUI) |
| Config | `src/config/` | AppConfig schema + profiles |
| Public SDK | `tradex/` | CLI entry, session facade |

---

## Target Module Layout (convergence goal)

```text
src/
├── domain/
│   ├── entities/          # Order, Position, Instrument, ...
│   ├── value_objects/     # Price, Quantity, Signal, ...
│   ├── events/            # DomainEvent types
│   ├── ports/             # All Protocol definitions
│   └── fsm/               # ORDER_STATUS_TRANSITIONS, ...
├── application/
│   ├── oms/               # OrderManager, reconciliation
│   ├── execution/         # ExecutionEngine façade → ExecutionTarget
│   ├── trading/           # Orchestrator (signal path only)
│   └── risk/              # RiskManager impl (or oms/risk if merged)
├── infrastructure/
│   ├── event_bus/
│   ├── idempotency/
│   ├── auth/
│   └── resilience/
├── runtime/
│   └── factory.py         # build_kernel(), resolve_execution_target()
├── brokers/
│   ├── dhan/
│   ├── upstox/
│   └── paper/
├── analytics/
│   ├── pipeline/          # features, indicators
│   ├── replay/
│   ├── backtest/
│   └── strategy/
├── datalake/
│   ├── core/              # duckdb_utils ONLY connect site
│   ├── ingestion/
│   └── quality/
└── interface/
    ├── api/
    └── ui/
```

---

## Execution Target Wiring (single branch)

**Only file allowed to branch on execution mode:**

`src/runtime/factory.py` → `resolve_execution_target(config) -> ExecutionTarget`

```text
resolve_execution_target
├── ReplayTarget      → analytics/replay/
├── BacktestTarget    → analytics/backtest/ (or shared with replay)
├── PaperTarget       → application/execution/simulated_fill.py
└── LiveTarget        → brokers/*/execution + gateway
```

All paths delegate to same `OrderManager.place_order`.

---

## Plugin Registration

`pyproject.toml`:

```toml
[project.entry-points."tradex.brokers"]
dhan = "brokers.providers.dhan:register"
upstox = "brokers.providers.upstox:register"
paper = "brokers.providers.paper:register"

[project.entry-points."tradex.exchanges"]
nse = "..."
```

Runtime discovers once at boot; injects into MarketDataProvider and LiveTarget.

---

## Import-Linter Contracts (enforced)

Align with `01` §7:

1. `domain` independent
2. `application` → `domain` only
3. `infrastructure` → `domain` only
4. `runtime` may import all inward layers + brokers + datalake
5. `interface` → `application`, `runtime` (warning on direct `brokers`)

Additional ratchets (Phase H):

- `grep`: no `execution_mode` string branch outside `runtime/factory.py`
- `grep`: no `datetime.now` in order/fill paths
- architecture test: single EventBus implementation wired at runtime

---

## Data Layout

| Path | Purpose |
|---|---|
| `data/lake/` | Historical parquet, DuckDB files (target) |
| `data/state/` | Durable orders, idempotency ledger (Live) |
| `.env.*` | Profiles (never committed with secrets) |

---

## Test Layout

| Path | Purpose |
|---|---|
| `tests/architecture/` | Layering, single bus, single OMS path |
| `tests/integration/` | Real wiring, parity, broker contracts |
| `tests/component/` | Context-level with real deps |
| `tests/e2e/` | Full flows CLI → kernel |

**Rule:** Run via `venv/bin/pytest`. No system Python.

---

## Public Surfaces

| Surface | Entry | Kernel access |
|---|---|---|
| CLI | `tradex` → `tradex/session.py` | `runtime.factory.build_kernel` |
| API | `src/interface/api/main.py` | `deps.py` → factory |
| TUI | `src/interface/ui/main.py` | session bridge |
| MCP | `src/datalake/mcp/` | read-only market data |

---

## Configuration Spine

Single schema: `src/config/schema.py` (`AppConfig`)

Profile selection: `src/config/profiles/`

Required fields for kernel boot:

- `broker_id: BrokerId`
- `execution_target: ExecutionTargetKind` (enum)
- `environment: Environment` (BACKTEST | REPLAY | PAPER | LIVE)

---

## Observability Conventions

- Structured log keys: `correlation_id`, `order_id`, `instrument_id`, `reason_code`
- Trace spans on: place_order, risk evaluate, reconcile
- Metrics: order count by state, risk deny rate, bus DLQ depth

---

## Migration from Current Tree

Phase G (`07-gap-analysis.md`) ranks drift. Phase H moves code toward this layout **incrementally**:

1. Collapse execution adapters → `ExecutionTarget` protocol
2. Move all mode branching to `runtime/factory.py`
3. Ensure `application/execution/execution_engine.py` is the single façade
4. Delete duplicate sim paths once parity tests pass

No big-bang directory rename without a gated phase.

---

## ADR Location

Architecture changes to P1–P12: `docs/architecture/adr/` (numeric ADR) + update constitution if product-level.

---

## graphify

After any code change in Phase H:

```bash
graphify update .
```

Keeps dependency graph current for gap analysis.
