# TradeXV2 Engineering Handbook

> **The single source of truth for coding standards, architectural rules, and review criteria.**
> Every engineer and AI agent must consult this document before writing code.

---

## Table of Contents

1. [Naming Conventions](#1-naming-conventions)
2. [Dependency Rules](#2-dependency-rules)
3. [File Size Limits](#3-file-size-limits)
4. [Logging Standards](#4-logging-standards)
5. [Error Handling Standards](#5-error-handling-standards)
6. [Testing Standards](#6-testing-standards)
7. [Documentation Standards](#7-documentation-standards)
8. [Security Standards](#8-security-standards)
9. [Performance Standards](#9-performance-standards)
10. [Code Review Checklist](#10-code-review-checklist)

---

## 1. Naming Conventions

### 1.1 Files

| Context | Convention | Example |
|---|---|---|
| Modules | `snake_case.py` | `order_manager.py`, `rate_limiter.py` |
| Test files | `test_<subject>.py` | `test_order_placement.py` |
| Architecture tests | `test_<invariant>.py` | `test_domain_isolation.py` |
| `__init__.py` | Must define `__all__` for packages with public API | `brokers/dhan/__init__.py` |
| `__init__.py` | Must have module docstring (≥20 chars) | `"""Dhan broker adapter package."""` |

### 1.2 Classes

| Context | Convention | Example |
|---|---|---|
| Regular classes | `PascalCase` | `OrderManager`, `StructuredFormatter` |
| Exception classes | Must end with `Error` | `BrokerError`, `RateLimitError` (enforced by `TestNamingConventions`) |
| Protocol interfaces (application layer) | `I` prefix + `Protocol` | `IOrderManager`, `IRiskManager`, `IBrokerGateway` |
| Protocol interfaces (domain ports) | `PascalCase` + `Port` suffix | `OrderServicePort`, `DataProvider`, `MetricsRegistryPort` |
| Data classes | `PascalCase` | `OmsOrderCommand`, `OrderResult` |
| Fakes / Test Doubles | `Fake` prefix | `FakeOrderManager`, `FakeRiskManager` |
| Filters / Formatters | Descriptive `PascalCase` | `TokenRedactionFilter`, `StructuredFormatter` |

**Protocol naming decision:** The codebase uses **two conventions** depending on layer:

- **Application layer** (`application/oms/protocols.py`): Uses `I` prefix — `IOrderManager(Protocol)`, `IRiskManager(Protocol)`, `IBrokerGateway(Protocol)`.
- **Domain ports** (`domain/ports/`): Uses descriptive `PascalCase` with `Port` suffix — `OrderServicePort(Protocol)`, `DataProvider(Protocol)`, `MetricsRegistryPort(Protocol)`.

Do **not** mix conventions within a layer. New application-layer protocols use `I` prefix. New domain ports use `Port` suffix.

### 1.3 Functions and Methods

| Context | Convention | Example |
|---|---|---|
| Regular functions | `snake_case` | `configure_logging()`, `get_logger()` |
| Test functions | `test_<behavior>` | `test_domain_does_not_import_from()`, `test_oms_has_no_live_broker_name_literals()` |
| Private helpers | `_leading_underscore` | `_extract_import_root()`, `_iter_domain_prod_files()` |
| Factory functions | `create_<thing>` | `create_trading_context()`, `create_domain_event()` |
| Boolean returns | `is_<condition>` / `has_<state>` / `can_<action>` | `is_token_expired()`, `is_market_open()` |
| Setup functions | `setup_<thing>` | `setup_exception_handlers()` |

### 1.4 Constants

| Context | Convention | Example |
|---|---|---|
| Module-level constants | `UPPER_SNAKE_CASE` | `FORBIDDEN_LAYERS`, `LIVE_BROKER_NAMES` |
| Frozen sets | `_<UPPER_SNAKE_CASE>` (private) | `_DHAN_PUBLIC`, `_SENSITIVE_EXTRA_KEYS` |
| Compiled regexes | `_<UPPER_SNAKE_CASE>` | `_TOKEN_PATTERNS`, `_BANNED` |

### 1.5 Private Members

- Single leading underscore: `_method()`, `_field` — internal implementation detail.
- Double leading underscore (`__name`) — use **only** for name-mangling in class hierarchies (rare).
- Do **not** use trailing underscores.

### 1.6 Import Ordering

Enforced by ruff (`I` rule, isort). Standard order within each group, separated by blank lines:

```
# 1. __future__ imports
from __future__ import annotations

# 2. Standard library
import ast
import json
import logging
from pathlib import Path

# 3. Third-party packages
import pytest
from fastapi import FastAPI

# 4. Project imports (absolute from src/)
from domain.errors import BrokerError
from application.oms.protocols import IOrderManager
from infrastructure.logging_config import get_logger
```

**Rules:**
- Always use absolute imports from `src/` root (e.g., `from domain.errors import ...`).
- Never use relative imports (`.`, `..`) — they break with namespace packages.
- `from __future__ import annotations` must be the first import in every file.

---

## 2. Dependency Rules

### 2.1 Architectural Layers

The codebase follows a strict layered architecture with dependency direction flowing **inward** (toward the domain):

```
┌──────────────────────────────────────────────────────────┐
│                    interface                              │
│              (ui, api, agent, cli, mcp)                   │
├──────────────────────────────────────────────────────────┤
│                    runtime                                │
│          (composition root, event loop, wiring)           │
├──────────────────────────────────────────────────────────┤
│                  application                              │
│         (oms, execution, trading, services)               │
├──────────────────────────────────────────────────────────┤
│                 infrastructure                            │
│  (event bus, logging, metrics, resilience, gateway)       │
├──────────────────────────────────────────────────────────┤
│               brokers / analytics / datalake              │
│        (adapter plugins, strategy engines, storage)       │
├──────────────────────────────────────────────────────────┤
│                     domain                                │
│     (entities, value objects, ports, errors, events)      │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Import-Linter Contracts (from `pyproject.toml`)

All contracts are enforced by `import-linter` in CI (`lint-imports --config pyproject.toml`).

| # | Contract Name | Source | Forbidden |
|---|---|---|---|
| 1 | **Domain independence** | `domain` | `infrastructure`, `brokers`, `analytics`, `datalake`, `interface`, `application`, `tradex`, `runtime`, `config` |
| 2 | **Infrastructure independence** | `infrastructure` | `brokers`, `analytics`, `interface`, `application` |
| 3 | **Analytics broker-adapter isolation** | `analytics` | `brokers.dhan`, `brokers.upstox`, `brokers.paper` |
| 4 | **Trading does not import Analytics (D2)** | `application.oms`, `application.execution` | `analytics` |
| 5 | **Analytics does not import Trading OMS/execution (D2 inverse)** | `analytics` | `application.oms`, `application.execution` |
| 6 | **Broker common isolation** | `brokers.common` | `brokers.dhan`, `brokers.upstox`, `brokers.paper`, `analytics` |
| 7 | **Application broker isolation** | `application` | `brokers.dhan`, `brokers.upstox`, `brokers.paper`, `brokers.common` |
| 8 | **Analytics does not import interface presentation** | `analytics` | `interface.ui`, `interface.api` |
| 9 | **Dispatcher broker isolation** | `runtime.commands`, `runtime.queries` | `brokers.dhan`, `brokers.upstox`, `brokers.paper`, `brokers.common` |
| 10 | **Runtime does not import interface** | `runtime` | `interface` |
| 11 | **Application infrastructure separation** | `application` | `infrastructure` |
| 12 | **CLI broker-implementation isolation** | `interface.ui` | `brokers.dhan`, `brokers.upstox`, `brokers.paper` |
| 13 | **API broker-implementation isolation** | `interface.api` | `brokers.dhan`, `brokers.upstox`, `brokers.paper` |
| 14 | **Tradex public API broker isolation** | `tradex` | `brokers.dhan`, `brokers.upstox`, `brokers.paper` |
| 15 | **UI uses connect shims not raw factory** | `interface.ui` | `infrastructure.gateway.factory` |

### 2.3 Allowed Exceptions (Documented `ignore_imports`)

These are the sanctioned cross-layer imports. New exceptions require an ADR and a comment in `pyproject.toml`:

| Contract | Exception | Reason |
|---|---|---|
| Infrastructure independence | `infrastructure.gateway.factory → brokers.paper` | Composition root constructs broker gateways |
| Infrastructure independence | `infrastructure.gateway.factory → datalake.gateway` | Gateway factory imports datalake re-exports |
| Infrastructure independence | `infrastructure.broker_infrastructure → runtime.broker_infrastructure` | Thin re-export shim |
| Application infrastructure separation | `application.composer.router → infrastructure.observability.audit` | Cross-cutting audit logging |
| Application infrastructure separation | `application.composer.router → infrastructure.time.clock` | Clock abstraction |
| Application infrastructure separation | `application.services.historical_data → infrastructure.historical_data` | Thin re-export |
| Application infrastructure separation | `application.services.production_readiness → infrastructure.security.ssl_hardening` | TLS inspection |
| Application broker isolation | `application.oms.tests.* → brokers.common.**` | Test-only integration |
| Broker common isolation | `brokers.common.tests.* → brokers.dhan.**` | Test-only integration |
| Analytics does not import interface | `analytics.replay.engine → interface.ui.services.compose` | Known residual (REF-6) |
| Runtime does not import interface | `runtime.api_bootstrap → interface.api.bootstrap` | Back-compat shim |

### 2.4 Banned Imports (Ruff `flake8-tidy-imports`)

These are compile-time errors, not just linter warnings:

| Banned Import | Message |
|---|---|
| `brokers.dhan.domain.Quote` | Import Quote from domain, not from brokers.dhan.domain |
| `brokers.dhan.domain.Balance` | Import Balance from domain, not from brokers.dhan.domain |
| `brokers.dhan.domain.DepthLevel` | Import DepthLevel from domain, not from brokers.dhan.domain |
| `brokers.dhan.domain.MarketDepth` | Import MarketDepth from domain, not from brokers.dhan.domain |
| `interface.ui` | Lower layers cannot import from interface.ui |
| `interface.api` | Lower layers cannot import from interface.api |
| `brokers.dhan` | Cannot import in brokers.common or other broker packages |
| `brokers.upstox` | Cannot import in brokers.common or other broker packages |
| `infrastructure.gateway.factory.create_gateway` | Use bootstrap_gateway or require_gateway |

### 2.5 Ruff Lint Rules Enabled

```
E, W      — pycodestyle
F         — pyflakes
I         — isort
B         — flake8-bugbear
UP        — pyupgrade
G         — flake8-logging-format
N         — pep8-naming
RUF       — ruff-specific
S         — flake8-bandit (security)
C4        — flake8-comprehensions
SIM       — flake8-simplify
TID       — flake8-tidy-imports
```

Globally ignored: `E501` (line length — handled by formatter), `B008` (FastAPI defaults), `S101` (assert), `S104` (hardcoded bind).

---

## 3. File Size Limits

| Threshold | Action |
|---|---|
| **< 300 LOC** | Ideal — no action needed |
| **300–400 LOC** | Soft warning — consider splitting |
| **400–600 LOC** | Review required — must justify in PR description |
| **> 600 LOC** | Hard limit — must be split before merge (architecture test enforcement proposed) |

**Current largest files** (from codebase scan):

| File | LOC | Status |
|---|---|---|
| `analytics/replay/engine.py` | 1,125 | Needs decomposition |
| `domain/events/types.py` | 1,008 | Needs decomposition |
| `domain/capability_manifest/catalog.py` | 905 | Needs decomposition |
| `domain/instruments/instrument.py` | 819 | Needs decomposition |
| `application/oms/context.py` | 809 | Needs decomposition |

**Guidelines for splitting large files:**
- Extract cohesive groups of functions/classes into new modules.
- Preserve the module's public API in `__init__.py` with re-exports.
- Run `python -m py_compile <file>` and the full test suite after splitting.

---

## 4. Logging Standards

### 4.1 Getting a Logger

```python
# CORRECT — every module gets its own logger
import logging
logger = logging.getLogger(__name__)

# WRONG — never do this
import __import__("logging")
logger = logging.getLogger("hardcoded_name")
```

**Why:** `__name__` automatically produces hierarchical logger names (`domain.services.history`), enabling per-module filtering and the correlation filter.

### 4.2 Logging Configuration

Call `configure_logging()` once at application startup:

```python
from infrastructure.logging_config import configure_logging

configure_logging(service="api", level="INFO")
```

Configuration is controlled by environment variables:
- `XV2_LOG_LEVEL` — Log level (default: `INFO`)
- `APP_ENV` — `production`/`prod` selects JSON format; anything else selects human-readable format
- `TRADING_SERVICE_NAME` — Service name in structured logs (default: `trading-platform`)

### 4.3 Token Redaction

The `TokenRedactionFilter` is installed by default and redacts:
- `access_token`, `refresh_token`, `api_key`, `api_secret`, `password` in key=value patterns
- `Authorization: Bearer <token>` headers
- URL query parameters `?token=<value>`
- Broker-specific tokens (`DHAN_*TOKEN`, `UPSTOX_*TOKEN`, etc.)
- Any string ≥32 alphanumeric characters that matches token patterns
- Sensitive `extra` fields: `token`, `access_token`, `refresh_token`, `api_key`, `api_secret`, `password`, `pin`, `totp`, `totp_secret`, `authorization`, `bearer_token`, and any key ending in `_token`

**You must never disable token redaction in production.** Disable only in controlled test environments:

```python
configure_logging(service="test", enable_redaction=False)
```

### 4.4 Correlation ID

Every log record automatically includes:
- `correlation_id` — from `infrastructure.correlation.get_current_correlation_id()`
- `service_name` — from configuration

These are injected by `CorrelationFilter` and appear in both JSON and human-readable output.

### 4.5 Structured JSON (Production)

In production (`APP_ENV=production`), logs are JSON:

```json
{
  "timestamp": "2026-07-12T09:30:00.000+00:00",
  "service": "api",
  "level": "INFO",
  "logger": "application.oms.order_manager",
  "message": "Order placed",
  "module": "order_manager",
  "function": "place_order",
  "line": 42,
  "correlation_id": "abc-123",
  "order_id": "ORD-001",
  "symbol": "RELIANCE"
}
```

### 4.6 Human-Readable (Development)

In development, logs are colorized with ANSI codes:
```
HH:MM:SS.mmm LEVEL logger_name                        message [correlation_id] key=value
```

### 4.7 Log Level Guidance

| Level | When to Use |
|---|---|
| `DEBUG` | Detailed diagnostic info: variable values, branch decisions, cache hits. Never in hot paths in production. |
| `INFO` | Significant business events: order placed/cancelled, session started, configuration loaded. |
| `WARNING` | Recoverable issues: rate limit approaching, broker degraded, retry attempted. Not an error — the system continues. |
| `ERROR` | Unrecoverable failures: order rejected, broker authentication failed, data corruption detected. Requires attention. |
| `CRITICAL` | System-threatening: all brokers down (degraded mode), circuit breaker permanently open, data store unreachable. Page on-call. |

**Use `extra={}` to attach structured context:**

```python
logger.info("Order placed", extra={"order_id": order_id, "symbol": symbol})
logger.error("Order failed", extra={"order_id": order_id, "reason": str(exc)})
```

### 4.8 File Handler

If `log_file` is provided to `configure_logging()`, a `RotatingFileHandler` is created:
- Max file size: 10 MB
- Backup count: 5
- Same filters (redaction + correlation) apply

---

## 5. Error Handling Standards

### 5.1 Exception Hierarchy

The canonical hierarchy lives in `domain/exceptions.py` (root) and `domain/errors.py` (broker/platform errors):

```
TradeXV2Error (domain/exceptions.py)
├── DataError
├── ConfigError
├── ValidationError
├── BrokerNotReadyError
├── NotConfiguredError
├── BrokerError (domain/errors.py)
│   ├── RetryableError (alias: TradeXV2RecoverableError)
│   │   └── NetworkError
│   ├── NonRetryableError
│   ├── RateLimitError
│   ├── CircuitBreakerOpenError
│   ├── AuthenticationError
│   ├── InstrumentNotFoundError
│   ├── OrderError
│   ├── NotSupportedError
│   │   └── ExitAllError
│   └── BrokerDegradedError

BrokerUnavailableError (inherits RuntimeError)
UnsupportedExtensionError (inherits NotImplementedError)
MergeConflictError (inherits ValueError)
RoutingError (inherits RuntimeError)
QuotaExhaustedError (inherits RuntimeError)
UnsupportedGatewayOperationError (inherits NotImplementedError, TradeXV2Error)
```

**Rules:**
- All domain-visible exceptions inherit from `TradeXV2Error`.
- Exception classes must end with `Error` (enforced by ruff `N818` and architecture test `TestNamingConventions`).
- New exception classes go in `domain/errors.py` (broker/platform errors) or `domain/exceptions.py` (cross-cutting errors).

### 5.2 HTTP Status Mapping

The global exception handler (`infrastructure/global_exception_handler.py`) maps exceptions to HTTP status codes:

| Exception | HTTP Status | Error Type |
|---|---|---|
| `AuthenticationError` | 401 | `broker_auth_error` |
| `RateLimitError` | 429 | `rate_limit_exceeded` |
| `OrderError` | 400 | `order_execution_error` |
| `CircuitBreakerOpenError`, `BrokerDegradedError` | 503 | `service_unavailable` |
| `InstrumentNotFoundError` | 404 | `instrument_not_found` |
| `ValidationError` | 422 | `validation_error` |
| `NotSupportedError` | 501 | `not_supported` |
| `DataError`, `ConfigError` | 500 | `data_error` / `config_error` |
| `RetryableError` | 503 | `recoverable_error` |
| `NonRetryableError` | 500 | `fatal_error` |
| `BrokerError` | 502 | `broker_error` |
| All other `TradeXV2Error` | 500 | `tradexv2_error` |
| Unexpected `Exception` | 500 | `internal_server_error` |

### 5.3 Error Handling Rules

1. **No bare `except:` clauses.** Always catch specific exceptions:
   ```python
   # CORRECT
   except (ConnectionError, TimeoutError) as exc:
   except BrokerError as exc:

   # WRONG
   except:
   except Exception:
   ```

2. **Never swallow errors silently.** Every `except` block must either re-raise, log, or handle explicitly:
   ```python
   # WRONG — silent swallow
   try:
       dangerous_operation()
   except Exception:
       pass

   # CORRECT — log and re-raise
   try:
       dangerous_operation()
   except BrokerError:
       logger.exception("dangerous_operation failed")
       raise
   ```

3. **Use `logger.exception()` for unexpected errors** — it captures the full traceback.

4. **DLQ for handler failures.** When an event handler fails, the event goes to the dead letter queue (`DeadLetterQueuePort`), not to a retry loop that could block processing.

5. **Domain exceptions, not broker exceptions.** Application and domain code raise `domain.errors.*` — never broker-specific exceptions. Broker adapters translate broker SDK exceptions into `domain.errors.*` at the adapter boundary.

6. **Debug info is gated.** The generic exception handler only exposes exception type/details when `TRADEXV2_DEBUG=1`:
   ```python
   if os.getenv("TRADEXV2_DEBUG", "").lower() in ("1", "true"):
       details["type"] = type(exc).__name__
   ```

---

## 6. Testing Standards

### 6.1 Test Pyramid

```
tests/
├── unit/          — Domain / pure business-rule tests (fast, isolated)
├── component/     — Single-service tests (OMS, execution, registry)
├── integration/   — Cross-service / adapter tests
├── e2e/           — End-to-end trading flow tests
├── architecture/  — Architecture boundary / import-linter guard tests
└── fakes/         — Protocol-based test doubles
```

### 6.2 Protocol-Based Fakes, Not MagicMock

**This is a hard requirement.** All test doubles implement Protocol interfaces and live in `tests/fakes/`.

```python
# tests/fakes/fake_oms.py

from application.oms.protocols import IOrderManager, IRiskManager

@dataclass
class FakeRiskManager(IRiskManager):
    """Observable, deterministic risk manager for testing."""
    allow_all: bool = True
    kill_switch_active: bool = False
    kill_switch_set_calls: list[bool] = field(default_factory=list)

    def set_kill_switch(self, enabled: bool) -> None:
        self.kill_switch_active = enabled
        self.kill_switch_set_calls.append(enabled)

    def check_order(self, order: Order) -> Any:
        if not self.allow_all:
            return SimpleNamespace(allowed=False, reason="risk check failed")
        return SimpleNamespace(allowed=True)
```

**Why not MagicMock:**
- Fakes are **observable** — you can assert on call counts, arguments, and state.
- Fakes are **deterministic** — no `.return_value` side effects or `.reset_mock()` boilerplate.
- Fakes are **self-documenting** — the fake's code shows what the test is actually testing.
- Fakes **fail at compile time** if the Protocol changes — MagicMock fails silently.

**Existing fakes:**

| Fake | Protocol | Location |
|---|---|---|
| `FakeRiskManager` | `IRiskManager` | `tests/fakes/fake_oms.py` |
| `FakePositionManager` | `IPositionManager` | `tests/fakes/fake_oms.py` |
| `FakeOrderManager` | `IOrderManager` | `tests/fakes/fake_oms.py` |
| `FakeReconciliationService` | `IReconciliationService` | `tests/fakes/fake_oms.py` |
| `FakeExecutionAdapter` | `IExecutionAdapter` | `tests/fakes/fake_oms.py` |
| `FakeBrokerGateway` | `IBrokerGateway` | `tests/fakes/fake_oms.py` |
| `FakeTradingOrchestrator` | `ITradingOrchestrator` | `tests/fakes/fake_trading.py` |

### 6.3 Test Naming

```
test_<behavior_under_test>
```

Examples:
- `test_domain_does_not_import_from` — tests the domain isolation rule
- `test_oms_has_no_live_broker_name_literals` — tests no broker name branching
- `test_central_module_exists_and_is_sanctioned_site` — tests concurrency boundary
- `test_public_surfaces_do_not_reference_broker_tokens` — tests security leak prevention

### 6.4 Pytest Configuration

From `pyproject.toml`:

```toml
asyncio_mode = "auto"                          # All async tests run automatically
asyncio_default_fixture_loop_scope = "function" # Fresh event loop per test function
addopts = "-ra --strict-markers --tb=short --durations=10"
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```

**Key settings:**
- `--strict-markers`: Unregistered markers cause errors (prevents typos).
- `--tb=short`: Concise tracebacks.
- `--durations=10`: Shows 10 slowest tests.

### 6.5 Pytest Markers

| Marker | Purpose | When to Use |
|---|---|---|
| `@pytest.mark.unit` | Domain / pure business-rule tests | No external dependencies, fast |
| `@pytest.mark.component` | Single-service tests | Mocked/doubled collaborators |
| `@pytest.mark.architecture` | Architecture boundary tests | Import checks, layering, naming |
| `@pytest.mark.integration` | Cross-service tests | Real adapters, shared state |
| `@pytest.mark.e2e` | End-to-end flow | Full trading lifecycle |
| `@pytest.mark.golden` | Golden dataset / replay parity | Deterministic output comparison |
| `@pytest.mark.chaos` | Chaos / concurrency stress | Recovery under failure |
| `@pytest.mark.contract` | Broker contract tests | Verify adapter conformance |
| `@pytest.mark.dhan` | DhanHQ integration | Requires Dhan credentials |
| `@pytest.mark.upstox` | Upstox-specific unit | Upstox SDK tests |
| `@pytest.mark.upstox_integration` | Upstox integration | Gated by `UPSTOX_INTEGRATION=1` |
| `@pytest.mark.sandbox` | Order placement tests | May place/cancel real orders |
| `@pytest.mark.live_readonly` | Live read-only | Reads from real endpoints |
| `@pytest.mark.performance` | Benchmarks | Latency / throughput |
| `@pytest.mark.slow` | Long-running (>1s) | Slow tests |
| `@pytest.mark.property` | Property-based (Hypothesis) | Fuzzing / invariant testing |
| `@pytest.mark.memory` | Memory profiling | Leak detection |
| `@pytest.mark.regression` | Regression suite | Run with `-m regression` |
| `@pytest.mark.market_hours` | Requires NSE 09:15–15:30 | Streaming / WebSocket tests |
| `@pytest.mark.auth_integration` | Live TOTP bootstrap | Auto-skips without creds |
| `@pytest.mark.certification` | Broker certification | CLI smoke tests |

### 6.6 Test Fixture Patterns

**Session-scoped wiring** (`conftest.py`):

```python
@pytest.fixture(scope="session", autouse=True)
def _register_domain_runtime_hooks() -> None:
    """Wire broker factories into domain hooks for analytics engines."""
    from application.execution.factory import create_oms_backtest_adapter
    from domain.runtime_hooks import register_oms_backtest_factory
    register_oms_backtest_factory(create_oms_backtest_adapter)
```

**Credential fixtures** — auto-skip when unavailable:

```python
@pytest.fixture(autouse=False)
def live_credentials():
    """Provides Dhan credentials or skips."""
    if not Path(".env.local").exists():
        pytest.skip(".env.local not found")
    # ... load and validate ...
    return client_id, access_token
```

**Builder helpers** — construct complex objects with sane defaults:

```python
def build_test_trading_context(**kwargs: Any) -> "TradingContext":
    """Build TradingContext with default event infrastructure for tests."""
    if "event_bus" not in kwargs:
        kwargs["event_bus"] = EventBus(...)
    return create_trading_context(**kwargs)
```

### 6.7 Coverage and Mutation Testing

| Tool | Threshold | Command |
|---|---|---|
| `pytest-cov` | 80% branch coverage (`fail_under = 80`) | `pytest --cov` |
| `mutmut` | 90% mutant kill rate (`fail_under = 90`) | `mutmut run` |

Coverage source: `brokers`, `analytics`, `interface`, `datalake`, `application`, `domain`, `infrastructure`, `runtime`, `tradex`, `config`.

Excluded from coverage: `*/tests/*`, `*/__init__.py`.

### 6.8 Architecture Test Requirements

Every new architectural invariant **must** have a corresponding architecture test in `tests/architecture/`. These tests use AST parsing, grep scanning, and import graph analysis to enforce rules.

**Current architecture tests:**

| Test File | Invariant Enforced |
|---|---|
| `test_domain_isolation.py` | Domain never imports outer layers |
| `test_import_direction_and_layering.py` | No circular dependencies between brokers; no shim imports; no deprecated event_bus paths |
| `test_gateway_surface_freeze.py` | Gateway public method sets cannot grow silently |
| `test_concurrency_boundary.py` | Only `runtime/event_loop.py` may call `asyncio.new_event_loop()` |
| `test_no_broker_name_branching.py` | OMS, cert suite, rate limiter cannot branch on broker name strings |
| `test_domain_no_pandas_import.py` | Domain modules have zero top-level pandas imports |
| `test_no_security_id_leak.py` | Public surfaces (interface, CLI, MCP, services) do not reference broker tokens |

When adding a new architectural rule:
1. Write a test in `tests/architecture/`.
2. Use AST parsing (preferred) or grep scanning.
3. Include a scan-root sanity check (assert files found > N to prevent silent false greens).
4. Document the rule in this handbook.

---

## 7. Documentation Standards

### 7.1 Docstring Format

Use Google-style docstrings with types:

```python
def configure_logging(
    service: str = "tradexv2",
    level: str | None = None,
    log_format: str | None = None,
    log_file: str | None = None,
    enable_redaction: bool = True,
) -> None:
    """Configure logging for the entire application.

    Args:
        service: Service name for log identification.
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env var
            XV2_LOG_LEVEL or INFO.
        log_format: 'json' for structured, 'human' for readable. Defaults to
            'json' in production, 'human' otherwise.
        log_file: Optional file path for log output.
        enable_redaction: If True (default), install TokenRedactionFilter.

    Raises:
        ValueError: If log_format is not 'json' or 'human'.
    """
```

**Minimum docstring requirements:**
- All `__init__.py` files must have a module-level docstring (≥20 characters).
- All public functions/classes must have docstrings.
- Private helpers: docstring recommended but not enforced.

### 7.2 Architecture Decision Records (ADRs)

Architectural decisions (new layers, changed boundaries, new dependencies, breaking conventions) must have an ADR:

```
docs/adr/NNNN-<title>.md
```

**ADR template:**

```markdown
# NNNN. <Decision Title>

## Status
Proposed | Accepted | Deprecated | Superseded by NNNN

## Context
What is the issue motivating this decision?

## Decision
What is the change being proposed?

## Consequences
What are the positive and negative outcomes?
```

### 7.3 Architecture Test Documentation

Every file in `tests/architecture/` must have a module docstring that:
1. States the architectural invariant being enforced.
2. References the design rule (e.g., DR-B1, TOS-P5-010, REF-012).
3. Explains what would break if the test were removed.

Example:
```python
"""DR-E2 / TOS-P5-010 concurrency boundary enforcement (mixed thread/asyncio).

Exactly ONE module in the tree — ``src/runtime/event_loop.py`` — may call
``asyncio.new_event_loop()``. All other call sites must use
``run_coro_sync`` / ``get_runtime_loop`` / ``new_dedicated_loop``.
"""
```

### 7.4 Public API Documentation

- Every package with `__all__` must document what the exported symbols represent.
- Broker packages (`brokers/dhan`, `brokers/upstox`, `brokers/common`) must define `__all__` in `__init__.py` (enforced by architecture test).
- Frozen gateway method sets in `test_gateway_surface_freeze.py` serve as living API documentation.

---

## 8. Security Standards

### 8.1 No Hardcoded Secrets

- **Never** commit API keys, tokens, passwords, or secrets to source code.
- Use environment variables or `.env.local` / `.env.upstox` files (gitignored).
- The `TokenRedactionFilter` provides defense-in-depth but is **not a substitute** for proper secret management.

### 8.2 Token Redaction in Logs

- `TokenRedactionFilter` is installed by default in all logging configurations.
- It redacts tokens in both the log message string and structured `extra` fields.
- Sensitive extra key names: `token`, `access_token`, `refresh_token`, `api_key`, `api_secret`, `password`, `pin`, `totp`, `totp_secret`, `authorization`, `bearer_token`, and any key ending in `_token`.
- Pattern-based redaction catches `Authorization: Bearer <token>`, URL `?token=<value>`, key=value assignments, and broker-specific token env vars.

### 8.3 No Broker Tokens at Public Boundaries

The architecture test `test_no_security_id_leak.py` scans public surfaces (interface, CLI, MCP, services) for broker-specific token references:
- `security_id`
- `instrument_token`
- `securityId` / `Security ID`

Lines with `ponytail:`, `# internal`, `# deprecated`, or `# no broker token` comments are exempted.

### 8.4 SSL Hardening

- Production uses hardened TLS sessions via `infrastructure.security.ssl_hardening`.
- `application.services.production_readiness` inspects TLS configuration.
- Certificate verification is mandatory in production.

### 8.5 API Key Auth Defaults

- Broker authentication is handled by bootstrap functions, not hardcoded tokens.
- `BrokerNotReadyError` is raised when credentials are missing or expired.
- The `live_credentials` fixture auto-skips tests when `.env.local` is absent or tokens are expired (JWT expiry check built in).

### 8.6 Production Config Validation

- `TRADEXV2_DEBUG` controls debug information exposure in error responses (must be `0` in production).
- `APP_ENV=production` activates JSON logging and other production safeguards.
- Configuration errors raise `ConfigError` (HTTP 500) and must be caught at startup.

---

## 9. Performance Standards

### 9.1 No Pandas in Domain Layer

**Enforced by architecture test `test_domain_no_pandas_import.py`.**

- Domain modules (`src/domain/`) must have **zero top-level pandas imports**.
- Pandas may be lazy-imported inside functions in export adapters only (e.g., `to_dataframe`, `from_dataframe`).
- The test verifies that core domain modules can import without pandas loaded in `sys.modules`.

**Rationale:** Pandas is a ~30 MB dependency that slows cold start. Domain logic must be pure and fast.

### 9.2 Lock Discipline

**Enforced by architecture test `test_concurrency_boundary.py`.**

- Exactly **one** module (`src/runtime/event_loop.py`) may call `asyncio.new_event_loop()`.
- All other code must use the centralized helpers: `get_runtime_loop()`, `new_dedicated_loop()`, `run_coro_sync()`.
- **No I/O under lock.** Network calls, file I/O, and database operations must never occur while holding a threading lock or asyncio lock.

### 9.3 Bounded Caches

- All caches must have a `max_entries` parameter or equivalent bound.
- Unbounded caches will be flagged in code review.
- Prefer `functools.lru_cache(maxsize=N)` for simple caches.
- For custom caches, document the eviction policy.

### 9.4 Thread Safety

- Shared mutable state accessed from multiple threads must be protected.
- Prefer `threading.Lock` for simple cases, `asyncio.Lock` for async contexts.
- Document thread-safety guarantees in class docstrings.
- The `EventBus` and `DeadLetterQueue` handle concurrent event publication via the infrastructure layer.

### 9.5 Line Length

- **100 characters** maximum (ruff `line-length = 100`).
- Long strings and URLs may exceed the limit (handled by the formatter).

---

## 10. Code Review Checklist

Every merge request must pass all items below. The reviewer (human or AI) checks each item.

### Correctness
- [ ] **All tests pass** (`pytest tests/ -x -q`)
- [ ] **No architecture test regressions** (`pytest tests/architecture/ -q`)
- [ ] **No import-linter violations** (`lint-imports --config pyproject.toml`)
- [ ] **mypy passes** (`mypy src/ --strict` with project config)
- [ ] **ruff passes** (`ruff check src/ tests/`)
- [ ] **Coverage does not drop** (`pytest --cov` ≥ 80%)

### Architecture
- [ ] **Domain layer is pure** — no imports from outer layers
- [ ] **No broker name branching** in OMS / cert suite / rate limiter
- [ ] **No top-level pandas imports** in domain layer
- [ ] **No broker tokens** at public boundaries (interface, CLI, MCP, services)
- [ ] **Gateway surface frozen** — new methods require explicit update of freeze list + PR review
- [ ] **Concurrency boundary respected** — only `runtime/event_loop.py` creates event loops
- [ ] **New architectural invariants have tests** in `tests/architecture/`

### Code Quality
- [ ] **File size** — under 400 LOC (or justified in PR description)
- [ ] **No bare `except:`** — all exception handlers catch specific types
- [ ] **No silent error swallowing** — every except block re-raises, logs, or handles explicitly
- [ ] **Logging uses `getLogger(__name__)`** — not hardcoded names
- [ ] **No secrets in source** — all credentials via env vars
- [ ] **`from __future__ import annotations`** is the first import in every file
- [ ] **Imports ordered** per ruff isort (stdlib → third-party → project)
- [ ] **Exception classes end with `Error`**

### Testing
- [ ] **Protocol-based fakes** — no new MagicMock usage
- [ ] **Test functions named** `test_<behavior>`
- [ ] **Appropriate pytest markers** applied
- [ ] **New Protocol interfaces** have corresponding fakes in `tests/fakes/`
- [ ] **Fixture patterns follow** `conftest.py` conventions (builder helpers, auto-skip for credentials)

### Documentation
- [ ] **Module docstrings** on all `__init__.py` files (≥20 chars)
- [ ] **Public functions/classes** have docstrings
- [ ] **Architecture tests** have invariant-explaining docstrings
- [ ] **ADR created** for any architectural decision
- [ ] **This handbook updated** if a new convention is introduced

### Security
- [ ] **Token redaction** active (not disabled in production config)
- [ ] **No hardcoded tokens** or API keys
- [ ] **SSL hardening** maintained
- [ ] **Debug mode gated** — `TRADEXV2_DEBUG` not set in production

---

## Appendix: Quick Reference Commands

```bash
# Linting
ruff check src/ tests/
ruff format --check src/ tests/

# Type checking
mypy src/ --config-file pyproject.toml

# Import boundaries
PYTHONPATH=src lint-imports --config pyproject.toml

# Full test suite
pytest tests/ -x -q

# Architecture tests only
pytest tests/architecture/ -q

# Coverage
pytest --cov --cov-report=term-missing

# Mutation testing
mutmut run

# Run a single architecture test
pytest tests/architecture/test_domain_isolation.py -v
```

---

*Last updated: 2026-07-12. This document is living — update it when conventions change.*
