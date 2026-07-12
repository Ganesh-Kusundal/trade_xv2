# Evidence Appendix

## Audit metadata

| Field | Value |
|-------|-------|
| Date | 2026-07-11 |
| Commit | `8f825b5d4be67915635123486ae76a1118573c12` |
| Branch | `refactor/structural-cleanup` |
| Auditor method | Static analysis + graphify CLI + limited command execution |
| Production code modified | **None** (audit-only) |

## Evidence states used

| State | Meaning |
|-------|---------|
| `verified_by_execution` | Command ran in audit environment |
| `verified_by_static_analysis` | Source/workflow read + grep |
| `documented_only` | Prior review/docs; not re-executed |
| `not_run` | Planned but not executed |
| `blocked_by_environment` | Requires creds, market hours, self-hosted runner |

## Commands executed

| Command | Result | State |
|---------|--------|-------|
| `git rev-parse HEAD` | `8f825b5d...` | verified_by_execution |
| `find . -type f` count | ~54,594 files | verified_by_execution |
| `PYTHONPATH=src lint-imports --config pyproject.toml` | 3 broken contracts | verified_by_execution |
| `PYTHONPATH=src pytest tests/architecture --collect-only` | 469 collected | verified_by_execution |
| `PYTHONPATH=src python3 scripts/verify/check_constants_placement.py` | PASS | verified_by_execution |
| `PYTHONPATH=src python3 -m scripts.verify_event_replay` | ModuleNotFoundError | verified_by_execution |
| Path existence checks (15 CI paths) | 6 MISSING, 9 EXISTS | verified_by_execution |
| `graphify query` (entry points, order lifecycle, market data, parity) | Subgraph returned | verified_by_execution |
| Live broker API calls | Not executed | blocked_by_environment |
| Full `pytest tests/` | Not executed (scope) | not_run |
| `ci.yml` GitHub Actions run | Not executed | not_run |

## Graphify queries run

1. `entry points composition roots SDK CLI API broker session` — 405 nodes
2. `order lifecycle place order fill reconciliation OMS execution ledger` — 1130 nodes
3. `market data websocket subscription tick depth normalization event bus` — 96 nodes
4. `backtest replay paper live parity mode execution` — 49 nodes

**Note:** `graphify update .` not run — audit documents only; no code graph changes.

## Paths reviewed (by category)

### Source (leaf sample — full tree inventoried)

- `src/domain/**` — 199 Python files
- `src/application/**` — 76 files
- `src/infrastructure/**` — 119 files
- `src/brokers/**` — 298 files
- `src/analytics/**` — 97 files
- `src/runtime/**` — 18 files
- `src/interface/**` — 156 files
- `src/tradex/**` — 5 files

### Key flow files (line-level trace)

- `src/application/execution/place_order_use_case.py`
- `src/application/oms/order_manager.py`
- `src/application/oms/_internal/order_lifecycle.py`
- `src/application/oms/reconciliation_service.py`
- `src/application/oms/process_context.py`
- `src/application/oms/context.py`
- `src/domain/reconciliation_engine.py`
- `src/domain/market/segment_mapper.py`
- `src/domain/executions/execution.py`
- `src/brokers/dhan/websocket/market_feed.py`
- `src/brokers/dhan/websocket/publish.py`
- `src/brokers/upstox/websocket/market_data_v3.py`
- `src/tradex/session.py`
- `src/runtime/trading_runtime_factory.py`
- `src/runtime/parity_gate.py`
- `src/analytics/backtest/engine.py`
- `src/analytics/replay/engine.py`
- `src/analytics/paper/engine.py`

### Tests

- `tests/unit/` (386 files)
- `tests/component/oms/`
- `tests/integration/brokers/{dhan,upstox}/`
- `tests/e2e/test_*_flow.py`
- `tests/architecture/` (30 files, 469 tests)
- `tests/chaos/`

### Workflows and config

- `.github/workflows/*.yml` (8 files)
- `pyproject.toml` (entry points, pytest, import-linter, coverage)
- `.pre-commit-config.yaml`
- `docs/architecture/RUNTIME_KERNEL.md`
- `docs/reviews/2026-07-10-trading-platform-review/**` (input, not truth)

### Scripts

- `scripts/audit/production_certification.py`
- `scripts/audit/capability_report.py`
- `scripts/verify/check_constants_placement.py`
- `scripts/verify/verify_event_replay.py`
- `scripts/verify/baseline_quant_parity.py`

## Environment-blocked checks

| Check | Blocker |
|-------|---------|
| Dhan live integration | `DHAN_ACCESS_TOKEN`, market hours |
| Upstox live WS parity | `UPSTOX_ACCESS_TOKEN`, `FORCE_MARKET_OPEN` |
| `dhan-regression.yml` | Self-hosted `dhan-live` runner + secrets |
| `broker_live_certify.yml` live jobs | GitHub secrets |
| Sandbox order lifecycle | `DHAN_INTEGRATION=1`, `TRADEX_LIVE_ORDERS=1` |
| Auth integration TOTP | `.env.local` / `.env.upstox` on runner |

**Credentials were not read.** `.env.local` appears in git status as modified — not inspected.

## Known unknowns

| Unknown | Resolution plan | Backlog |
|---------|-----------------|--------|
| Live Upstox tick latency under load | Market-hours benchmark | AUDIT-003 + perf tier |
| Duplicate order rate on HTTP timeout | Chaos test with mock server | AUDIT-017 |
| Multi-process OMS corruption rate | Deployment topology audit | A-07 |
| Actual CI last green run on this branch | Run repaired CI in Iteration 1 | AUDIT-001 |
| Collection errors (12+) root cause | Fix imports/fixtures | AUDIT-001 |
| Production capital deployment topology | Operator interview | — |

## Input documents (not accepted as truth)

- `docs/reviews/2026-07-10-trading-platform-review/executive-summary.md` — hypotheses confirmed independently
- `docs/architecture/RUNTIME_KERNEL.md` — two composition roots confirmed
- `src/brokers/OBJECT_MODEL_PLAN.md` — partial adoption
- `.kilo/plans/1783693185737-brokers-architectural-audit.md` — not fully validated