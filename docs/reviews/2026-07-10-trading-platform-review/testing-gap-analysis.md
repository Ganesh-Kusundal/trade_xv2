# Testing Gap Analysis

## Assessment

The repository has broad test taxonomy and many meaningful component/integration suites. The weakness is not test count; it is that several gates can be green without validating production behavior.

## Present coverage

- Unit tests cover domain, indicators, broker adapters, resilience, parsing, and some security controls.
- Component tests cover OMS composition, risk concurrency, reconciliation, and UI lifecycle.
- Integration tests cover APIs, broker contracts, WebSockets, datalake, and restart/replay paths.
- E2E and chaos directories exist.
- `pyproject.toml` declares parity, live-readonly, stress, memory, pre-production, and sandbox markers (`pyproject.toml:105-140`).

## Critical gaps

### 1. Contract tests are too shallow

The broker contract suite checks a subset of attributes and cannot prove semantic equivalence across Dhan, Upstox, and Paper (`src/brokers/common/contracts/broker_contract.py:43-81`). It must assert typed returns, order state transitions, error classes, capabilities, timestamp semantics, partial fills, and reconciliation behavior.

### 2. Real-data integration is optional rather than a release truth source

Live tests skip on missing gateways, rate limits, credentials, or market-hours conditions. This is appropriate for developer convenience but unsafe as a production gate: an outage can produce a green build. Separate “not runnable” from “passed,” and require a scheduled environment with explicit availability status.

### 3. Chaos tests accept unsafe data

Some corruption tests allow missing OHLCV, NaN/∞, and negative prices to proceed (`tests/chaos/test_data_corruption.py:48-132`). The production contract should reject or quarantine invalid market data and prove that no order decision is emitted from it.

### 4. Architecture tests can miss production code

Some tests scan `brokers` or `infrastructure` rather than `src/brokers` and `src/infrastructure` (`tests/architecture/test_production_code_fitness_rules.py:170-197`, `tests/unit/security/test_security_controls.py:18-24`). A passing scan can therefore mean zero files were inspected.

### 5. CI gates are advisory or stale

Mypy, Bandit, Safety, benchmarks, and mutation testing are non-blocking or ignored in workflows. CI references obsolete paths such as `brokers/dhan/tests`, and production gates reference missing suites (`.github/workflows/ci.yml`, `.github/workflows/production_gate.yml`, `.github/workflows/dhan-regression.yml`).

## Missing behavior tests

- Broker accepts an order, response is lost, process restarts, and reconciliation prevents duplicate submission.
- Two concurrent signals reserve the same exposure and one is rejected atomically.
- Partial fill, out-of-order fill, duplicate cumulative fill, and overfill.
- Broker disconnect during order acknowledgement and recovery after restart.
- Exchange event time versus receipt time, clock skew, delayed burst delivery, and stale-data blocking.
- Full economic reconciliation: fill quantity, average price, fees, multiplier, realized/unrealized PnL, and cash.
- Multi-symbol chronological portfolio simulation with shared cash.
- Feature pipeline failure must block signal generation.
- Kill-switch blocks new entries but permits explicitly authorized emergency exits/flattening.
- WebSocket queue overflow and client resync from a sequence/checkpoint.
- Authenticated and authorized feature-flag mutation, webhook signature verification, secret rotation, and audit durability.

## Correct test pyramid

1. Pure domain property tests for state transitions, sizing, decimal/price rules, and PnL.
2. Component tests using real in-process repositories/event stores and real serializers; doubles only at external network boundaries.
3. Contract tests against every broker adapter and a real Paper transport using the same port.
4. Read-only live integration tests against real broker endpoints with explicit environment availability and freshness assertions.
5. Sandbox order lifecycle tests with broker-side reconciliation, never inferred success.
6. Restart and chaos tests around network ambiguity, duplicate events, event-log failure, queue overflow, and stale data.
7. Performance tests with enforced budgets, not warning output.

## Release gate redesign

A gate must report four states: `passed`, `failed`, `not_run`, and `blocked_by_environment`. `not_run` cannot satisfy a production promotion. Critical controls (type checks at broker boundaries, security scanning, reconciliation, duplicate-write tests, and data validity) must be blocking. Coverage remains a signal, not the release criterion.
