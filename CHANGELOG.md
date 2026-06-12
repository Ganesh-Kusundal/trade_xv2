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

#### Fixed
- **`DhanOrderCommandAdapter.cancel_order` misclassifies errors** — now checks `status == "success"`.
- **`DhanWebSocketConnectionManager._create_websocket_connection` returns a stub** — now logs WARNING (full replacement in Phase 4).
- **`_extract_future_underlying` strips valid characters** — replaced rstrip character class with regex.
- **`Quote` model missing `security_id` field** — field added; mappers updated.
- **`Gateway.limit_buy(price=0)` silently places market order** — now raises `ValueError`.

## [0.1.0] - PRE-PHASE-0

Initial framework, broker-agnostic abstractions, Dhan/Upstox adapters, contract tests.

[Unreleased]: https://github.com/YOUR_ORG/Trade_XV2/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YOUR_ORG/Trade_XV2/releases/tag/v0.1.0
