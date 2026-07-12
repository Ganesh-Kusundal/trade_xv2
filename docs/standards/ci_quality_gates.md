# CI Quality Gates — TradeXV2

> **Phase 3 Deliverable D3.2** · Last updated: 2026-07-12

This document catalogs every quality gate in the TradeXV2 CI pipeline: what each
tool checks, how it is configured, how to run it locally, and whether it blocks
merges.

---

## 1 · Current Tooling (Already Working)

### 1.1 Ruff (Lint & Format)

| Item | Detail |
|------|--------|
| **What it checks** | Pycodestyle errors/warnings (E/W), pyflakes (F), isort (I), flake8-bugbear (B), pyupgrade (UP), logging format (G), naming (N), ruff-specific (RUF), bandit security (S), comprehensions (C4), simplify (SIM), tidy-imports (TID) |
| **Configuration** | `pyproject.toml` → `[tool.ruff]` (line-length 100, target py310), `[tool.ruff.lint]` select/ignore, `[tool.ruff.format]` (double quotes, spaces, LF) |
| **Banned APIs** | `[tool.ruff.lint.flake8-tidy-imports.banned-api]` blocks domain types from broker packages, lower-layer UI imports, cross-broker imports, and raw factory usage |
| **How to run** | `ruff check .` · `ruff format --check .` |
| **Pass/fail** | Exit 1 = fail. CI step is **blocking** on all PRs and pushes to main/develop |

### 1.2 MyPy (Static Type Checking)

| Item | Detail |
|------|--------|
| **What it checks** | Type correctness (disallow_untyped_defs, disallow_incomplete_defs, warn_unused_ignores, warn_redundant_casts, warn_return_any) |
| **Configuration** | `pyproject.toml` → `[tool.mypy]` (python_version 3.13, strict false). Overrides ignore_missing_imports for dhanhq, textual, rich, upstox_client, pandas, numpy |
| **Scope** | **ERROR gate (blocking):** domain submodules (aggregates, analytics, backtest, capability_manifest, constants, market, models, primitives, providers, quotes, repositories, risk, scanners, sessions, value_objects, extensions/broker_plugin_interface.py) + application/oms core files (25 files). **Advisory (warning):** src/brokers/ (~499 errors, deferred to P7) |
| **How to run** | `PYTHONPATH=src mypy src/domain/ src/application/oms/` |
| **Pass/fail** | Domain+OMS: exit 1 = **blocking**. Brokers: exit 1 = **warning** (surfaces errors, does not block merge) |

### 1.3 Import Linter (Architectural Boundary Enforcement)

| Item | Detail |
|------|--------|
| **What it checks** | 13 forbidden-import contracts that enforce layer boundaries: domain independence, infrastructure independence, analytics isolation, trading↔analytics separation, broker common isolation, application broker isolation, analytics→interface isolation, dispatcher broker isolation, runtime→interface isolation, application→infrastructure separation, CLI/API broker isolation, tradex broker isolation, UI→factory shim |
| **Configuration** | `pyproject.toml` → `[tool.importlinter]` (root_packages) + 13 `[[tool.importlinter.contracts]]` blocks with `type = "forbidden"`, `source_modules`, `forbidden_modules`, and `ignore_imports` |
| **How to run** | `PYTHONPATH=src lint-imports --config pyproject.toml` |
| **Pass/fail** | Exit 1 = **blocking**. CI runs it in three places: lint job, pyramid-architecture job, and unit-and-contract job |

### 1.4 Pytest (Unit / Component / Architecture / Integration Tests)

| Item | Detail |
|------|--------|
| **What it checks** | Correctness across all test layers: unit (pure business logic), component (single-service), architecture (boundary guards), integration (non-live), e2e, stress, chaos |
| **Configuration** | `pyproject.toml` → `[tool.pytest.ini_options]` — pythonpath `["src", "."]`, asyncio_mode auto, addopts `-ra --strict-markers --tb=short --durations=10`. 30+ markers including unit, component, architecture, integration, sandbox, live_readonly, chaos, etc. |
| **How to run** | `PYTHONPATH=src pytest tests/unit -q --tb=short` · `pytest tests/architecture/ -v --tb=short` · `pytest tests/component/ -q` |
| **Pass/fail** | Exit 1 = **blocking** on all layers. CI runs them in parallel pyramid jobs (unit, component, architecture) plus the unified coverage job |

### 1.5 Coverage (Branch Coverage)

| Item | Detail |
|------|--------|
| **What it checks** | Branch coverage across brokers, analytics, interface, datalake, application, domain, infrastructure, runtime, tradex, config |
| **Configuration** | `pyproject.toml` → `[tool.coverage.run]` (source list, omit tests + \_\_init\_\_.py), `[tool.coverage.report]` — **fail_under = 80%**, excludes pragma/no-cover, NotImplementedError, TYPE\_CHECKING, Ellipsis |
| **How to run** | `PYTHONPATH=src pytest --cov=application --cov=domain --cov-branch --cov-report=term-missing` then `coverage report --fail-under=80` |
| **Pass/fail** | Exit 1 = **blocking**. Per-module gates: overall ≥ 80%, brokers ≥ 85%, OMS core ≥ 90%, application ≥ 80% |

### 1.6 Mutmut (Mutation Testing)

| Item | Detail |
|------|--------|
| **What it checks** | Test quality by mutating source code (unary ops, binary ops, continue-or-swap) — tests must kill 90% of mutants |
| **Configuration** | `pyproject.toml` → `[tool.mutmut]` — paths_to_mutate: brokers, analytics, datalake, domain, application, infrastructure; operators: uop, aod, aor, cos; timeout 300s; **fail_under = 90%** |
| **How to run** | `mutmut run --paths-to-mutate src/domain/,src/brokers/common/,src/application/oms/ --runner "PYTHONPATH=src python -m pytest -x -q"` then `mutmut results` |
| **Pass/fail** | **Advisory (nightly)** — runs at 03:00 UTC daily via `mutation_nightly.yml`. Real exit code preserved (no `\|\| true`), but NOT a required status check |

### 1.7 Pre-commit Hooks

| Item | Detail |
|------|--------|
| **What it checks** | Ruff lint+format, trailing whitespace, EOF fixer, YAML/TOML validation, large files (>1024 KB), merge conflicts, private keys, AWS credentials, gitleaks secret scanning, mypy (domain+OMS clean set), pytest smoke on staged test files, exception hierarchy, architecture fitness tests |
| **Configuration** | `.pre-commit-config.yaml` — ruff-pre-commit v0.4.4, pre-commit-hooks v4.6.0, gitleaks v8.18.4, mirrors-mypy v1.10.0, 3 local hooks (pytest-smoke, check-exception-hierarchy, architecture-tests) |
| **How to run** | `pre-commit run --all-files` |
| **Pass/fail** | Exit 1 = commit blocked locally. Architecture tests run on every `.py` file change |

### 1.8 Bandit (Security Static Analysis)

| Item | Detail |
|------|--------|
| **What it checks** | Security vulnerabilities in Python code (SQL injection, hardcoded passwords, insecure functions, etc.) |
| **Configuration** | Run as `bandit -r src/ -ll -f json` — only HIGH severity blocks |
| **How to run** | `bandit -r src/ -ll -f json -o bandit-report.json` |
| **Pass/fail** | HIGH severity count > 0 = **blocking**. MEDIUM/LOW = warning |

### 1.9 Safety (Dependency Vulnerability Check)

| Item | Detail |
|------|--------|
| **What it checks** | Known CVEs in installed Python dependencies |
| **Configuration** | Advisory until P7 |
| **How to run** | `safety check --json` |
| **Pass/fail** | **Advisory (warning)** — surfaces count, does not block merges |

### 1.10 Gitleaks (Secret Detection)

| Item | Detail |
|------|--------|
| **What it checks** | Hardcoded secrets, API keys, tokens in committed code |
| **Configuration** | `.pre-commit-config.yaml` → gitleaks v8.18.4 |
| **How to run** | `gitleaks detect --source .` |
| **Pass/fail** | Exit 1 = **blocking** (pre-commit), also checked in CI lint job via git grep |

---

## 2 · Proposed CI Pipeline (Consolidated 10-Stage Model)

The following stages represent the target pipeline. Stages 1–5 are the fast
path (under 5 minutes combined). Stages 6–10 add depth.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Stage 1     │───▶│ Stage 2     │───▶│ Stage 3     │
│ Lint+Format │    │ Type Check  │    │ Import      │
│ (ruff)      │    │ (mypy)      │    │ Contracts   │
└─────────────┘    └─────────────┘    └─────────────┘
                                              │
                     ┌─────────────┐    ┌──────▼──────┐
                     │ Stage 5     │◀───│ Stage 4     │
                     │ Architecture│    │ Unit Tests  │
                     │ Tests       │    │ (pytest)    │
                     └──────┬──────┘    └─────────────┘
                            │
               ┌────────────┼────────────┐
        ┌──────▼──────┐    │    ┌───────▼───────┐
        │ Stage 6     │    │    │ Stage 7       │
        │ Component   │    │    │ Integration   │
        │ Tests       │    │    │ (non-live)    │
        └──────┬──────┘    │    └───────┬───────┘
               └────────────┼────────────┘
                      ┌─────▼──────┐
                      │ Stage 8    │
                      │ Coverage   │
                      │ Gate       │
                      └─────┬──────┘
                            │
                  ┌─────────┼─────────┐
           ┌──────▼──────┐  │  ┌──────▼──────┐
           │ Stage 9     │  │  │ Stage 10    │
           │ Security    │  │  │ File Size   │
           │ Scan        │  │  │ Gate        │
           └─────────────┘  │  └─────────────┘
                            ▼
                    ┌──────────────┐
                    │ MERGE READY  │
                    └──────────────┘
```

### Stage 1 — Lint & Format

| Field | Value |
|-------|-------|
| **Tool** | `ruff check .` + `ruff format --check .` |
| **What it checks** | Code style, imports, banned APIs, formatting |
| **Blocking?** | ✅ **Yes** — blocks PR merge |
| **Timeout** | 5 minutes |
| **Failure action** | Block merge. Fix: `ruff check --fix . && ruff format .` |
| **How to fix** | Run pre-commit locally: `pre-commit run ruff --all-files` |

### Stage 2 — Type Check

| Field | Value |
|-------|-------|
| **Tool** | `mypy` (domain + OMS core modules) |
| **What it checks** | Type correctness on verified-clean submodules |
| **Blocking?** | ✅ **Yes** (domain+OMS core) / ⚠️ **Warning** (brokers) |
| **Timeout** | 10 minutes |
| **Failure action** | Block merge for clean modules. Warn for brokers (~499 known errors, deferred to P7) |
| **How to fix** | `PYTHONPATH=src mypy <failing_module>` — fix type errors or add type stubs |

### Stage 3 — Import Contracts

| Field | Value |
|-------|-------|
| **Tool** | `lint-imports --config pyproject.toml` |
| **What it checks** | 13 architectural boundary contracts (layer independence, broker isolation, etc.) |
| **Blocking?** | ✅ **Yes** |
| **Timeout** | 5 minutes |
| **Failure action** | Block merge. Indicates architectural boundary violation |
| **How to fix** | Remove the offending import; refactor to use ports/protocols or a composition root |

### Stage 4 — Unit Tests

| Field | Value |
|-------|-------|
| **Tool** | `pytest tests/unit -q --tb=short -n auto` |
| **What it checks** | Pure business logic correctness, domain rules, edge cases |
| **Blocking?** | ✅ **Yes** |
| **Timeout** | 20 minutes |
| **Failure action** | Block merge |
| **How to fix** | `pytest tests/unit/<failing_file> -v` to isolate, then fix the test or production code |

### Stage 5 — Architecture Tests

| Field | Value |
|-------|-------|
| **Tool** | `pytest tests/architecture/ -q --tb=short` |
| **What it checks** | Domain isolation, import direction, exception hierarchy, lock discipline, token redaction, no scattered dotenv, gateway signatures, no security ID leak, no broker name branching, composition root integrity, file fitness rules, behavioral test names, and ~50 other invariants |
| **Blocking?** | ✅ **Yes** |
| **Timeout** | 15 minutes |
| **Failure action** | Block merge. The failing test identifies the specific architectural violation |
| **How to fix** | Read the failing test name — it describes the rule. Fix the code to satisfy the constraint |

### Stage 6 — Component Tests

| Field | Value |
|-------|-------|
| **Tool** | `pytest tests/component -q --tb=short -n auto` |
| **What it checks** | Single-service correctness (OMS, execution, registry) with mocked collaborators |
| **Blocking?** | ✅ **Yes** |
| **Timeout** | 20 minutes |
| **Failure action** | Block merge |
| **How to fix** | `pytest tests/component/<failing_path> -v` — fix service logic or test doubles |

### Stage 7 — Integration Tests (Non-Live)

| Field | Value |
|-------|-------|
| **Tool** | `pytest tests/integration -m "not sandbox and not live_readonly and not market_hours" --ignore=tests/integration/brokers/dhan --ignore=tests/integration/brokers/upstox` |
| **What it checks** | Cross-module flows, event replay determinism, auth integration (auto-skips without creds) |
| **Blocking?** | ✅ **Yes** |
| **Timeout** | 20 minutes |
| **Failure action** | Block merge |
| **How to fix** | Run locally with `PYTHONPATH=src pytest tests/integration/<path> -v` — usually a wiring or adapter issue |

### Stage 8 — Coverage Gate

| Field | Value |
|-------|-------|
| **Tool** | `coverage report --fail-under=80` + per-module gates |
| **What it checks** | Branch coverage across all source modules |
| **Thresholds** | Overall: ≥ 80% · Brokers: ≥ 85% · OMS Core: ≥ 90% · Application: ≥ 80% |
| **Blocking?** | ✅ **Yes** |
| **Timeout** | 5 minutes (report only — coverage collected during Stage 4–7) |
| **Failure action** | Block merge. Shows missing lines in output |
| **How to fix** | Add tests for uncovered branches. Use `coverage report --show-missing` to find gaps |

### Stage 9 — Security Scan

| Field | Value |
|-------|-------|
| **Tool** | `bandit -r src/ -ll` + `gitleaks detect` + `safety check` + secret scan (git grep) |
| **What it checks** | Code vulnerabilities (bandit), leaked secrets (gitleaks), dependency CVEs (safety), tracked credential files |
| **Blocking?** | ⚠️ **Partial** — bandit HIGH = blocking, safety = advisory, gitleaks = blocking |
| **Timeout** | 10 minutes |
| **Failure action** | HIGH severity bandit finding: block merge. Safety CVEs: warn. Gitleaks: block |
| **How to fix** | Bandit: fix the insecure pattern. Gitleaks: remove the secret, rotate keys, add to .gitignore. Safety: upgrade the vulnerable dependency |

### Stage 10 — File Size Gate

| Field | Value |
|-------|-------|
| **Tool** | New architecture test (proposed: `tests/architecture/test_file_size_gate.py`) |
| **What it checks** | New files ≤ 400 LOC, new classes ≤ 200 LOC |
| **Blocking?** | ⚠️ **Warning** (initially) → ✅ **Yes** (after baseline is set) |
| **Timeout** | 2 minutes |
| **Failure action** | Warn on PR, block after baseline established |
| **How to fix** | Decompose oversized files/classes. Extract into focused modules. Use god-object decomposition pattern from Phase 2 |

---

## 3 · Gate Priority Matrix

| Priority | Gate | Blocks PR Merge | Failure Action | Fix Time |
|----------|------|:-:|----------------|----------|
| **P0** | Ruff Lint + Format | ✅ | Block merge | < 1 min (`ruff check --fix . && ruff format .`) |
| **P0** | Import Linter Contracts | ✅ | Block merge | 5–30 min (refactor import) |
| **P0** | Architecture Tests | ✅ | Block merge | 5–30 min (depends on violation) |
| **P0** | Unit Tests | ✅ | Block merge | 5–30 min |
| **P0** | Coverage ≥ 80% | ✅ | Block merge | 10–60 min (add tests) |
| **P1** | MyPy (domain+OMS) | ✅ | Block merge | 5–15 min |
| **P1** | Component Tests | ✅ | Block merge | 5–30 min |
| **P1** | Integration Tests (non-live) | ✅ | Block merge | 10–30 min |
| **P1** | Per-module Coverage (brokers ≥ 85%, OMS ≥ 90%) | ✅ | Block merge | 15–60 min |
| **P2** | Bandit HIGH Severity | ✅ | Block merge | 5–15 min |
| **P2** | Gitleaks Secret Detection | ✅ | Block merge | 5–10 min (rotate + remove secret) |
| **P2** | File Size Gate (400 LOC / 200 LOC) | ⚠️ → ✅ | Warn → Block | 15–60 min (decompose) |
| **P3** | MyPy (brokers) | ⚠️ | Warning only | Deferred to P7 |
| **P3** | Safety Dependency Check | ⚠️ | Advisory | Upgrade dependency |
| **P3** | Mutmut (nightly) | ⚠️ | Advisory | Improve test quality |
| **P3** | Broker Doctor Smoke | ⚠️ | Warn-only | Environment/config issue |

### Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Blocks PR merge (required status check) |
| ⚠️ | Warning only (advisory, visible but non-blocking) |
| P0 | Must pass before any merge — architectural integrity |
| P1 | Must pass — functional correctness |
| P2 | Must pass — security hygiene |
| P3 | Advisory — tracked for incremental improvement |

---

## 4 · Local Development Commands

```bash
# Full local gate check (mirrors CI lint stage)
pre-commit run --all-files

# Individual stages
ruff check .                          # Stage 1: lint
ruff format --check .                 # Stage 1: format
PYTHONPATH=src mypy src/domain/       # Stage 2: types
PYTHONPATH=src lint-imports --config pyproject.toml  # Stage 3: imports
PYTHONPATH=src pytest tests/unit -q --tb=short       # Stage 4: unit
PYTHONPATH=src pytest tests/architecture/ -q --tb=short  # Stage 5: arch
PYTHONPATH=src pytest tests/component -q --tb=short  # Stage 6: component
PYTHONPATH=src pytest tests/integration -m "not sandbox and not live_readonly" --tb=short  # Stage 7: integration
coverage report --fail-under=80       # Stage 8: coverage
bandit -r src/ -ll                    # Stage 9: security

# Nightly only
mutmut run --paths-to-mutate src/domain/ --runner "PYTHONPATH=src python -m pytest -x -q"
```

---

## 5 · CI Workflow File Map

| Workflow File | Trigger | Purpose |
|---------------|---------|---------|
| `ci.yml` | push/PR to main+develop | **Primary CI** — all stages above |
| `architecture-enforcement.yml` | push/PR (`.py`, `pyproject.toml`, pre-commit) | Ruff, exception hierarchy, import rules, print statements, architecture fitness, import smoke |
| `production_gate.yml` | push to release/v* tags | Unit, chaos, memory, security, code quality, replay determinism, certification |
| `mutation_nightly.yml` | cron 03:00 UTC daily | Mutation testing (advisory) |
| `broker_live_certify.yml` | cron + manual dispatch | Live broker verification (paper, dhan, upstox) |
| `dhan-regression.yml` | cron + manual + v* tags | Dhan regression (off-market, market-hours, sandbox, full) |
| `load-test.yml` | cron Monday + manual | Paper broker load testing |
| `web.yml` | push/PR to `web/` | Frontend build, Vitest, Playwright e2e |
