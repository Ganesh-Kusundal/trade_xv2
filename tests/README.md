# TradeXV2 test suite

Tests are the **living specification** of platform guarantees. They describe
behavior that must remain true across refactors — not the history of how a
change was introduced.

## Pyramid + source hierarchy

```text
tests/
├── unit/domain/**          ↔  src/domain/**
├── component/oms/**        ↔  src/application/oms/**
├── component/execution/**  ↔  src/application/execution/**
├── integration/brokers/**  ↔  multi-module broker contracts
├── e2e/ chaos/             ↔  full process
└── architecture/           ↔  layering / suite rules
```

| Layer | Directory | Question answered |
|-------|-----------|-------------------|
| Unit | `tests/unit/` (esp. `unit/domain/`) | Does this business rule work? |
| Component | `tests/component/` (oms, execution, trading, …) | Does this service behave correctly? |
| Integration | `tests/integration/` | Do components collaborate? |
| E2E | `tests/e2e/`, `tests/chaos/` | Does the full system work? |
| Architecture | `tests/architecture/` | Do layering / import rules hold? |

**Waves 1–3 done.** All production tests live under `tests/{unit,component,integration,e2e,architecture,chaos}`.

| Source | Test home |
|--------|-----------|
| `src/domain/**` | `tests/unit/domain/**` |
| `src/application/**` | `tests/component/{oms,execution,…}` |
| `src/brokers/**` | `tests/unit/brokers/**`, `tests/integration/brokers/**` |
| `src/analytics/**` | `tests/unit/analytics/**` |
| `src/datalake/**` | `tests/unit/datalake/**` |
| `src/infrastructure/**` | `tests/unit/infrastructure/**` |
| `src/interface/ui/**` | `tests/unit/interface/ui/**` (CLI/unit doubles); keep only true collaboration under `tests/component/ui/` |
| `src/interface/api/**` | `tests/integration/api/**` |

Do **not** add new tests under `src/**/tests`.

**Hierarchy rules (behavioral cleanup):**

- Name guarantees, not process history (`phase*`, `recent_fixes`, `wireup`, `migration`, ticket ids).
- Do not leave duplicate copies after a move — delete the temporary path.
- Mock-heavy CLI/doctor/order UI tests belong in `tests/unit/interface/ui/`, not `tests/component/ui/`.
- AST/import/LOC ratchets belong in `scripts/ci/` or import-linter, not pytest integration.
- Structural layering may remain under `tests/architecture/` until extracted; money-safety and domain behavior stay in unit/component/integration.

## Naming rules

**Good** (keep after a rewrite of the implementation):

- `test_duplicate_order_is_not_submitted_twice.py`
- `test_order_rejected_when_kill_switch_active.py`
- `test_process_oms_book_is_shared.py`

**Bad** (describes history, not guarantee):

- `test_b7_oms_wireup.py`
- `test_phase3.py`
- `test_after_refactor.py`
- `test_issue_127.py`
- `test_recent_fixes.py`
- `test_http_observability_wireup.py`

Heuristic: *If I rewrite the implementation tomorrow but keep the same external
behavior, would I keep this test?* If no, rewrite the test or delete it.

## Markers

See `pyproject.toml` `[tool.pytest.ini_options] markers`.

Broker-focused markers stand in for dedicated top-level dirs (`property/`, `stress/`,
`resilience/`, `acceptance/`, `live/`):

| Marker | Role |
|---|---|
| `live_readonly` | Live broker read-only integration |
| `market_hours` | Requires NSE market open |
| `dhan` / `upstox` | Broker-specific live paths |
| `regression` | Permanent broker bug guards (manifest-backed) |
| `certification` | `BrokerCertifier` / mapping / golden suites |

**Canonical broker contract pair:** `BrokerContractSuite` (market + lifecycle) and
`MarketCoverageContract` (declared `market_surfaces`). Legacy `GatewayContractSuite` is
deprecated.

Common filters:

```bash
PYTHONPATH=src pytest -m unit
PYTHONPATH=src pytest tests/component -q
PYTHONPATH=src pytest tests/integration -q
PYTHONPATH=src pytest tests/e2e -q
PYTHONPATH=src pytest tests/architecture -q
```

## Adding a test

1. Pick the pyramid layer (not a sprint or phase folder).
2. Name the file after the guarantee.
3. Prefer real domain objects; mock only at trust boundaries (network, clock).
4. Do not import production code from `tests/` into `src/`.
