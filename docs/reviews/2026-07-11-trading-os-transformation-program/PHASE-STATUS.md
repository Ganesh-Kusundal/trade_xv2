# Transformation Program — Phase Status

**Last updated:** 2026-07-11 (Iteration 7 complete)
**Baseline commit:** `8f825b5d` (branch `refactor/structural-cleanup`)

## Summary

| Phase | Status | Evidence |
|-------|--------|----------|
| 0 — Discovery & Baseline | ✅ **Complete** | [architecture-audit](../2026-07-11-trading-os-architecture-audit/README.md) |
| 1 — Architecture Foundation | ✅ **Complete** | HANDBOOK v1, ADR-015–018, GLOSSARY, EVENT_CATALOG, OBJECT_MODEL |
| 2 — Runtime & Flow Design | ✅ **Complete** | [FLOWS.md](../../architecture/FLOWS.md), STATE_MACHINES, ERROR_TAXONOMY |
| 3 — Engineering Standards | ✅ **Complete** | import-linter 15/15, arch tests, ADR-019, STANDARDS, DEPENDENCY_GRAPH |
| 4 — Developer Platform | 🟡 **In progress** | platform_ops unity, golden manifest, minimal example |
| 5 — Core Platform Refactor | 🟡 **In progress** | factory.build CLI path, api readiness gates |
| 6 — Feature Delivery | ⏸ Blocked on P5 | — |
| 7 — Production Hardening | ⏸ Blocked on P6 | — |

## Dependency graph & parallel execution

Master DAG: [DEPENDENCY_GRAPH.md](../../architecture/DEPENDENCY_GRAPH.md)

| Wave | Lanes (parallel) | Conflict rule |
|------|------------------|---------------|
| **Wave 1** ✅ | P1 docs ∥ P3 CI ∥ P3-008 code | No shared files |
| **Wave 2** ✅ | P2 flow docs ∥ dep-graph test ∥ Upstox bus | Brokers ≠ domain edits |
| **Wave 3** | P4 CLI ∥ P5 ledger ∥ P5 factory | Feature flags default off |

Sync guard: `tests/architecture/test_dependency_graph_sync.py` — pyproject.toml ↔ `_APPROVED_EDGES`.

---

## Iteration 1 — Validation truth ✅

import-linter 15/15, SegmentMapperRegistry, tracing decoupling, arch tests P3-010/011.

---

## Iteration 2 — Production safety paths 🟡

| Task | Status | Evidence |
|------|--------|----------|
| Phase 2 flow docs | ✅ | `FLOWS.md`, `STATE_MACHINES.md`, `ERROR_TAXONOMY.md` |
| Dependency graph | ✅ | `DEPENDENCY_GRAPH.md` + sync test |
| Flow contract stubs | ✅ | `test_flow_contracts.py` (1 xfail: MD-3) |
| Upstox EventBus TICK | ✅ | `market_data_v3._publish_tick_to_bus`, unit test |
| Tick translator fix | ✅ | Direct payload dict support |
| Fail-closed tick drops (MD-3) | ✅ | Dhan + Upstox `MARKET_DATA_DEGRADED` |
| Upstox recon unify | ✅ | `ReconciliationEngine` in upstox recon service |

### Verification (Wave 2)

```bash
PYTHONPATH=src lint-imports --config pyproject.toml
PYTHONPATH=src pytest tests/architecture/ -q -m architecture --ignore=tests/architecture/test_imports.py
PYTHONPATH=src pytest tests/unit/brokers/upstox/test_market_data_event_bus.py -q
```

---

## Iteration 3 — Execution spine ✅

| Task | Status | Evidence |
|------|--------|----------|
| `runtime.factory.build` | ✅ | `src/runtime/factory.py`, `compose.build_for_api` |
| `TRADEX_LEDGER_AUTHORITY` gate | ✅ | `runtime/ledger_policy.py`, OMS/API bootstrap |
| Shadow ledger parity | ✅ | `ledger_shadow.py`, recon loop hook |
| Platform ops unity | ✅ | `brokers/platform_ops.py`, broker_ops + MCP |
| Fail-closed tick drops | ✅ | `MARKET_DATA_DEGRADED` in Dhan publisher |
| Upstox → ReconciliationEngine | ✅ | `upstox/reconciliation/service.py` |
| Recon uses domain types | ✅ | `reconciliation_service` → `get_orders()` / `get_positions()` |

## Iteration 4 — CI gates & composition migration ✅

| Task | Status | Evidence |
|------|--------|----------|
| 24h shadow parity gate | ✅ | `shadow_parity_24h.json`, `test_shadow_parity_gate.py`, `parity_gate.py` |
| `open_session` → `factory.build` | ✅ | trade mode + `broker_service`, `active_session.py` |
| Cert JSON schema v2 | ✅ | `schema_v2.py`, `test_cert_schema_v2.py`, ADR-018 fields |
| Upstox bus golden cert | ✅ | `upstox_bus_ticks.json`, `test_upstox_bus_golden.py` |

### Verification (Iteration 4)

```bash
PYTHONPATH=src pytest tests/architecture/test_shadow_parity_gate.py tests/architecture/test_cert_schema_v2.py -q
PYTHONPATH=src pytest tests/unit/brokers/upstox/test_upstox_bus_golden.py -q
PYTHONPATH=src pytest tests/unit/tradex/test_open_session_factory.py -q
```

## Iteration 5 — MD-3 + cert unity + developer platform ✅

| Task | Status | Evidence |
|------|--------|----------|
| Fail-closed MD-3 (Upstox) | ✅ | `_maybe_emit_market_data_degraded`, `test_market_feed_degraded.py` |
| Flow contract MD-3 | ✅ | `test_flow_contracts` parametrized Dhan + Upstox |
| Cert path unity | ✅ | `test_cert_path_unity.py`, CLI → `platform_ops` |
| Golden manifest | ✅ | `tests/fixtures/golden/manifest.yaml` |
| Minimal session example | ✅ | `examples/minimal_session/run.py` |

### Verification (Iteration 5)

```bash
PYTHONPATH=src pytest tests/architecture/test_cert_path_unity.py tests/architecture/test_flow_contracts.py -q
PYTHONPATH=src pytest tests/unit/brokers/upstox/test_market_feed_degraded.py -q
PYTHONPATH=src python examples/minimal_session/run.py
```

## Iteration 6 — Factory migration + API readiness + doctor schema ✅

| Task | Status | Evidence |
|------|--------|----------|
| `compose.build_runtime` → `factory.build` | ✅ | `compose.py`, `test_factory_migration.py` |
| API `/health` + `/ready` gates | ✅ | `api_readiness.py`, `/ready` alias on health router |
| Unified doctor JSON | ✅ | `diagnostics/schema.py`, `broker doctor --json` |

### Verification (Iteration 6)

```bash
PYTHONPATH=src pytest tests/architecture/test_factory_migration.py tests/unit/application/services/test_api_readiness.py tests/unit/brokers/diagnostics/test_doctor_schema.py -q
PYTHONPATH=src pytest tests/integration/api/test_health.py -q
```

## Iteration 7 — Ledger outbox + CLI trade spine + production gate ✅

| Task | Status | Evidence |
|------|--------|----------|
| Ledger outbox boundary | ✅ | `ledger_outbox.py`, `persist_intent_then_submit`, fail-closed policy |
| CLI trade spine | ✅ | `_TRADE_SPINE_CMDS` → `build_runtime` in `main.py` |
| Production gate readiness | ✅ | `production_gate.yml` api/ledger/shadow tests |

### Verification (Iteration 7)

```bash
PYTHONPATH=src pytest tests/unit/application/oms/test_ledger_outbox.py tests/architecture/test_ledger_outbox_boundary.py -q
PYTHONPATH=src pytest tests/unit/tradex/test_cli_trade_spine.py -q
```

## Next actions (Iteration 8)

1. **TRANS-P5-032** — Reconciliation economics / PnL drift detection
2. **TRANS-P5-040** — Remove composition shims at zero usage
3. **TRANS-P6-001** — Market Access v1 (blocked on P5 completion review)

## Task ID mapping

| User spec | Program ID |
|-----------|------------|
| P2 flows | TRANS-P2-001 … 015 |
| Dep graph | TRANS-P1-007 + P3-011 extension |
| Iter 2 bus | TRANS-P5-010 / AUDIT-003 |