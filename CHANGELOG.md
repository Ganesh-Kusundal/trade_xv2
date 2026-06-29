# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### V2.2 — Multi-Agent Parallel Orchestration (2026-06-25)
#### Added
- **HTTP observability server** — `GET /healthz`, `GET /readyz`, `GET /metrics` (Prometheus format)
- **Chaos test suite** — 10 deterministic failure-mode tests (B10)
- **LifecycleManager** — owns all background services (TokenRefreshScheduler, ReconciliationService, DailyPnlResetScheduler, WebSocket threads)
- **CircuitBreaker split** — Dhan circuit breaker now has 3 categories (A1)
- **Thread-safe RiskManager** — RLock-protected mutators and readers (A2+A3)
- **DailyPnlResetScheduler** — resets running PnL at IST 00:00 (B7)
- **Real capital sizing** — OMS RiskManager sized to `gateway.funds().available_balance` (C.1)

#### Changed
- **OMS-first execution** — all orders flow through OrderManager for risk checks (ADR-007)
- **Domain single source** — canonical domain types in `domain/` package (ADR-001)
- **Exchange resolution layer** — centralized `parse_segment()` in `brokers/common/core/exchange_segments.py` (ADR-006)
- **Batch fetch mixin** — shared parallel fetch utility (ADR-004)
- **Option chain domain type** — canonical option chain representation (ADR-008)
- **Execution service facade** — unified execution entry point (ADR-009)

#### Fixed
- **TUI widget broker readiness** — graceful degradation when broker not ready (CHANGELOG_V2.1)
- **OMS wireup test type mismatch** — corrected `OrderRequest` to `BrokerOrderPayload` (CHANGELOG_V2.1)
- **Mypy Python version** — aligned to 3.13 from 3.12 (CHANGELOG_V2.1)
- **Mypy import checking** — removed global ignore, added per-module overrides (CHANGELOG_V2.1)
- **Coverage configuration** — cleaned up source and omit lists (CHANGELOG_V2.1)
- **DhanOrderCommandAdapter.cancel_order** — now checks `status == "success"` (Phase 0)
- **_extract_future_underlying** — replaced rstrip character class with regex (Phase 0)
- **Quote model** — added missing `security_id` field (Phase 0)
- **Gateway.limit_buy(price=0)** — now raises `ValueError` (Phase 0)

#### Removed
- **Deprecated modules** — 9 modules deleted (~1,800 LOC) (C.4+C.5+C.6)
- **Duplicate ADR-003** — removed reconciliation-engine.md (duplicate of broker-abstraction-audit.md)

#### Security
- **Kill switch enforcement** — blocks orders deterministically (B7)
- **Pre-trade risk validation** — enforced before REST submission
- **Audit logging** — all order placements, modifications, cancellations logged

### Phase 0 — Foundation
#### Added
- `pyproject.toml` — unified project configuration
- `.github/workflows/ci.yml` — CI pipeline (lint, unit, contract, integration)
- `.pre-commit-config.yaml` — pre-commit hooks (ruff, mypy, hygiene)
- `.github/dependabot.yml` — weekly dependency updates
- Coverage measurement (≥60% baseline)
- `docs/IMPORT_DIRECTION_RULES.md` — architectural invariants
- `docs/DATA_DICTIONARY.md` — canonical data schemas
- `docs/UPSTOX_WIRE_FORMAT.md` — Upstox endpoint audit
- `CONTRIBUTING.md` — contributor guide
- `SECURITY.md` — vulnerability disclosure policy
- `agent.md` — module-by-module onboarding guide

## [0.1.0] - PRE-PHASE-0

Initial framework, broker-agnostic abstractions, Dhan/Upstox adapters, contract tests.

[Unreleased]: https://github.com/Ganesh-Kusundal/trade_xv2/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Ganesh-Kusundal/trade_xv2/releases/tag/v0.1.0
