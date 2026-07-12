# Code Review Checklist — TradeXV2

> **Phase 3 Deliverable D3.3** · Last updated: 2026-07-12

Use this checklist for every PR. Each item links to the enforcing mechanism —
automated test, linter rule, or manual review — so reviewers know what is
self-enforcing vs. what needs human judgment.

---

## 1 · Architecture Compliance

| # | Check | Enforcing Mechanism | Auto? |
|---|-------|---------------------|:-----:|
| A1 | Domain layer imports from nothing (no application, brokers, analytics, interface, infrastructure, datalake, config, tradex, runtime) | `tests/architecture/test_domain_isolation.py` · `import-linter` contract "Domain independence" | ✅ |
| A2 | No broker-specific code in generic paths (application, infrastructure, interface must not import `brokers.dhan`, `brokers.upstox`, `brokers.paper`) | `import-linter` contracts "Application broker isolation", "CLI/API broker isolation" · `ruff` TID252 banned-api | ✅ |
| A3 | No `brokers.common` imports from concrete broker packages | `import-linter` contract "Broker common isolation" · `tests/architecture/test_broker_data_access_compliance.py` | ✅ |
| A4 | New files under 400 LOC | `tests/architecture/test_production_code_fitness_rules.py` (proposed Stage 10 file size gate) | ⚠️ |
| A5 | New classes under 200 LOC | Manual review + proposed architecture test | ⚠️ |
| A6 | Architecture tests added for new patterns/constraints | Manual review — if the PR introduces a new architectural invariant, a corresponding `tests/architecture/test_*.py` must be included | ❌ |
| A7 | Infrastructure does not import application or domain (except allowed domain subsets) | `import-linter` contract "Infrastructure independence" | ✅ |
| A8 | Application layer does not import infrastructure (except documented composition-root exceptions) | `import-linter` contract "Application infrastructure separation" · `tests/architecture/test_import_direction_and_layering.py` | ✅ |
| A9 | Analytics does not import OMS/execution (D2 constraint) | `import-linter` contracts "Trading does not import Analytics" + inverse | ✅ |
| A10 | Runtime does not import interface (except documented shims) | `import-linter` contract "Runtime does not import interface" | ✅ |
| A11 | Tradex public API does not import concrete brokers | `import-linter` contract "Tradex public API broker isolation" | ✅ |
| A12 | No phantom/removed directories still imported | `tests/architecture/test_module_boundaries_and_decomposition.py::test_removed_phantom_directories_not_imported` | ✅ |

---

## 2 · Code Quality

| # | Check | Enforcing Mechanism | Auto? |
|---|-------|---------------------|:-----:|
| Q1 | No bare `except:` clauses | `tests/architecture/test_cross_cutting_concerns.py::TestNoBareExcept` · ruff B001 | ✅ |
| Q2 | No `__import__("logging")` anti-pattern | Manual review — grep for `__import__` in source files | ❌ |
| Q3 | No `PYTEST_CURRENT_TEST` in production code | Manual review — grep `PYTEST_CURRENT_TEST` outside `tests/` | ❌ |
| Q4 | Logging uses `getLogger(__name__)` | `tests/architecture/test_cross_cutting_concerns.py::TestNoBasicConfig` (blocks `logging.basicConfig` in production) | ✅ |
| Q5 | Token/secret redaction in log statements | `tests/architecture/test_cross_cutting_concerns.py::TestNoTokenLeakage` + `TestGuardrailNoBareTokenLogging` · `tests/architecture/test_no_security_id_leak.py` | ✅ |
| Q6 | No `logging.basicConfig()` in production code | `tests/architecture/test_cross_cutting_concerns.py::TestNoBasicConfig` | ✅ |
| Q7 | No `print()` in production code | `architecture-enforcement.yml` → "No Print Statements" job | ✅ |
| Q8 | Exception hierarchy: all exceptions inherit from `TradeXV2Error` | `tests/architecture/test_cross_cutting_concerns.py::TestExceptionHierarchy` · `scripts/architecture/check_exception_hierarchy.py` · pre-commit hook `check-exception-hierarchy` | ✅ |
| Q9 | No `ssl._create_unverified_context` or `verify=False` | `tests/architecture/test_cross_cutting_concerns.py::TestGuardrailNoVerifyFalse` | ✅ |
| Q10 | No `pickle.load` on untrusted data | `tests/architecture/test_cross_cutting_concerns.py::TestGuardrailNoPickleLoad` | ✅ |
| Q11 | No inline Upstox URLs (use centralized config) | `tests/architecture/test_cross_cutting_concerns.py::TestGuardrailNoInlineUpstoxUrls` | ✅ |
| Q12 | No `_load_dotenv` duplication | `tests/architecture/test_no_scattered_dotenv.py` | ✅ |
| Q13 | No `simulate_event` in production code | `tests/architecture/test_cross_cutting_concerns.py::TestPhase8Guardrails::test_no_simulate_event_in_production_code` | ✅ |
| Q14 | No manual retry loops (use `@retry` framework) | `tests/architecture/test_production_code_fitness_rules.py::TestRetryUsage::test_no_manual_retry_loops` | ✅ |
| Q15 | Constants in canonical location, not scattered | `scripts/verify/check_constants_placement.py` (CI lint job) | ✅ |
| Q16 | No hardcoded credentials | `tests/architecture/test_production_code_fitness_rules.py::TestConfigurationValidation::test_no_hardcoded_credentials` | ✅ |
| Q17 | `ruff check` passes (all selected rules) | `ruff check .` in pre-commit + CI Stage 1 | ✅ |
| Q18 | `ruff format` passes (formatting consistency) | `ruff format --check .` in pre-commit + CI Stage 1 | ✅ |
| Q19 | `mypy` passes for domain + OMS core | `mypy` in pre-commit + CI Stage 2 | ✅ |

---

## 3 · Testing

| # | Check | Enforcing Mechanism | Auto? |
|---|-------|---------------------|:-----:|
| T1 | Unit tests for new logic | Manual review — PR should include `tests/unit/` changes for any new production code | ❌ |
| T2 | Protocol-based fakes, not MagicMock | Manual review — prefer `typing.Protocol` fakes over `unittest.mock.MagicMock`. See `tests/unit/` for examples | ❌ |
| T3 | Test names describe behavior (not implementation) | `tests/architecture/test_test_suite_uses_behavioral_names.py` | ✅ |
| T4 | Architecture tests pass | `pytest tests/architecture/ -q --tb=short` — CI Stage 5 (blocking) | ✅ |
| T5 | Coverage does not decrease | `coverage report --fail-under=80` — CI Stage 8. Check `coverage diff` if available | ✅ |
| T6 | Tests use markers correctly (`unit`, `component`, `architecture`, `integration`) | `pytest --strict-markers` (enforced by `pyproject.toml` addopts) | ✅ |
| T7 | No integration/live tests without proper markers | `pytest` will fail on unmarked tests hitting external services; review test markers for integration tests | ✅ |
| T8 | Chaos/concurrency tests included for new concurrency paths | `tests/architecture/test_concurrency_boundary.py` · `tests/architecture/test_stream_oms_lock_discipline.py` | ✅ |
| T9 | Broker contract tests for new broker adapters | Manual review — new broker adapters need tests in `tests/unit/brokers/certification/` | ❌ |
| T10 | No `@pytest.mark.skip` without a linked issue | Manual review — skips should reference a tracked issue | ❌ |

---

## 4 · Security

| # | Check | Enforcing Mechanism | Auto? |
|---|-------|---------------------|:-----:|
| S1 | No hardcoded secrets or API keys | `tests/architecture/test_production_code_fitness_rules.py::TestConfigurationValidation::test_no_hardcoded_credentials` · `ruff` S105/S106 · gitleaks pre-commit | ✅ |
| S2 | Input validation with Pydantic where applicable | Manual review — new API endpoints and public interfaces should validate inputs with Pydantic models | ❌ |
| S3 | Auth checks where needed | `tests/architecture/test_eng004_auth_default.py` · Manual review for new endpoints | ✅ |
| S4 | No security ID leakage at public boundaries | `tests/architecture/test_no_security_id_leak.py` — scans interface, CLI, MCP, services for `security_id`, `instrument_token` | ✅ |
| S5 | No tracked credential files (.env.local, .env.upstox) | CI lint job "Secret scan (tracked env files)" — `git ls-files --error-unmatch .env.local .env.upstox` | ✅ |
| S6 | No `DHAN_ACCESS_TOKEN`/`DHAN_PIN` in tracked source | CI lint job — `git grep -E 'DHAN_ACCESS_TOKEN|DHAN_PIN'` | ✅ |
| S7 | Bandit HIGH severity scan clean | `bandit -r src/ -ll` — CI Stage 9 (blocking for HIGH) | ✅ |
| S8 | Gitleaks scan clean | gitleaks pre-commit hook + CI Stage 9 | ✅ |
| S9 | `verify=False` not used in production | `tests/architecture/test_cross_cutting_concerns.py::TestGuardrailNoVerifyFalse` | ✅ |
| S10 | No pickle.load on untrusted data | `tests/architecture/test_cross_cutting_concerns.py::TestGuardrailNoPickleLoad` | ✅ |
| S11 | Broker tokens not exposed in public API/CLI output | `tests/architecture/test_no_security_id_leak.py` | ✅ |
| S12 | No `detect-private-key` / `detect-aws-credentials` violations | pre-commit hook `detect-private-key` + `detect-aws-credentials` | ✅ |

---

## 5 · Documentation

| # | Check | Enforcing Mechanism | Auto? |
|---|-------|---------------------|:-----:|
| D1 | Public API changes documented | Manual review — if a public function/class signature changes, docstring and any ADR must be updated | ❌ |
| D2 | ADR for architectural decisions | Manual review — new architectural patterns, boundary changes, or design trade-offs need an ADR in `docs/adr/` | ❌ |
| D3 | Docstrings on public methods | Manual review — all public (non-underscore) methods should have docstrings | ❌ |
| D4 | README updated if needed | Manual review — if setup steps, CLI usage, or project structure changes, update README | ❌ |
| D5 | CI workflow changes documented | Manual review — changes to `.github/workflows/*.yml` should be explained in PR description | ❌ |
| D6 | Import linter contract changes explained | Manual review — if `pyproject.toml` `[tool.importlinter.contracts]` changes, PR description must explain why | ❌ |

---

## 6 · Performance

| # | Check | Enforcing Mechanism | Auto? |
|---|-------|---------------------|:-----:|
| P1 | No I/O under lock (no `time.sleep`, network calls inside `with lock:`) | `tests/architecture/test_concurrency_boundary.py` · `tests/architecture/test_stream_oms_lock_discipline.py` · `tests/architecture/test_production_code_fitness_rules.py::TestRetryUsage` | ✅ |
| P2 | Bounded collections (no unbounded queues/lists in hot paths) | Manual review — check for `list.append()` in loops without size limits; use `collections.deque(maxlen=N)` | ❌ |
| P3 | No pandas in domain layer | `tests/architecture/test_domain_no_pandas_import.py` | ✅ |
| P4 | Thread safety verified for new shared-state classes | `tests/architecture/test_stream_oms_lock_discipline.py` — RLock must guard position/order mutations. Manual review for new concurrent structures | ⚠️ |
| P5 | No blocking calls in async functions | Manual review — async methods should not call `time.sleep()`, synchronous HTTP, or blocking I/O | ❌ |
| P6 | Lock ordering consistent (no deadlock risk) | Manual review — if multiple locks are acquired, ensure consistent ordering across all call sites | ❌ |

---

## 7 · Broker Integration

| # | Check | Enforcing Mechanism | Auto? |
|---|-------|---------------------|:-----:|
| B1 | No broker-name branching (if/elif dhan/upstox/paper) in application layer | `tests/architecture/test_no_broker_name_branching.py` · `tests/architecture/test_oms_no_broker_name_branching.py` | ✅ |
| B2 | New broker adapters implement the gateway ABC | `tests/architecture/test_gateway_abc_compliance.py` · `tests/architecture/test_gateway_signatures.py` | ✅ |
| B3 | Broker gateway surface is frozen | `tests/architecture/test_gateway_surface_freeze.py` | ✅ |
| B4 | Cross-broker imports forbidden | `ruff` TID252 banned-api (brokers.dhan → brokers.upstox) · `import-linter` "Broker common isolation" | ✅ |
| B5 | UI does not import concrete broker packages | `import-linter` contracts "CLI broker-implementation isolation", "API broker-implementation isolation" | ✅ |
| B6 | Broker certification tests pass | CI `unit-and-contract` job → `pytest tests/unit/brokers/certification -m certification` · `broker --broker paper verify && broker --broker paper certify --json` | ✅ |
| B7 | Ledger outbox boundary respected | `tests/architecture/test_ledger_outbox_boundary.py` · `tests/architecture/test_shadow_parity_gate.py` | ✅ |
| B8 | Factory migration complete (no raw `create_gateway`) | `ruff` TID252 banned-api for `infrastructure.gateway.factory.create_gateway` · `tests/architecture/test_factory_migration.py` | ✅ |

---

## 8 · How to Use This Checklist

### For Authors (before opening PR)

1. Run `pre-commit run --all-files` locally — catches most auto-enforced items
2. Run `PYTHONPATH=src pytest tests/architecture/ -q --tb=short` — catches architecture violations
3. Self-review against non-auto items (❌ column) before requesting review

### For Reviewers

1. **Skip auto-enforced items** — CI already catches them. Focus on ❌ and ⚠️ items
2. **Check the PR description** — should explain *why*, not just *what*
3. **Verify test coverage** — new logic needs new tests; coverage shouldn't decrease
4. **Watch for architecture creep** — even if import-linter passes, check if the change *spirit* respects boundaries
5. **Security mindset** — for any change touching auth, tokens, or external input, review S1–S12

### Gate Mapping to CI Stages

| CI Stage | Checklist Section |
|----------|-------------------|
| Stage 1: Lint & Format | Q17, Q18 |
| Stage 2: Type Check | Q19 |
| Stage 3: Import Contracts | A1–A3, A7–A12, B4, B5 |
| Stage 4: Unit Tests | T1, T6, T7 |
| Stage 5: Architecture Tests | A1–A12, Q1, Q4–Q16, T3, T8, P1, P3, P4, B1–B8, S1, S4, S9–S11 |
| Stage 6: Component Tests | T2, T8 |
| Stage 7: Integration Tests | T7, T9 |
| Stage 8: Coverage Gate | T5 |
| Stage 9: Security Scan | S1, S5–S8, S12 |
| Stage 10: File Size Gate | A4, A5 |
