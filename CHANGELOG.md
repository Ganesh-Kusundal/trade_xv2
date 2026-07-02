# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Phase 0 — Foundation (in progress)
#### Added
- `pyproject.toml` — unified project configuration
- `.github/workflows/ci.yml` — CI pipeline (lint, unit, contract, integration)
- `.pre-commit-config.yaml` — pre-commit hooks (ruff, mypy, hygiene)
- `.github/dependabot.yml` — weekly dependency updates
- Coverage measurement (≥60% baseline)
- `MYPY.md` — type-check error budget
- `docs/coverage-history.md` — coverage tracking
- `CHANGELOG.md` — this file
- `CONTRIBUTING.md` — contributor guide
- `SECURITY.md` — vulnerability disclosure policy
- `docs/retros/` — phase retrospective templates
- **Containerization:** `Dockerfile`, `Dockerfile.dev`, `docker-compose.yml` with Prometheus/Grafana monitoring stack
- **Labelled metrics:** `LabelledCounter`, `LabelledGauge`, `LabelledHistogram` in `MetricsRegistry` for dynamic label combinations
- **OMS context:** `application/execution/context.py` with `oms_managed()` context manager to prevent duplicate event publishing
- **Analytics coverage gate:** `test_all_feature_classes_have_tests()` dynamically discovers Feature classes and asserts test coverage

#### Changed
- **MarketBridge optimization:** O(N×M) → O(N+M) WebSocket dispatch using reverse index (`_symbol_index`) for O(1) symbol→connection routing
- **Centralized data paths:** All modules now use `DEFAULT_DATA_ROOT` from `datalake/core/paths.py` instead of hardcoded `"market_data"`
- **Typed gateway resolution:** `BrokerService.active_gateway` property replaces string-based attribute probing
- **HttpRequestMetrics migration:** Now delegates to central `MetricsRegistry` instead of maintaining separate counters
- **Dhan adapter normalization:** `place_order()`, `modify_order()`, `cancel_order()` now return `OrderResponse` (matching Upstox pattern) instead of `Order`/raising `OrderError`
- **IdempotencyCache:** Now stores `OrderResponse` instead of `Order` for consistency

#### Fixed
- **`DhanOrderCommandAdapter.cancel_order` misclassifies errors** — now checks `status == "success"`.
- **`DhanWebSocketConnectionManager._create_websocket_connection` returns a stub** — now logs WARNING (full replacement in Phase 4).
- **`_extract_future_underlying` strips valid characters** — replaced rstrip character class with regex.
- **`Quote` model missing `security_id` field** — field added; mappers updated.
- **`Gateway.limit_buy(price=0)` silently places market order** — now raises `ValueError`.
- **Duplicate ORDER_PLACED events** — OMS path now suppresses adapter-level event publishing via context variable
- **Dead MetricsCollector code** — removed unused `collector_snapshot` parameter and 3 `_render_collector_*` functions
- **Analytics test gaps** — added tests for 11 untested Feature classes (RelativeVolume, VolumeSMA, SwingHighLow, etc.)

## [0.1.0] - PRE-PHASE-0

Initial framework, broker-agnostic abstractions, Dhan/Upstox adapters, contract tests.

[Unreleased]: https://github.com/YOUR_ORG/Trade_XV2/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YOUR_ORG/Trade_XV2/releases/tag/v0.1.0
