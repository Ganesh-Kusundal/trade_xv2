# D0.8 — Risk Register

> **Generated:** 2026-07-12 | **Scope:** TradeXV2 transformation program | **Method:** Code analysis + architecture review

Risks are organized by category. Each risk includes a concrete mitigation strategy grounded in the current codebase state.

---

## 1. Technical Risks

| ID | Description | Severity | Probability | Impact | Mitigation Strategy | Owner |
|----|-------------|----------|-------------|--------|---------------------|-------|
| **RT-01** | **God class decomposition breaks behavior** — Splitting ReplayEngine (1125 LOC), TradingOrchestrator (807 LOC), RiskManager (678 LOC), and TradingContext (809 LOC) risks subtle behavioral changes. ReplayEngine alone mixes pipeline execution, order routing, position tracking, and result accumulation with shared mutable state across methods. | Critical | High | High | (a) Extract each new class behind a Protocol first; (b) Write behavioral characterization tests (golden-file snapshots) before touching any class; (c) Decompose one class at a time with full integration test pass between each; (d) Keep a temporary `LegacyXxx` adapter that delegates to the new split for 1 release. | Phase 5 Lead |
| **RT-02** | **Event split breaks imports** — `domain/events/types.py` (1008 LOC) is imported by ~30+ files across application, infrastructure, and analytics layers. Splitting into per-aggregate event files will break every `from domain.events.types import XxxEvent`. | High | High | High | (a) First add re-exports in `domain/events/types.py` pointing to new sub-modules; (b) Add `__all__` to preserve public API; (c) Use `lint-imports` (already configured in `pyproject.toml`) to verify no circular deps; (d) Phase the split: keep the old file as a re-export shim, remove only after all callers migrate. | Domain Lead |
| **RT-03** | **Capability catalog split breaks broker wiring** — `domain/capability_manifest/catalog.py` (905 LOC) is the single source for broker capabilities consumed by `brokers/session/session_factory.py`, `runtime/broker_discovery.py`, and `tradex/session.py`. Fragmenting it risks capability registry drift. | High | Medium | High | (a) Define a `CapabilityRegistry` Protocol before splitting; (b) Ensure `ensure_core_plugins()` fallback still works after split; (c) Add architecture test: "every broker module must register capabilities via the registry, not direct import." | Infrastructure Lead |
| **RT-04** | **Legacy `brokers/dhan/` dead code shadows active package** — Top-level `brokers/dhan/gateway.py` (536 LOC) and `orders.py` (801 LOC) coexist with the canonical `src/brokers/dhan/` package. Any sys.path misconfiguration could import the wrong module. | High | Medium | High | (a) Verify no imports reference the top-level `brokers/dhan/` via `grep -r "from brokers.dhan" --include="*.py"` on the whole tree (excluding `brokers/` itself); (b) Add `pyproject.toml` lint-imports rule to forbid imports from the top-level `brokers/` root; (c) Delete the directory in Phase 5 Task D5.1. | Platform Lead |
| **RT-05** | **`PYTEST_CURRENT_TEST` in production code creates hidden test coupling** — 5 production files (`order_manager.py`, `sqlite_order_store.py`, `auth.py`, `parity_gate.py`, `production_config.py`) branch behavior based on pytest's environment variable. If a non-pytest test runner is used, or `PYTEST_CURRENT_TEST` leaks into production, behavior changes silently. | Medium | Medium | High | (a) Replace with explicit `test_mode: bool` parameter or dependency injection; (b) For `OmsOrderCommand`, use a factory or fixture instead of runtime env-var check; (c) Add architecture test: `PYTEST_CURRENT_TEST` must not appear in `src/` (already planned in D1.9 guardrails). | Application Lead |
| **RT-06** | **`__import__("logging")` and `__import__("time")` anti-pattern in 10+ files** — Hides module dependencies from static analysis, linters, and import linter contracts. Found in `order_validator.py`, `trade_recorder.py`, `async_http_client.py` (3 usages), plus test files. | Low | High | Medium | (a) Replace with standard top-level imports; (b) Add lint rule (ruff `banned-api` or custom) to prevent `__import__` usage; (c) Low risk because behavior is identical, but blocks future tooling. | Any Engineer |
| **RT-07** | **Dual port abstractions: BrokerAdapter vs BrokerTransport** — Two overlapping Protocol/ABC surfaces for broker access (`domain/ports/broker_adapter.py` and `domain/ports/broker_transport.py`) with no clear ownership. Wire-layer code bypasses both via string-method calls. | Medium | Medium | Medium | (a) Consolidate into a single port hierarchy (ADR-014/013 revision); (b) Enforce via architecture test: no direct wire-method calls from application layer; (c) Address in Phase 2 contract freeze. | Domain Lead |
| **RT-08** | **Import boundary violations: UI → concrete broker packages** — `interface/ui/services/*` directly imports `brokers.dhan.identity.account_registry`, `brokers.dhan.wire.DhanBrokerGateway`, `brokers.upstox.mappers.domain_mapper`, bypassing the import-linter contract. | Medium | High | Medium | (a) Route all broker access through `infrastructure.broker_plugin` or `application.composer` registry; (b) Fix the `lint-imports` config to catch these (currently not enforced); (c) Add explicit `ignore_imports` removal. | Interface Lead |
| **RT-09** | **Scattered `__import__` in test code masks missing dependencies** — Tests use `__import__("pytest")`, `__import__("os")`, `__import__("sys")`, `__import__("domain")` in 15+ locations, defeating static analysis and making test dependency graphs opaque. | Low | Low | Low | (a) Convert to standard imports; (b) Add ruff `banned-api` rule project-wide. | Test Engineer |

---

## 2. Operational Risks

| ID | Description | Severity | Probability | Impact | Mitigation Strategy | Owner |
|----|-------------|----------|-------------|--------|---------------------|-------|
| **RO-01** | **No deployment infrastructure** — No `Dockerfile`, `docker-compose.yml`, `Makefile`, or `Procfile` exists. `.dockerignore` is present but unused. The only artefact is `.github/dependabot.yml`. Deploying requires manual `pip install -e .` on a server. | Critical | High | Critical | (a) Create a minimal `Dockerfile` + `docker-compose.yml` for local dev parity; (b) Add a `Makefile` or `justfile` for common tasks; (c) Target: containerised local dev → staging deploy pipeline within Phase 1. | Platform Lead |
| **RO-02** | **CI/CD pipeline gaps** — GitHub Actions workflows exist (`ci.yml`, `architecture-enforcement.yml`, `production_gate.yml`, `dhan-regression.yml`, `broker_live_certify.yml`, `mutation_nightly.yml`, `web.yml`, `load-test.yml`) but there is no automated deploy pipeline. CI validates code quality but does not produce deployable artefacts. | High | Medium | High | (a) Add a `deploy-staging.yml` workflow triggered on main branch merge; (b) Add artifact build (wheel/sdist) to CI; (c) Target: automated staging deploy by end of Phase 1. | Platform Lead |
| **RO-03** | **No production monitoring or alerting** — The codebase has `application/observability.py` and `infrastructure/observability/` modules, but no configured alerting, no metrics export to a time-series DB, and no log aggregation setup. `infra/resilience/broker_health_monitor.py` exists but its output destination is unclear. | High | High | High | (a) Configure Prometheus metrics export (already instrumented via `prometheus_client` in broker code); (b) Set up Grafana dashboards for broker health, order flow, and PnL; (c) Add PagerDuty/OpsGenie alerting for kill-switch and circuit-breaker events. | Platform Lead |
| **RO-04** | **No secret management for production** — `SecretManager` (429 LOC) handles Fernet encryption, but production secrets (Dhan API tokens, Upstox OAuth) are stored in `.env.local` files on disk. No vault integration, no rotation automation. | High | Medium | Critical | (a) Integrate with a secrets manager (AWS SSM / HashiCorp Vault); (b) `EncryptedTokenStore` already handles at-rest encryption — extend to support remote backends; (c) Add automated token rotation for Dhan TOTP flow. | Security Lead |
| **RO-05** | **No database migration strategy** — SQLite stores exist (`oms_orders.sqlite`, `journal.sqlite`, `backtest_results.sqlite`, `catalog.duckdb`) but no migration framework (Alembic, etc.) is in place. Schema changes require manual intervention. | Medium | Medium | High | (a) Add Alembic for SQLite schema versioning; (b) Create initial migration from current schema; (c) Target: migration framework in place before Phase 3 schema changes. | Data Lead |
| **RO-06** | **`market_data/` root directory contains runtime artefacts in repo** — SQLite databases, DuckDB files, JSON snapshots, and WAL files exist in `market_data/`. These should be in `.gitignore` or a data volume, not tracked. | Medium | High | Medium | (a) Add `market_data/*.sqlite*`, `market_data/*.duckdb`, `market_data/*.json` to `.gitignore`; (b) Ensure `market_data/` is created at runtime, not committed; (c) Check git history for committed binary bloat. | Platform Lead |
| **RO-07** | **No structured logging in production** — While `logging_config.py` exists and `getLogger(__name__)` is used consistently, no configuration for structured JSON logging, log correlation IDs, or log shipping is wired up in production. | Medium | Medium | Medium | (a) Wire structured JSON logging in production config; (b) Add correlation_id propagation to all loggers; (c) Set up log aggregation (ELK / Loki). | Platform Lead |

---

## 3. Business Risks

| ID | Description | Severity | Probability | Impact | Mitigation Strategy | Owner |
|----|-------------|----------|-------------|--------|---------------------|-------|
| **RB-01** | **Live trading disruption during refactoring** — Phase 5 god-class decomposition touches the hot path (order placement, risk checks, position tracking). A bug in decomposition could reject valid orders, double-place orders, or miss risk limits. | Critical | Medium | Critical | (a) All Phase 5 changes behind feature flags with instant rollback; (b) Run `broker_live_certify.yml` + `dhan-regression.yml` before every merge to main; (c) Shadow-mode testing: run decomposed path alongside legacy path and diff results for 1 week; (d) No live trading changes during market hours. | Trading Lead |
| **RB-02** | **Data loss during event schema migration** — Splitting `domain/events/types.py` could break event serialization/deserialization for events in transit or in journals. `journal.sqlite` and `oms_orders.sqlite` contain serialized event data. | High | Medium | High | (a) Add schema version to all event payloads before splitting; (b) Write migration script to update stored events; (c) Test deserialization of all existing stored events against new schema; (d) Backup all SQLite files before any migration. | Data Lead |
| **RB-03** | **Backward-compat shim removal breaks third-party integrations** — The `tradex.runtime` facade re-exports 80+ module paths with deprecation warnings. Removing these shims in Phase 3-4 could break any external code importing from `tradex.runtime.*`. | Medium | Medium | Medium | (a) Keep deprecation warnings for 2 major versions; (b) Publish migration guide before removal; (c) Monitor deprecation warning logs to identify active consumers; (d) Add changelog entry for each removal batch. | API Lead |
| **RB-04** | **Broker credential exposure during refactoring** — Refactoring `brokers/dhan/identity/`, `brokers/dhan/auth/`, and `SecretManager` in a live environment could expose tokens if encryption boundaries are temporarily weakened. | High | Low | Critical | (a) Never refactor encryption/credential paths without a security review; (b) Ensure `EncryptedTokenStore` is not broken by any refactoring (add architecture test); (c) Rotate all credentials after any security-adjacent change. | Security Lead |
| **RB-05** | **Paper trading parity loss during decomposition** — `PaperGateway` and live broker gateways share the `IBrokerGateway` protocol. Refactoring one without the other could break the paper/live parity that `dhan-regression.yml` and `broker_live_certify.yml` validate. | Medium | Medium | High | (a) Any protocol change must update all implementations (dhan, upstox, paper) atomically; (b) Run certification suite after each protocol change; (c) Maintain a "protocol change checklist" in PR template. | Trading Lead |

---

## 4. Schedule Risks

| ID | Description | Severity | Probability | Impact | Mitigation Strategy | Owner |
|----|-------------|----------|-------------|--------|---------------------|-------|
| **RS-01** | **Scope creep from Phase 1 into Phase 5** — Architecture guardrails (D1.9) define max 400 LOC / 200 LOC per class, but fixing existing violations requires Phase 5 work. Pressure to "just fix it now" could derail Phase 1 deliverables. | High | High | High | (a) Phase 1 only adds enforcement (lint rules, architecture tests); violations are logged as debt, not fixed; (b) Track violations via `tech_debt_register.md` (D0.5); (c) Phase gate: Phase 1 closes only when all guardrails are enforced, not when violations are fixed. | Program Lead |
| **RS-02** | **Parallel work conflicts on shared files** — `domain/events/types.py`, `domain/universe.py`, and `application/oms/context.py` are touched by multiple workstreams (analytics, OMS, trading). Parallel PRs will conflict. | High | High | Medium | (a) Assign file ownership per workstream in `CODEOWNERS` (already exists); (b) Use stacked PRs or feature branches per workstream; (c) Merge order: domain → application → infrastructure → interface; (d) Weekly integration merge to `main`. | Program Lead |
| **RS-03** | **Missing automated test coverage for critical paths** — The codebase has tests but mutation testing (`mutation_nightly.yml`) suggests gaps. Refactoring without adequate coverage risks silent regressions. | High | Medium | High | (a) Before Phase 5, ensure mutation score ≥ 80% for `application/oms/`, `application/trading/`, `domain/risk/`; (b) Add characterization tests for all god classes before decomposition; (c) Block Phase 5 start on coverage gate. | Test Lead |
| **RS-04** | **Legacy facade shim maintenance burden** — The 80+ entry `tradex.runtime` deprecation shim must be maintained during the entire transition period. Each new module requires a shim entry; forgetting to update it causes silent import failures. | Medium | Medium | Medium | (a) Automate shim generation from the canonical module map; (b) Add CI check: "if a `tradex.runtime.*` import is used, the shim must exist"; (c) Set a hard deadline for shim removal (end of Phase 4). | Platform Lead |
| **RS-05** | **Dependency on external broker APIs for testing** — `dhan-regression.yml` and `broker_live_certify.yml` require live broker connections. Network issues or broker downtime can block CI. | Medium | High | Low | (a) Add offline mock mode to certification suite; (b) Cache broker responses for CI replay; (c) Allow manual override to skip broker tests with justification. | Test Lead |
| **RS-06** | **Phase 3-4 engineering standards adoption lag** — Standards (D3.1 handbook, D3.3 review checklist) require team-wide behavioral change. Old habits (`__import__`, magic numbers, `MagicMock`) persist without enforcement. | Medium | High | Medium | (a) Enforce via CI (ruff rules, architecture tests) not just documentation; (b) Add pre-commit hooks for `__import__` detection; (c) Monthly "standards compliance" scorecard from CI metrics. | Engineering Lead |

---

## Risk Matrix Summary

| Severity ↓ \ Probability → | Low | Medium | High |
|----------------------------|-----|--------|------|
| **Critical** | RB-04 | RB-01, RT-01 | RO-01 |
| **High** | — | RT-03, RB-02, RO-02 | RT-02, RT-04, RO-03, RO-04, RS-01, RS-02, RS-03 |
| **Medium** | RT-09 | RT-07, RO-05, RO-07, RB-03, RB-05 | RT-05, RT-06, RT-08, RO-06, RS-04, RS-05, RS-06 |
| **Low** | — | — | — |

**Top 5 risks requiring immediate attention:**
1. **RO-01** — No deployment infrastructure (blocks any production use)
2. **RT-01** — God class decomposition breaking behavior (highest-impact refactoring risk)
3. **RB-01** — Live trading disruption during refactoring (financial exposure)
4. **RO-03** — No production monitoring (invisible failures)
5. **RS-02** — Parallel work conflicts on shared files (schedule impact)

---

## Related Documents

- [D0.5 — Technical Debt Register](./tech_debt_register.md)
- [Transformation Roadmap](../TRANSFORMATION_ROADMAP.md)
- [Deep Review 2026-07-11](../roadmap/DEEP-REVIEW-2026-07-11.md)
- [Execution Roadmap](../roadmap/TRADING-OS-EXECUTION-ROADMAP.md)
