# Production Certification Criteria

## Overview

This document defines the requirements and verification steps for certifying
the TradeXV2 system as production-ready. All criteria must pass before any
release branch can be merged to `main` or deployed to production.

---

## Quick Reference

| # | Requirement | Test File | Threshold | Status |
|---|------------|-----------|-----------|--------|
| 1 | Unit Tests | `tests/` | All passing | 🔴 Required |
| 2 | Chaos Tests | `tests/chaos/` | 40+ tests passing | 🔴 Required |
| 3 | Memory Tests | `tests/regression/test_memory_leaks.py` | 15+ tests passing | 🔴 Required |
| 4 | Test Coverage | Coverage report | ≥ 90% | 🔴 Required |
| 5 | Security Scan | Bandit | 0 HIGH vulnerabilities | 🔴 Required |
| 6 | Linting | Ruff | 0 errors | 🟡 Warning |
| 7 | Formatting | Ruff format | Consistent | 🟡 Warning |
| 8 | Type Checking | MyPy | Tracked (non-blocking) | 🟡 Warning |
| 9 | Replay Determinism | `scripts/verify_event_replay.py` | Deterministic | 🔴 Required |

---

## 1. Unit Tests

**File**: All files under `tests/`

**What it verifies**: Core functionality, contract compliance, and business logic correctness.

**How it works**:
```bash
pytest -m "not integration and not sandbox and not live_readonly" \
    --cov=brokers --cov=cli --cov=datalake --cov=analytics \
    --cov-branch --cov-report=xml
```

**Pass criteria**: All tests pass, exit code 0.

**Remediation**:
- Fix the failing test — do NOT skip it unless there's a documented reason
- If a test is flaky, add `@pytest.mark.flaky(reruns=3)` and file a ticket
- Check for environment-dependent assumptions (file paths, env vars)

---

## 2. Chaos Engineering Tests

### 2.1 Network Partition Chaos Tests

**File**: `tests/chaos/test_network_partitions.py` (25 tests)

**What it verifies**: The system survives network failures gracefully.

| Test Category | Tests | What It Checks |
|--------------|-------|----------------|
| Broker API Mid-Order | 6 | Health monitor detects failures, gateway falls back to healthy broker, degraded mode serves stale cache but rejects writes |
| WebSocket Disconnect | 5 | Event bus continues dispatching after handler crash, DLQ captures failures, metrics track errors |
| Connection Lost During Write | 5 | Event log failures don't block dispatch, fail_fast mode propagates errors, thread safety under contention |
| Network Latency Spikes | 4 | Slow handlers don't block others, cache avoids redundant latency, dispatch order preserved |
| Partial Failures | 10 | Per-broker health tracking, routing around unhealthy brokers, mixed handler results, immutable snapshots |

**Pass criteria**: All 25 tests pass, each completing in < 5 seconds.

**Key patterns**:
- Health monitor transitions broker from healthy → unhealthy after threshold failures
- IntelligentGateway automatically routes around unhealthy brokers
- EventBus dispatches to all handlers even if some crash
- DeadLetterQueue captures all failures for later replay

**Remediation**:
- If health monitor test fails: verify `failure_threshold` logic in `BrokerHealthMonitor`
- If fallback test fails: check `_route()` method in `IntelligentGateway`
- If event bus test fails: verify `_handle_handler_failure()` doesn't block dispatch loop

### 2.2 Data Corruption Chaos Tests

**File**: `tests/chaos/test_data_corruption.py` (30 tests)

**What it verifies**: The system detects and handles corrupted data.

| Test Category | Tests | What It Checks |
|--------------|-------|----------------|
| Corrupted DataFrame | 7 | Empty DF, missing columns, NaN/inf values, negative prices, out-of-order timestamps, large values |
| Corrupted Events | 4 | Naive timestamps, corrupted payloads, None values, empty event types |
| Duplicate Events | 6 | Both dispatched, monotonic sequence numbers, replay mode preserves originals, DLQ bounded capacity |
| Clock Skew | 4 | UTC timestamps, backdated/future events, timestamped counters with skew |
| Invalid State Transitions | 7 | Unknown broker health, state transitions, replay mode disables persistence, correlation ID injection |
| Concurrency Integrity | 6 | Concurrent subscribe/unsubscribe, metric increments, publishes, DLQ pushes, health records |

**Pass criteria**: All 30 tests pass, each completing in < 5 seconds.

**Key patterns**:
- ReplayEngine sorts timestamps automatically
- EventBus assigns monotonically increasing sequence numbers
- DLQ enforces max_size with drop tracking
- EventMetrics prunes old timestamped entries to prevent unbounded growth

**Remediation**:
- If replay engine test fails: verify `_run_single()` handles missing columns with defaults
- If sequence number test fails: check `_sequence_counter` increment logic in `EventBus.publish()`
- If DLQ test fails: verify `deque(maxlen=...)` is used

---

## 3. Memory Leak Regression Tests

**File**: `tests/regression/test_memory_leaks.py` (18 tests)

**What it verifies**: No unbounded memory growth in critical components.

| Test Category | Tests | What It Checks |
|--------------|-------|----------------|
| EventBus Memory | 4 | Rapid publishes bounded, subscribe/unsubscribe cycles, handler reference release, DLQ bounded |
| ReplayEngine Memory | 2 | Bounded deque window, O(window_size) not O(n_bars) memory |
| Cache Eviction | 4 | TTLCache maxsize enforcement, TTL expiry, IntelligentGateway cache bounds |
| Reference Cycles | 4 | EventBus, DomainEvent, HealthMonitor, EventMetrics — no uncollectable cycles |
| DataFrame Memory | 4 | No full DF reference held, cache returns copies, column access is view, memory tracking |
| Overall Growth | 3 | Sustained load < 10MB, GC stability, metrics pruning |

**Measurement approach**:
- `tracemalloc` for precise allocation tracking
- `gc.collect()` + `gc.garbage` for reference cycle detection
- `weakref` for verifying reference release
- Bounded growth assertions (< 10MB over 1000 iterations)

**Pass criteria**: All 18 tests pass, memory growth within bounds.

**Remediation**:
- If EventBus memory test fails: check that event objects are not stored after dispatch
- If ReplayEngine memory test fails: verify `deque(maxlen=config.window_size)` is used
- If cache eviction test fails: check TTLCache configuration in `DataLakeGateway`
- If reference cycle test fails: look for circular references in `__init__` methods

---

## 4. Test Coverage

**Threshold**: ≥ 90% (line + branch)

**How it works**:
```bash
pytest --cov=brokers --cov=cli --cov=datalake --cov=analytics \
    --cov-branch --cov-fail-under=90
```

**What's measured**:
- `brokers/` — All broker implementations and common infrastructure
- `cli/` — CLI entry points and commands
- `datalake/` — Data lake gateway and utilities
- `analytics/` — Replay engine, pipelines, strategies

**Remediation**:
- Add tests for uncovered lines — don't add `# pragma: no cover` without justification
- Focus on critical paths: order lifecycle, event handling, risk gates
- Use `pytest --cov-report=term-missing` to identify specific uncovered lines

---

## 5. Security Scan

**Tool**: Bandit (HIGH severity = FAIL)

**How it works**:
```bash
bandit -r brokers/ cli/ datalake/ analytics/ -ll -f json
```

**Severity levels**:
- **HIGH**: Immediate failure — must be fixed before merge
- **MEDIUM**: Warning — should be addressed in next sprint
- **LOW**: Informational — track in backlog

**Common findings and fixes**:

| Finding | Fix |
|---------|-----|
| Hardcoded password/secret | Use environment variables or secret manager |
| `eval()` / `exec()` | Replace with safe parsing (`json.loads`, `ast.literal_eval`) |
| SQL injection | Use parameterized queries (DuckDB supports `?` placeholders) |
| Insecure temp file | Use `tempfile.mkstemp()` or `tempfile.NamedTemporaryFile()` |
| Missing SSL verification | Always verify SSL (`verify=True` in requests) |

**Remediation**:
- Fix the underlying code issue
- Add a test that verifies the fix
- Document why the fix is correct in a code comment

---

## 6. Linting

**Tool**: Ruff

**Threshold**: 0 errors (warnings allowed)

```bash
ruff check .
ruff format --check .
```

**Remediation**:
- Run `ruff check --fix .` for auto-fixable issues
- Manually fix remaining issues
- For intentional deviations, add `# noqa: <rule>` with explanation

---

## 7. Formatting

**Tool**: Ruff format

**Threshold**: Consistent formatting across codebase

```bash
ruff format .
```

**Remediation**:
- Run `ruff format .` to auto-format
- Commit formatting changes separately from functional changes

---

## 8. Type Checking

**Tool**: MyPy

**Status**: Tracked (non-blocking) — existing errors logged, new code must be typed

```bash
mypy brokers/
```

**Goal**: Reduce to 0 errors by Phase 4

**Remediation**:
- Add type hints to new code
- Fix existing errors incrementally
- Use `# type: ignore` sparingly with explanation

---

## 9. Replay Determinism

**Script**: `scripts/verify_event_replay.py`

**What it verifies**: Running the same replay twice produces identical results.

**Why it matters**: Backtest results must be reproducible for regulatory compliance and strategy validation.

**Pass criteria**: Two consecutive runs produce byte-identical output.

**Remediation**:
- Check for non-deterministic operations (random seeds, current time, unordered dicts)
- Ensure `sequence_number` is used for event ordering
- Verify `replay_mode=True` preserves original timestamps

---

## Running the Full Certification

```bash
# Interactive (verbose output)
python scripts/production_certification.py --verbose

# CI-friendly (JSON output)
python scripts/production_certification.py --json > report.json

# Individual checks
pytest tests/chaos/ -v           # Chaos tests only
pytest tests/regression/ -v      # Memory tests only
bandit -r brokers/ -ll           # Security scan only
```

---

## CI Workflow

The production gate runs automatically on:
- Push to `release/**` branches
- Push to `v*.*.*` tags
- Pull requests to `release/**` with `production-gate` label
- Manual trigger via `workflow_dispatch`

See `.github/workflows/production_gate.yml` for the full workflow definition.

**Workflow phases**:
1. Unit & Contract Tests (parallel)
2. Chaos Engineering Tests (parallel)
3. Memory Leak Regression Tests (parallel)
4. Security Vulnerability Scan (parallel)
5. Code Quality Checks (parallel)
6. Replay Determinism Check (parallel)
7. Production Certification Gate (sequential, depends on all above)
8. Summary Report

**The certification gate blocks merge if ANY check fails.**

---

## Troubleshooting

### Tests Pass Locally but Fail in CI
- Check for environment differences (Python version, OS)
- Look for timing-dependent tests (add `time.sleep()` or use mocks)
- Verify file paths are relative, not absolute

### Coverage Drops Unexpectedly
- New code paths without tests
- Changed control flow (e.g., added error handling branch)
- Run `pytest --cov-report=term-missing` to find exact uncovered lines

### Memory Test Fails Intermittently
- GC timing is non-deterministic — increase the bound slightly
- Check for platform-specific memory behavior
- Use `gc.collect()` before measurement for consistency

### Security Scan Flags False Positive
- Add `# nosec` comment with explanation
- File a ticket to review and potentially suppress the rule

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-06-22 | Initial certification criteria |
