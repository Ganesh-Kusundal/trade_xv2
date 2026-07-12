# Phase 4 — Validation and Delivery-System Audit

**Evidence state:** `verified_by_static_analysis` + partial `verified_by_execution`

## Gate classification legend

| State | Meaning |
|-------|---------|
| `passed` | Executed successfully in audit environment |
| `failed` | Path broken or command errors deterministically |
| `not_run` | Not executed (time/env) |
| `blocked_by_environment` | Requires creds, market hours, or self-hosted runner |

## Workflow inventory (8 files)

| Workflow | Trigger | Primary purpose |
|----------|---------|-----------------|
| `ci.yml` | push/PR main,develop | Lint, pyramid, coverage, cert, e2e |
| `production_gate.yml` | release/**, tags | Full production certification |
| `broker_live_certify.yml` | cron weekdays | Live broker doctor/verify/certify |
| `architecture-enforcement.yml` | PR on `*.py` | Ruff, arch tests, import grep |
| `dhan-regression.yml` | cron, self-hosted | Dhan live regression tiers |
| `load-test.yml` | cron Mon | Paper load test |
| `mutation_testing.yml` | cron | Mutation via shell script |
| `mutation_nightly.yml` | cron | mutmut on domain/brokers |

## Critical path drift (CI → working tree)

| CI reference | Status | Actual location |
|--------------|--------|-----------------|
| `scripts/check_constants_placement.py` | **MISSING** | `scripts/verify/check_constants_placement.py` ✅ |
| `scripts/capability_report.py` | **MISSING** | `scripts/audit/capability_report.py` ✅ |
| `scripts/detect_flaky_tests.py` | **MISSING** | `scripts/debug/detect_flaky_tests.py` |
| `scripts/run_mutation_tests.sh` | **MISSING** | `scripts/verify/run_mutation_tests.sh` |
| `python -m scripts.verify_event_replay` | **BROKEN** | `scripts/verify/verify_event_replay.py` (direct OK) |
| `brokers/dhan/tests/integration/` | **MISSING** | `tests/integration/brokers/dhan/` |
| `brokers/dhan/tests/integration/test_regression_suite.py` | **MISSING** | No file in tree |
| `tests/stress/` | **MISSING** | `tests/e2e/stress/` |
| `tests/regression/test_memory_leaks.py` | **MISSING** | `tests/architecture/regression_invariants/test_memory_leaks.py` |
| `tests/brokers/` (flaky job) | **MISSING** | Consolidated under `tests/` |
| `parity_gate.py` replay path | **WRONG** | Points to `scripts/verify_event_replay.py` (not `scripts/verify/`) |

**Verified locally:**

```
MISSING: scripts/check_constants_placement.py
EXISTS:  scripts/verify/check_constants_placement.py  → PASS when run
MISSING: tests/stress
EXISTS:  tests/e2e/stress
```

## Per-workflow gate status

| Gate / Job | Status | Notes |
|------------|--------|-------|
| `ci.yml` lint constants check | **failed** | Wrong script path L44 |
| `ci.yml` capability reports | **failed** | Wrong path L169-173 |
| `ci.yml` import-linter | **failed** | 3 broken contracts locally |
| `ci.yml` replay determinism | **failed** | `-m scripts.verify_event_replay` L214,277 |
| `ci.yml` pyramid unit/component/arch | **blocked_by_environment** | Paths OK; 12 collection errors |
| `ci.yml` integration (main push) | **failed** | `brokers/dhan/tests/integration/` L298 |
| `ci.yml` e2e stress | **failed** | `tests/stress/` missing |
| `ci.yml` broker doctor | **not_run** (warn-only) | `continue-on-error: true` L189 |
| `ci.yml` flaky detection | **failed** | Wrong script + missing `tests/brokers/` |
| `production_gate.yml` memory tests | **failed** | Wrong memory test path |
| `production_gate.yml` certification script | **failed** | Stale `brokers/`, `cli/` paths in cert |
| `dhan-regression.yml` | **failed** | Old tree + missing regression suite |
| `architecture-enforcement.yml` | **blocked_by_environment** | Partially runnable |
| `broker_live_certify.yml` paper | **blocked_by_environment** | Runnable with deps |
| `broker_live_certify.yml` live | **blocked_by_environment** | Needs `DHAN_ACCESS_TOKEN`, `UPSTOX_ACCESS_TOKEN` |
| `mutation_testing.yml` | **failed** | Wrong shell script path |
| `mutation_nightly.yml` | **failed** | Wrong mutate paths + `\|\| true` |
| Pre-commit pytest-smoke | **failed** | `brokers/*/tests/` paths missing |
| Pre-commit mypy | **failed** | `files: ^brokers/` should be `^src/brokers/` |

## CI truthfulness issues

| Pattern | Location | Impact |
|---------|----------|--------|
| `continue-on-error: true` | `ci.yml` L189,391,395,424; `mutation_testing.yml` L30 | Failures don't fail workflow |
| MyPy warn-only | `ci.yml` L66-76 | Type errors never block |
| `bandit \|\| true` / safety warn | `ci.yml`, `production_gate.yml` | Scanner exit swallowed |
| `fail_ci_if_error: false` | Codecov upload | Upload failure ignored |
| Integration job PR-gated | `ci.yml` L283 — push to main only | PRs skip Dhan sandbox |
| Auth tests skip without creds | `auth_integration` marker | Skipped = green |
| Coverage label "90%" runs `--fail-under=80` | `production_gate.yml` | Misleading gate name |
| `SKIP_PARITY_GATE=1` | `parity_gate.py` | Production boot gate bypass |

## Test pyramid inventory

| Layer | Test files | Collected (pytest) | Collection errors |
|-------|------------|-------------------|-------------------|
| `tests/unit` | 386 | 4,419 | 3 |
| `tests/component` | 97 | 1,067 | 6 |
| `tests/integration` | 151 | 1,603 | 3 |
| `tests/e2e` | 33 | 318 | 0 |
| `tests/architecture` | 30 | 469 | 0 |
| `tests/chaos` | 12 | 175 | 0 |
| **Total** | **710** | **~7,051+** | **12+** |

### Test classification by intent

| Class | Location / marker | Live evidence? |
|-------|-------------------|----------------|
| Unit | `tests/unit/` | Deterministic |
| Component | `tests/component/oms/`, etc. | Mocked collaborators |
| Contract | `tests/integration/brokers/*/contract/` | Mixed |
| Integration | `tests/integration/` + `@integration` | Env-gated |
| E2E | `tests/e2e/test_*_flow.py` | Mostly mocked brokers |
| Architecture | `tests/architecture/` | Static enforcement |
| Chaos | `tests/chaos/` | Simulated failures |
| Certification | `tests/unit/brokers/certification` + `broker certify` | Paper = real module; live = blocked |
| Regression | `@regression`, `dhan-regression.yml` | **Workflow broken** |
| Performance | `@performance`, `load-test.yml` | Paper only |

## Certification surfaces

| Surface | Entry | Path valid? |
|---------|-------|-------------|
| CI paper cert | `broker --broker paper verify/certify` | ✅ |
| `production_certification.py` | `scripts/audit/production_certification.py` | Partial — internal stale paths |
| Nightly live | `broker --broker {dhan\|upstox} doctor --live` | blocked_by_environment |
| Dhan regression report | `scripts/audit/dhan_regression_report.py` | ✅ script; workflow refs wrong |
| Parity gate | `runtime/parity_gate.py` | **broken replay invocation** |

## Environment variables for live/sandbox (names only)

**Workflow:** `STRICT_EXECUTION_PARITY`, `DHAN_INTEGRATION`, `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`, `DHAN_SANDBOX_*`, `UPSTOX_INTEGRATION`, `UPSTOX_ACCESS_TOKEN`, `PRE_PROD_GATE`, `FORCE_MARKET_OPEN`

**Auth gates:** `DHAN_PIN`, `DHAN_TOTP_SECRET`, `UPSTOX_API_KEY`, `UPSTOX_TOTP_SECRET`, `TRADEX_LIVE_ORDERS`, `SKIP_PARITY_GATE`, `ENFORCE_PARITY`

**File gates (not env):** `.env.local`, `.env.upstox` presence for live tests

## Commands executed in this audit

| Command | Result |
|---------|--------|
| `PYTHONPATH=src lint-imports --config pyproject.toml` | **FAIL** — 3 contracts |
| `PYTHONPATH=src pytest tests/architecture --collect-only` | **469 collected** |
| `PYTHONPATH=src python3 scripts/verify/check_constants_placement.py` | **PASS** |
| `PYTHONPATH=src python3 -m scripts.verify_event_replay` | **ModuleNotFoundError** |
| Path existence checks (15 paths) | Documented above |

## Separation: real vs mock evidence

| Claim type | Evidence quality |
|------------|------------------|
| OMS UNKNOWN handling | Unit/component tests — high confidence |
| Dhan tick publish | Integration tests exist — env-gated for live |
| Upstox EventBus ticks | **No test found** — static analysis only |
| Live order lifecycle | `tests/integration/brokers/dhan/test_live_order_lifecycle.py` — blocked |
| Paper certification | Runs offline — does not prove live parity |
| E2E `test_complete_trading_flow` | Uses `MockBrokerGateway` — not live |