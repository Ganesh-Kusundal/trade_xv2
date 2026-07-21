# Architectural Audit Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 40+ pending findings from the architectural audit (Phases 3-5) by executing parallel waves of refactoring tasks, establishing canonical vocabulary, eliminating boundary violations, and adding guardrails.

**Architecture:** Execute in 3 waves based on dependency graph. Wave 1 (8 parallel tasks) fixes foundational issues with no cross-dependencies. Wave 2 (2 tasks) consolidates after Wave 1 stabilizes. Wave 3 (4 tasks) adds guardrails and moves orchestration logic. Each wave produces independently testable deliverables.

**Tech Stack:** Python 3.11+, mypy strict, ruff, import-linter, pytest

## Global Constraints

- Python 3.11+ target
- mypy strict mode for cleaned modules
- ruff linting (line-length=100)
- import-linter contracts CI-blocking for rules 1-4
- coverage ≥ 80 overall, ≥ 85 brokers, ≥ 90 OMS
- No changes to domain model without ADR
- Zero-parity rule: backtest/replay/paper share identical logic
- Domain imports only stdlib + itself

---

## Wave 1: Foundational Fixes (Parallel — No Dependencies)

### Task 1: REF-1 — Unify Exception Hierarchy

**Files:**
- Modify: `src/domain/exceptions.py` (add broker exceptions)
- Modify: `src/domain/errors.py` (become thin re-export for backward compat)
- Delete: `src/infrastructure/resilience/errors.py` (re-exports)
- Modify: `src/domain/__init__.py` (update imports)

**Interfaces:**
- Consumes: Current `domain.exceptions` (TradeXV2Error subtree) + `domain.errors` (BrokerError subtree)
- Produces: Unified `domain.exceptions` with both hierarchies; `domain.errors` becomes deprecated re-export

- [ ] **Step 1: Write failing test for unified hierarchy**

```python
# tests/architecture/test_exception_hierarchy_unified.py
import pytest
from domain.exceptions import (
    TradeXV2Error,
    BrokerError,
    RetryableError,
    NonRetryableError,
    RateLimitError,
    AuthenticationError,
    InstrumentError,
    OrderError,
    ConfigError,
    ValidationError,
    DataError,
)

def test_broker_error_inherits_trade_x_v2_error():
    assert issubclass(BrokerError, TradeXV2Error)

def test_retryable_error_inherits_broker_error():
    assert issubclass(RetryableError, BrokerError)

def test_all_broker_errors_inherit_trade_x_v2_error():
    broker_errors = [
        RetryableError, NonRetryableError, RateLimitError,
        AuthenticationError, InstrumentError, OrderError,
    ]
    for err in broker_errors:
        assert issubclass(err, TradeXV2Error), f"{err.__name__} must inherit TradeXV2Error"

def test_config_error_inherits_trade_x_v2_error():
    assert issubclass(ConfigError, TradeXV2Error)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_exception_hierarchy_unified.py -v`
Expected: FAIL with ImportError (broker exceptions not in domain.exceptions)

- [ ] **Step 3: Merge broker exceptions into domain/exceptions.py**

```python
# src/domain/exceptions.py — add after existing exceptions

class BrokerError(TradeXV2Error):
    """Base exception for all broker communication errors."""

class RetryableError(BrokerError):
    """An error that can be retried (transient failure)."""

class NonRetryableError(BrokerError):
    """An error that should NOT be retried (permanent failure)."""

class RateLimitError(BrokerError):
    """Rate limit exceeded (429 / throttled)."""

class AuthenticationError(BrokerError):
    """Authentication or authorization failure."""

class InstrumentError(BrokerError):
    """Instrument resolution or validation failure."""

class InstrumentNotFoundError(InstrumentError):
    """Requested instrument not found."""

class OrderError(BrokerError):
    """Order placement, modification, or cancellation error."""

class RejectedOrderError(OrderError):
    """Order rejected by broker or exchange."""

# ... (copy all broker exceptions from domain/errors.py)
```

- [ ] **Step 4: Update domain/errors.py to re-export from exceptions**

```python
# src/domain/errors.py — thin re-export for backward compatibility
from domain.exceptions import (
    TradeXV2Error,
    BrokerError,
    RetryableError,
    NonRetryableError,
    # ... all exceptions
)

# Deprecation warning
import warnings
warnings.warn(
    "domain.errors is deprecated. Import from domain.exceptions instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/architecture/test_exception_hierarchy_unified.py -v`
Expected: PASS

- [ ] **Step 6: Run full architecture test suite**

Run: `pytest tests/architecture/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/domain/exceptions.py src/domain/errors.py tests/architecture/test_exception_hierarchy_unified.py
git commit -m "refactor(ref-1): unify exception hierarchy in domain.exceptions"
```

---

### Task 2: REF-3 — Eliminate Hardcoded NSE Defaults

**Files:**
- Modify: `src/analytics/core/providers.py` (5 occurrences)
- Modify: `src/analytics/paper/signal_processor.py` (8 occurrences)
- Modify: `src/analytics/paper/position_closer.py` (2 occurrences)
- Modify: `src/analytics/paper/models.py` (5 occurrences)
- Modify: `src/analytics/backtest/fast_backtest.py` (3 occurrences)
- Modify: `src/analytics/scanner/models.py` (2 occurrences)
- Modify: `src/application/services/instrument_registry.py` (4 occurrences)
- Modify: `src/config/endpoints.py` (1 occurrence)
- Modify: `src/config/indices.py` (2 occurrences)

**Interfaces:**
- Consumes: `domain.market_enums.Exchange` enum
- Produces: All function signatures use `Exchange.NSE` instead of `"NSE"` string

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_no_hardcoded_nse.py
import ast
import pathlib

SRC_ROOT = pathlib.Path("src")

def test_no_nse_string_default_in_signatures():
    """REF-3: No function parameter should default to string 'NSE'."""
    offenders = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if "test" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.defaults + node.args.kw_defaults:
                    if arg is None:
                        continue
                    if isinstance(arg, ast.Constant) and arg.value == "NSE":
                        offenders.append(f"{py_file}:{node.lineno} {node.name}")
    assert not offenders, f"Hardcoded 'NSE' defaults found: {offenders}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_no_hardcoded_nse.py -v`
Expected: FAIL with offenders listed

- [ ] **Step 3: Replace all `"NSE"` defaults with `Exchange.NSE`**

For each file, add import and replace:
```python
# Before
def ltp(self, symbol: str, *, exchange: str = "NSE") -> float: ...

# After
from domain.market_enums import Exchange
def ltp(self, symbol: str, *, exchange: Exchange = Exchange.NSE) -> float: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/architecture/test_no_hardcoded_nse.py -v`
Expected: PASS

- [ ] **Step 5: Add ruff banned-api rule**

```toml
# pyproject.toml — add to [tool.ruff.lint.flake8-tidy-imports.banned-api]
'"NSE"' = {msg = "Use Exchange.NSE enum instead of hardcoded 'NSE' string"}
```

- [ ] **Step 6: Commit**

```bash
git add src/analytics/ src/application/ src/config/ pyproject.toml tests/architecture/test_no_hardcoded_nse.py
git commit -m "refactor(ref-3): replace hardcoded NSE defaults with Exchange enum"
```

---

### Task 3: REF-6 — Rename Conflicting Session/TradingSession Types

**Files:**
- Modify: `src/domain/market/exchange.py` (rename TradingSession → MarketHours)
- Modify: `src/domain/session_status.py` (rename SessionStatus → ConnectivityStatus)
- Update: All consumers of old names

**Interfaces:**
- Consumes: Current `domain.market.exchange.TradingSession` and `domain.session_status.SessionStatus`
- Produces: `domain.market.exchange.MarketHours` and `domain.session_status.ConnectivityStatus`

- [ ] **Step 1: Write failing tests**

```python
# tests/architecture/test_session_type_renames.py
def test_market_hours_exists():
    from domain.market.exchange import MarketHours
    assert MarketHours is not None

def test_connectivity_status_exists():
    from domain.session_status import ConnectivityStatus
    assert Connectivity_status is not None

def test_old_trading_session_removed():
    import pytest
    with pytest.raises(ImportError):
        from domain.market.exchange import TradingSession

def test_old_session_status_removed():
    import pytest
    with pytest.raises(ImportError):
        from domain.session_status import SessionStatus
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/architecture/test_session_type_renames.py -v`
Expected: FAIL

- [ ] **Step 3: Rename types in source files**

```python
# src/domain/market/exchange.py
class MarketHours(NamedTuple):  # renamed from TradingSession
    name: str
    open_time: time
    close_time: time

# src/domain/session_status.py
class ConnectivityStatus:  # renamed from SessionStatus
    # ... existing fields
```

- [ ] **Step 4: Update all consumers**

Search and replace:
- `TradingSession` → `MarketHours` in `domain/market/exchange.py` consumers
- `SessionStatus` → `ConnectivityStatus` in `domain/session_status.py` consumers

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/architecture/test_session_type_renames.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/domain/market/exchange.py src/domain/session_status.py tests/architecture/test_session_type_renames.py
git commit -m "refactor(ref-6): rename TradingSession→MarketHours, SessionStatus→ConnectivityStatus"
```

---

### Task 4: REF-7 — Unify TimeService

**Files:**
- Modify: `src/infrastructure/time_service.py` (add SystemClock/FakeClock)
- Delete: `src/runtime/time_service.py` (or make thin re-export)
- Update: All consumers

**Interfaces:**
- Consumes: Current dual TimeService implementations
- Produces: Single `infrastructure.time_service.TimeService` with SystemClock/FakeClock

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_single_timeservice.py
def test_single_timeservice_implementation():
    import inspect
    from infrastructure import time_service
    classes = [name for name, obj in inspect.getmembers(time_service) 
               if inspect.isclass(obj) and name.endswith("Clock")]
    assert len(classes) <= 2, f"Expected at most 2 clock classes, found: {classes}"

def test_no_duplicate_fake_clock():
    from infrastructure.time_service import FakeClock as InfraFakeClock
    try:
        from runtime.time_service import FakeClock as RuntimeFakeClock
        assert InfraFakeClock is RuntimeFakeClock, "FakeClock should be the same class"
    except ImportError:
        pass  # runtime.time_service deleted — good
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_single_timeservice.py -v`
Expected: FAIL

- [ ] **Step 3: Merge clock implementations**

```python
# src/infrastructure/time_service.py — add if not present
class SystemClock:
    """Real system clock."""
    def now(self) -> datetime:
        return datetime.now()

class FakeClock:
    """Fake clock for testing."""
    def __init__(self, initial: datetime):
        self._time = initial
    def now(self) -> datetime:
        return self._time
    def advance(self, delta: timedelta):
        self._time += delta
```

- [ ] **Step 4: Make runtime/time_service.py a thin re-export**

```python
# src/runtime/time_service.py
from infrastructure.time_service import SystemClock, FakeClock, TimeService
__all__ = ["SystemClock", "FakeClock", "TimeService"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/architecture/test_single_timeservice.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/time_service.py src/runtime/time_service.py tests/architecture/test_single_timeservice.py
git commit -m "refactor(ref-7): unify TimeService in infrastructure, runtime becomes re-export"
```

---

### Task 5: REF-12 — Remove Broker __getattr__ Reach-Throughs

**Files:**
- Modify: `src/brokers/providers/dhan/domain.py` (remove __getattr__)
- Update: All consumers to use explicit imports

**Interfaces:**
- Consumes: Current `brokers.providers.dhan.domain.__getattr__` pattern
- Produces: Explicit imports from `domain` submodules

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_no_broker_getattr.py
def test_dhan_domain_no_getattr():
    import brokers.providers.dhan.domain as dhan_domain
    # Check module doesn't have custom __getattr__
    assert "__getattr__" not in dhan_domain.__dict__, "dhan/domain.py should not use __getattr__"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_no_broker_getattr.py -v`
Expected: FAIL

- [ ] **Step 3: Replace __getattr__ with explicit imports**

```python
# src/brokers/providers/dhan/domain.py — remove __getattr__ and _CANONICAL/_ALIASES

# Add explicit imports for types that were previously re-exported
from domain.entities import Order, Position, Trade
from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
```

- [ ] **Step 4: Update all consumers**

Search for `from brokers.providers.dhan.domain import` and update to use `domain.*` directly.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/architecture/test_no_broker_getattr.py -v`
Expected: PASS

- [ ] **Step 6: Add ruff rule to prevent future __getattr__**

```toml
# pyproject.toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"__getattr__" = {msg = "Do not use __getattr__ for re-exports. Use explicit imports."}
```

- [ ] **Step 7: Commit**

```bash
git add src/brokers/providers/dhan/domain.py pyproject.toml tests/architecture/test_no_broker_getattr.py
git commit -m "refactor(ref-12): remove __getattr__ reach-throughs in dhan/domain.py"
```

---

### Task 6: REF-4 — Consolidate OrderIntent Types

**Files:**
- Modify: `src/domain/orders/intent.py` (rename OrderIntent → OrderCommand)
- Keep: `src/domain/execution_contracts.py` (OrderIntent unchanged)
- Update: All consumers of pre-risk OrderIntent

**Interfaces:**
- Consumes: Dual OrderIntent classes
- Produces: `domain.orders.intent.OrderCommand` (pre-risk) + `domain.execution_contracts.OrderIntent` (durable)

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_order_intent_consolidated.py
def test_order_command_exists():
    from domain.orders.intent import OrderCommand
    assert OrderCommand is not None

def test_execution_contracts_order_intent_unchanged():
    from domain.execution_contracts import OrderIntent
    assert OrderIntent is not None

def test_old_order_intent_in_orders_removed():
    import pytest
    with pytest.raises(ImportError):
        from domain.orders.intent import OrderIntent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/architecture/test_order_intent_consolidated.py -v`
Expected: FAIL

- [ ] **Step 3: Rename in domain/orders/intent.py**

```python
# src/domain/orders/intent.py
@dataclass
class OrderCommand:  # renamed from OrderIntent
    """Pre-risk, ephemeral order command."""
    # ... existing fields
```

- [ ] **Step 4: Update all consumers**

Search for `from domain.orders.intent import OrderIntent` and update to `OrderCommand`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/architecture/test_order_intent_consolidated.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/domain/orders/intent.py tests/architecture/test_order_intent_consolidated.py
git commit -m "refactor(ref-4): rename pre-risk OrderIntent to OrderCommand"
```

---

### Task 7: REF-8 — Consolidate Config Classes

**Files:**
- Modify: `src/config/schema.py` (add api section)
- Delete: `src/interface/api/config.py` (merge into AppConfig)
- Update: All consumers

**Interfaces:**
- Consumes: Dual config classes (AppConfig + APIConfig)
- Produces: Single `config.schema.AppConfig` with nested `api` section

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_single_config.py
def test_app_config_has_api_section():
    from config.schema import AppConfig
    config = AppConfig()
    assert hasattr(config, 'api'), "AppConfig should have 'api' section"

def test_no_api_config_class():
    import pytest
    with pytest.raises((ImportError, AttributeError)):
        from interface.api.config import APIConfig
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/architecture/test_single_config.py -v`
Expected: FAIL

- [ ] **Step 3: Add APIConfig fields to AppConfig**

```python
# src/config/schema.py
class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = []
    rate_limit: int = 100

class AppConfig(BaseModel):
    # ... existing fields
    api: APIConfig = APIConfig()
```

- [ ] **Step 4: Delete interface/api/config.py**

```bash
rm src/interface/api/config.py
```

- [ ] **Step 5: Update all consumers**

Replace `from interface.api.config import APIConfig` with `from config.schema import AppConfig` and use `config.api.*`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/architecture/test_single_config.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/config/schema.py src/interface/api/config.py tests/architecture/test_single_config.py
git commit -m "refactor(ref-8): consolidate APIConfig into AppConfig.api section"
```

---

### Task 8: REF-9 — Establish Canonical Import Paths

**Files:**
- Modify: `src/domain/__init__.py` (reduce to minimal re-exports)
- Modify: `src/domain/types.py` (eventually delete or make minimal)
- Update: All 217+ facade imports across codebase

**Interfaces:**
- Consumes: Current facade imports (`from domain import Side`)
- Produces: Canonical imports (`from domain.enums import Side`)

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_canonical_imports.py
import ast
import pathlib

SRC_ROOT = pathlib.Path("src")

def test_no_facade_imports_in_src():
    """REF-9: All domain imports must use canonical submodule paths."""
    offenders = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if "test" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "domain":
                # Allow specific exceptions like domain.entities, domain.enums
                if not any(alias.name.startswith(("entities", "enums", "market_enums", "ports", "value_objects")) 
                          for alias in node.names):
                    offenders.append(f"{py_file}:{node.lineno}")
    assert not offenders, f"Facade imports found: {offenders[:10]}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_canonical_imports.py -v`
Expected: FAIL with 217+ offenders

- [ ] **Step 3: Batch replace facade imports**

Use sed/ripgrep to replace:
- `from domain import Side` → `from domain.enums import Side`
- `from domain import Order` → `from domain.entities import Order`
- etc.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/architecture/test_canonical_imports.py -v`
Expected: PASS

- [ ] **Step 5: Add ruff rule**

```toml
# pyproject.toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"domain" = {msg = "Import from domain submodules (domain.enums, domain.entities), not from domain facade"}
```

- [ ] **Step 6: Commit**

```bash
git add src/domain/__init__.py src/domain/types.py pyproject.toml tests/architecture/test_canonical_imports.py
git commit -m "refactor(ref-9): enforce canonical domain import paths"
```

---

## Wave 2: Consolidation (After Wave 1)

### Task 9: REF-5 — Complete Simulation Consolidation

**Files:**
- Modify: `src/analytics/paper/signal_processor.py` (use shared SignalProcessor)
- Modify: `src/analytics/replay/signal_processor.py` (use shared SignalProcessor)
- Modify: `src/analytics/paper/position_closer.py` (use shared PositionCloser)
- Modify: `src/analytics/replay/position_closer.py` (use shared PositionCloser)

**Interfaces:**
- Consumes: Partially consolidated `analytics.simulation.*`
- Produces: Paper/replay become thin adapters using shared simulation layer

**Depends on:** REF-2 (PositionSide elevation — DONE), REF-4 (OrderIntent consolidation)

- [ ] **Step 1: Write parity test**

```python
# tests/architecture/test_simulation_parity.py
def test_paper_and_replay_use_shared_processor():
    from analytics.paper.signal_processor import PaperSignalProcessor
    from analytics.replay.signal_processor import SignalProcessor
    from analytics.simulation.signal_processor import SignalProcessor as SharedProcessor
    
    # Both should inherit from or use the shared processor
    assert issubclass(PaperSignalProcessor, SharedProcessor) or \
           hasattr(PaperSignalProcessor, '_shared'), "Paper must use shared processor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_simulation_parity.py -v`
Expected: FAIL

- [ ] **Step 3: Refactor paper/replay to use shared classes**

```python
# src/analytics/paper/signal_processor.py
from analytics.simulation.signal_processor import SignalProcessor

class PaperSignalProcessor(SignalProcessor):
    """Paper-specific adapter using shared SignalProcessor."""
    # Only paper-specific overrides here
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/architecture/test_simulation_parity.py -v`
Expected: PASS

- [ ] **Step 5: Run golden dataset tests**

Run: `pytest tests/architecture/regression_invariants/test_golden_dataset.py -v`
Expected: PASS (zero-parity maintained)

- [ ] **Step 6: Commit**

```bash
git add src/analytics/paper/ src/analytics/replay/ tests/architecture/test_simulation_parity.py
git commit -m "refactor(ref-5): complete simulation consolidation, paper/replay use shared layer"
```

---

### Task 10: REF-10 — Move Orchestration Logic Out of Domain

**Files:**
- Create: `src/application/services/trading_costs_service.py`
- Create: `src/application/services/simulation_orchestrator.py`
- Create: `src/application/services/reconciliation_service.py`
- Modify: `src/domain/trading_costs.py` (become pure data)
- Modify: `src/domain/simulation_fill_pipeline.py` (become pure data)
- Modify: `src/domain/portfolio_projection.py` (become pure data)
- Modify: `src/domain/reconciliation_engine.py` (become pure data)

**Interfaces:**
- Consumes: Orchestration logic currently in domain
- Produces: Application services wrapping domain data; domain becomes pure entities

**Depends on:** REF-5 (simulation consolidation)

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_domain_purity.py
def test_domain_has_no_orchestration():
    """REF-10: Domain should contain only entities, value objects, and ports."""
    import ast
    import pathlib
    
    domain_root = pathlib.Path("src/domain")
    orchestration_patterns = ["orchestrat", "pipeline", "engine", "service"]
    
    for py_file in domain_root.rglob("*.py"):
        if py_file.name in ("__init__.py",):
            continue
        content = py_file.read_text().lower()
        for pattern in orchestration_patterns:
            if pattern in content and "class" in content:
                # Check if it's an orchestration class, not just a name reference
                tree = ast.parse(py_file.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and pattern in node.name.lower():
                        assert False, f"Orchestration class {node.name} found in domain: {py_file}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_domain_purity.py -v`
Expected: FAIL

- [ ] **Step 3: Create application services**

```python
# src/application/services/trading_costs_service.py
class TradingCostsService:
    """Application service for fee calculations."""
    
    def calculate_commission(self, trade_value: Decimal, model: CommissionModel) -> Decimal:
        # Move orchestration logic here from domain/trading_costs.py
        pass
    
    def apply_slippage(self, price: Decimal, side: Side, slippage_pct: float) -> Decimal:
        # Move orchestration logic here
        pass
```

- [ ] **Step 4: Simplify domain files to pure data**

```python
# src/domain/trading_costs.py — becomes pure data
@dataclass
class CommissionModel(Enum):
    FLAT = "flat"
    INDIAN_EQUITY = "indian_equity"
    INDIAN_FNO = "indian_fno"

@dataclass
class IndianMarketFees:
    """Fee structure data only."""
    stt_pct: float = 0.1
    # ... data fields only
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/architecture/test_domain_purity.py -v`
Expected: PASS

- [ ] **Step 6: Update consumers**

Replace direct domain orchestration calls with service calls.

- [ ] **Step 7: Commit**

```bash
git add src/application/services/ src/domain/trading_costs.py src/domain/simulation_fill_pipeline.py tests/architecture/test_domain_purity.py
git commit -m "refactor(ref-10): move orchestration logic to application services"
```

---

## Wave 3: Guardrails (After Wave 2)

### Task 11: REF-14 — Add Analytics Duplication Guardrail

**Files:**
- Modify: `pyproject.toml` (add import-linter contract)
- Create: `tests/architecture/test_analytics_isolation.py`

**Interfaces:**
- Consumes: Current analytics layer structure
- Produces: Import-linter contract preventing paper/replay cross-imports

- [ ] **Step 1: Write failing test**

```python
# tests/architecture/test_analytics_isolation.py
def test_paper_does_not_import_replay():
    """REF-14: analytics.paper must not import analytics.replay."""
    import ast
    import pathlib
    
    paper_root = pathlib.Path("src/analytics/paper")
    for py_file in paper_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "replay" in node.module:
                assert False, f"Paper imports replay: {py_file}:{node.lineno}"

def test_replay_does_not_import_paper():
    """REF-14: analytics.replay must not import analytics.paper."""
    import ast
    import pathlib
    
    replay_root = pathlib.Path("src/analytics/replay")
    for py_file in replay_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "paper" in node.module:
                assert False, f"Replay imports paper: {py_file}:{node.lineno}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_analytics_isolation.py -v`
Expected: FAIL (if cross-imports exist)

- [ ] **Step 3: Add import-linter contract**

```toml
# pyproject.toml
[[tool.importlinter.contracts]]
name = "Analytics paper/replay isolation"
type = "forbidden"
source_modules = ["analytics.paper"]
forbidden_modules = ["analytics.replay"]

[[tool.importlinter.contracts]]
name = "Analytics replay/paper isolation"
type = "forbidden"
source_modules = ["analytics.replay"]
forbidden_modules = ["analytics.paper"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/architecture/test_analytics_isolation.py -v`
Expected: PASS

- [ ] **Step 5: Run import-linter**

Run: `lint-imports --config pyproject.toml`
Expected: All contracts pass

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/architecture/test_analytics_isolation.py
git commit -m "refactor(ref-14): add analytics paper/replay isolation guardrail"
```

---

### Task 12: REF-15 — Expand mypy Strict Coverage

**Files:**
- Create: `mypy-strict-allowlist.txt`
- Modify: `pyproject.toml` (enable strict for allowlisted modules)
- Modify: `.pre-commit-config.yaml` (expand mypy hook)

**Interfaces:**
- Consumes: Current mypy ERROR-mode configuration
- Produces: Gradual strict-mode rollout with allowlist

- [ ] **Step 1: Create allowlist file**

```text
# mypy-strict-allowlist.txt
# Modules that have been cleaned and pass mypy strict
domain/enums.py
domain/market_enums.py
domain/value_objects.py
domain/entities/order.py
domain/entities/position.py
domain/entities/trade.py
```

- [ ] **Step 2: Update pyproject.toml**

```toml
# pyproject.toml
[tool.mypy]
strict = false  # Global default

# Strict mode for allowlisted modules
[[tool.mypy.overrides]]
module = [
    "domain.enums",
    "domain.market_enums",
    "domain.value_objects",
    "domain.entities.order",
    "domain.entities.position",
    "domain.entities.trade",
]
strict = true
```

- [ ] **Step 3: Run mypy strict on allowlisted modules**

Run: `mypy --strict src/domain/enums.py src/domain/market_enums.py`
Expected: PASS

- [ ] **Step 4: Add pre-commit hook expansion**

```yaml
# .pre-commit-config.yaml
- id: mypy
  args: [--strict, --config-file=pyproject.toml]
  additional_dependencies: []
```

- [ ] **Step 5: Commit**

```bash
git add mypy-strict-allowlist.txt pyproject.toml .pre-commit-config.yaml
git commit -m "refactor(ref-15): expand mypy strict coverage with allowlist"
```

---

## Validation Checklist

After all waves complete:

- [ ] Run full test suite: `pytest tests/ -v --tb=short`
- [ ] Run architecture tests: `pytest tests/architecture/ -v`
- [ ] Run import-linter: `lint-imports --config pyproject.toml`
- [ ] Run mypy: `mypy src/ --config-file=pyproject.toml`
- [ ] Run ruff: `ruff check src/`
- [ ] Verify coverage: `pytest --cov=src --cov-report=term-missing`
- [ ] Run golden dataset tests: `pytest tests/architecture/regression_invariants/ -v`

---

## Parallel Execution Strategy

**Wave 1 (8 tasks in parallel):**
- Task 1: REF-1 (Exception Hierarchy)
- Task 2: REF-3 (Hardcoded NSE)
- Task 3: REF-6 (Session Renames)
- Task 4: REF-7 (TimeService)
- Task 5: REF-12 (__getattr__)
- Task 6: REF-4 (OrderIntent)
- Task 7: REF-8 (Config)
- Task 8: REF-9 (Import Paths) — can start partial, complete after others

**Wave 2 (2 tasks in parallel, after Wave 1):**
- Task 9: REF-5 (Simulation Consolidation)
- Task 10: REF-10 (Orchestration Logic)

**Wave 3 (2 tasks in parallel, after Wave 2):**
- Task 11: REF-14 (Analytics Guardrail)
- Task 12: REF-15 (mypy Strict)

**Agent Dispatch:**
- Each task gets its own subagent
- Subagents run in parallel within waves
- Review checkpoint between waves
- Final validation after Wave 3
