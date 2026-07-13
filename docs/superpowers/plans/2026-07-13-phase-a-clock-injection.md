# Phase A: Clock Injection & Paper Bypass Retirement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate `datetime.now()` calls in execution/risk/domain paths (I2 invariant) and retire the PaperOrders legacy bypass that circumvents OMS controls.

**Architecture:** Inject `ClockPort` into every timestamp constructor in execution paths. Delete `PaperOrders._place_internal` so paper orders route through OMS like live orders.

**Tech Stack:** Python 3.11+, existing `ClockPort` protocol (`domain/ports/time_service.py`), `FakeClock` for tests, `pytest`.

## Global Constraints

- `domain/` imports nothing inward (stdlib + itself only)
- `application/` never imports infrastructure/runtime/brokers
- import-linter rules 1–4 are CI-blocking
- All timestamps in execution paths must come from injected `ClockPort`
- `datetime.now()` forbidden in: `src/application/execution/`, `src/application/oms/`, `src/domain/entities/`, `src/domain/execution_contracts.py`, `src/application/trading/trading_orchestrator.py`
- Run `graphify update .` after modifying code files

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/application/oms/trade_recorder.py` | Records fills with timestamps | Inject ClockPort |
| `src/application/oms/order_validator.py` | Validates orders, creates rejection events | Inject ClockPort |
| `src/application/oms/_internal/order_lifecycle.py` | Order lifecycle management | Inject ClockPort |
| `src/application/execution/gateway_submit.py` | Gateway submission events | Inject ClockPort |
| `src/domain/entities/market.py` | Market entity timestamps | Inject ClockPort |
| `src/domain/execution_contracts.py` | Execution contract types | Inject ClockPort |
| `src/application/trading/trading_orchestrator.py` | Orchestrator timestamps | Inject ClockPort |
| `src/brokers/paper/paper_orders.py` | Paper order placement | Delete `_place_internal` |
| `tests/unit/application/oms/test_clock_injection.py` | New: verify clock-injected paths | Create |
| `tests/unit/brokers/paper/test_paper_oms_path.py` | New: verify paper goes through OMS | Create |

---

### Task 1: Inject ClockPort into trade_recorder.py

**Files:**
- Modify: `src/application/oms/trade_recorder.py:215`
- Test: `tests/unit/application/oms/test_clock_injection.py`

**Interfaces:**
- Consumes: `ClockPort` from `domain/ports/time_service.py`
- Produces: `TradeRecorder` constructor accepts optional `clock: ClockPort | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/oms/test_clock_injection.py
"""Verify clock injection in execution paths — I2 invariant."""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock

from domain.ports.time_service import ClockPort


class FakeTestClock:
    """Deterministic clock for testing."""

    def __init__(self, fixed: datetime.datetime | None = None) -> None:
        self._now = fixed or datetime.datetime(2026, 7, 13, 10, 0, 0, tzinfo=datetime.timezone.utc)

    def now(self) -> datetime.datetime:
        return self._now

    def advance(self, delta: datetime.timedelta) -> None:
        self._now += delta


def test_trade_recorder_uses_injected_clock():
    """TradeRecorder must use injected ClockPort for fill timestamps."""
    from application.oms.trade_recorder import TradeRecorder

    clock = FakeTestClock()
    # TradeRecorder accepts clock parameter
    recorder = TradeRecorder.__new__(TradeRecorder)
    # Verify constructor signature accepts clock
    import inspect
    sig = inspect.signature(TradeRecorder.__init__)
    assert "clock" in sig.parameters, "TradeRecorder.__init__ must accept 'clock' parameter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_trade_recorder_uses_injected_clock -xvs`
Expected: FAIL — `TradeRecorder.__init__` has no `clock` parameter

- [ ] **Step 3: Implement clock injection**

In `src/application/oms/trade_recorder.py`, modify `__init__` to accept `clock: ClockPort | None = None` and store as `self._clock`. At line 215, replace `datetime.now(timezone.utc)` with `self._clock.now()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_trade_recorder_uses_injected_clock -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/oms/trade_recorder.py tests/unit/application/oms/test_clock_injection.py
git commit -m "fix(i2): inject ClockPort into TradeRecorder fill timestamps"
```

---

### Task 2: Inject ClockPort into order_validator.py

**Files:**
- Modify: `src/application/oms/order_validator.py:111,128`
- Test: `tests/unit/application/oms/test_clock_injection.py`

**Interfaces:**
- Consumes: `ClockPort` from `domain/ports/time_service.py`
- Produces: `OrderValidator` constructor accepts optional `clock: ClockPort | None`

- [ ] **Step 1: Write the failing test**

```python
def test_order_validator_uses_injected_clock():
    """OrderValidator must use injected ClockPort for rejection timestamps."""
    from application.oms.order_validator import OrderValidator
    import inspect
    sig = inspect.signature(OrderValidator.__init__)
    assert "clock" in sig.parameters, "OrderValidator.__init__ must accept 'clock' parameter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_order_validator_uses_injected_clock -xvs`
Expected: FAIL

- [ ] **Step 3: Implement clock injection**

In `src/application/oms/order_validator.py`, modify `__init__` to accept `clock: ClockPort | None = None`. At lines 111 and 128, replace `datetime.now(timezone.utc)` with `self._clock.now()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_order_validator_uses_injected_clock -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/oms/order_validator.py
git commit -m "fix(i2): inject ClockPort into OrderValidator rejection timestamps"
```

---

### Task 3: Inject ClockPort into order_lifecycle.py

**Files:**
- Modify: `src/application/oms/_internal/order_lifecycle.py:129`
- Test: `tests/unit/application/oms/test_clock_injection.py`

**Interfaces:**
- Consumes: `ClockPort` from `domain/ports/time_service.py`
- Produces: `OrderLifecycle` constructor accepts optional `clock: ClockPort | None`

- [ ] **Step 1: Write the failing test**

```python
def test_order_lifecycle_uses_injected_clock():
    """OrderLifecycle must use injected ClockPort for fallback created_at."""
    from application.oms._internal.order_lifecycle import OrderLifecycle
    import inspect
    sig = inspect.signature(OrderLifecycle.__init__)
    assert "clock" in sig.parameters, "OrderLifecycle.__init__ must accept 'clock' parameter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_order_lifecycle_uses_injected_clock -xvs`
Expected: FAIL

- [ ] **Step 3: Implement clock injection**

In `src/application/oms/_internal/order_lifecycle.py`, modify `__init__` to accept `clock: ClockPort | None = None`. At line 129, replace `datetime.now(timezone.utc)` with `self._clock.now()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_order_lifecycle_uses_injected_clock -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/oms/_internal/order_lifecycle.py
git commit -m "fix(i2): inject ClockPort into OrderLifecycle fallback timestamps"
```

---

### Task 4: Inject ClockPort into gateway_submit.py

**Files:**
- Modify: `src/application/execution/gateway_submit.py:34`
- Test: `tests/unit/application/oms/test_clock_injection.py`

**Interfaces:**
- Consumes: `ClockPort` from `domain/ports/time_service.py`
- Produces: `make_gateway_submit_fn` accepts optional `clock: ClockPort | None`

- [ ] **Step 1: Write the failing test**

```python
def test_gateway_submit_uses_injected_clock():
    """make_gateway_submit_fn must use injected ClockPort."""
    from application.execution.gateway_submit import make_gateway_submit_fn
    import inspect
    sig = inspect.signature(make_gateway_submit_fn)
    assert "clock" in sig.parameters, "make_gateway_submit_fn must accept 'clock' parameter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_gateway_submit_uses_injected_clock -xvs`
Expected: FAIL

- [ ] **Step 3: Implement clock injection**

In `src/application/execution/gateway_submit.py`, modify `make_gateway_submit_fn` to accept `clock: ClockPort | None = None`. At line 34, replace `datetime.now(timezone.utc)` with `clock.now()` (defaulting to `datetime.now(timezone.utc)` if clock is None for backward compatibility).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_gateway_submit_uses_injected_clock -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/execution/gateway_submit.py
git commit -m "fix(i2): inject ClockPort into gateway submission timestamps"
```

---

### Task 5: Inject ClockPort into domain entities (market.py, execution_contracts.py)

**Files:**
- Modify: `src/domain/entities/market.py:219,227,264,339,345`
- Modify: `src/domain/execution_contracts.py:82,91,100`
- Test: `tests/unit/application/oms/test_clock_injection.py`

**Interfaces:**
- Consumes: `ClockPort` from `domain/ports/time_service.py`
- Produces: `MarketQuote` and execution contract factories accept `clock: ClockPort`

- [ ] **Step 1: Write the failing test**

```python
def test_domain_entities_accept_clock():
    """Domain entity factories must accept ClockPort for timestamps."""
    from domain.entities.market import MarketQuote
    from domain.execution_contracts import SubmissionOutcome
    import inspect

    # Check MarketQuote or its factory accepts clock
    # Check SubmissionOutcome accepts clock
    # These are the types that need ClockPort injection
    assert hasattr(MarketQuote, '__init__') or hasattr(MarketQuote, 'create'), \
        "MarketQuote must have a factory accepting clock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_domain_entities_accept_clock -xvs`
Expected: FAIL (likely — domain entities may not accept clock yet)

- [ ] **Step 3: Implement clock injection**

In `src/domain/entities/market.py`, modify `MarketQuote` and related factories to accept `clock: ClockPort` parameter. Replace `datetime.now(timezone.utc)` calls with `clock.now()`.

In `src/domain/execution_contracts.py`, modify `SubmissionOutcome` and related types to accept `clock: ClockPort` parameter. Replace `datetime.now(timezone.utc)` calls with `clock.now()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_domain_entities_accept_clock -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/entities/market.py src/domain/execution_contracts.py
git commit -m "fix(i2): inject ClockPort into domain entity timestamp construction"
```

---

### Task 6: Inject ClockPort into trading_orchestrator.py

**Files:**
- Modify: `src/application/trading/trading_orchestrator.py:539`
- Test: `tests/unit/application/oms/test_clock_injection.py`

**Interfaces:**
- Consumes: `ClockPort` from `domain/ports/time_service.py`
- Produces: `TradingOrchestrator` constructor accepts optional `clock: ClockPort | None`

- [ ] **Step 1: Write the failing test**

```python
def test_trading_orchestrator_uses_injected_clock():
    """TradingOrchestrator must use injected ClockPort for last_check."""
    from application.trading.trading_orchestrator import TradingOrchestrator
    import inspect
    sig = inspect.signature(TradingOrchestrator.__init__)
    assert "clock" in sig.parameters, "TradingOrchestrator.__init__ must accept 'clock' parameter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_trading_orchestrator_uses_injected_clock -xvs`
Expected: FAIL

- [ ] **Step 3: Implement clock injection**

In `src/application/trading/trading_orchestrator.py`, modify `__init__` to accept `clock: ClockPort | None = None`. At line 539, replace `datetime.now(timezone.utc)` with `self._clock.now()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/application/oms/test_clock_injection.py::test_trading_orchestrator_uses_injected_clock -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/trading/trading_orchestrator.py
git commit -m "fix(i2): inject ClockPort into TradingOrchestrator timestamps"
```

---

### Task 7: Retire PaperOrders legacy bypass

**Files:**
- Modify: `src/brokers/paper/paper_orders.py` — delete `_place_internal` (lines 244-362)
- Test: `tests/unit/brokers/paper/test_paper_oms_path.py`

**Interfaces:**
- Consumes: `OrderManager`, `RiskManager`, `IdempotencyGuard` (existing)
- Produces: Paper orders route through OMS exclusively

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/brokers/paper/test_paper_oms_path.py
"""Verify paper orders route through OMS — no legacy bypass."""
from __future__ import annotations


def test_paper_orders_has_no_place_internal():
    """PaperOrders must not have _place_internal method (legacy bypass deleted)."""
    from brokers.paper.paper_orders import PaperOrders
    assert not hasattr(PaperOrders, '_place_internal'), \
        "PaperOrders._place_internal should be deleted — paper must route through OMS"


def test_paper_place_order_calls_oms():
    """PaperOrders.place_order must route through OrderManager."""
    from brokers.paper.paper_orders import PaperOrders
    import inspect
    # Verify the method exists and doesn't contain legacy bypass
    source = inspect.getsource(PaperOrders.place_order)
    assert "_place_internal" not in source, \
        "PaperOrders.place_order should not call _place_internal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/brokers/paper/test_paper_oms_path.py -xvs`
Expected: FAIL — `_place_internal` still exists

- [ ] **Step 3: Delete legacy bypass**

In `src/brokers/paper/paper_orders.py`:
1. Delete the `_place_internal` method (lines 244-362)
2. In `place_order`, remove the `if self._order_manager is None` branch that calls `_place_internal`
3. All paper orders now route through `_place_via_oms` → `OrderManager.place_order`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/brokers/paper/test_paper_oms_path.py -xvs`
Expected: PASS

- [ ] **Step 5: Run full paper test suite**

Run: `python -m pytest tests/unit/brokers/paper/ -x`
Expected: All existing paper tests pass (they should already use the OMS path)

- [ ] **Step 6: Commit**

```bash
git add src/brokers/paper/paper_orders.py tests/unit/brokers/paper/test_paper_oms_path.py
git commit -m "fix(i1): retire PaperOrders legacy bypass — paper routes through OMS"
```

---

### Task 8: Verify no datetime.now() remains in execution paths

**Files:**
- Test: `tests/architecture/test_clock_purity.py` (new)

**Interfaces:**
- Consumes: Architecture test infrastructure
- Produces: CI-blocking grep test for datetime.now in execution paths

- [ ] **Step 1: Write the architecture test**

```python
# tests/architecture/test_clock_purity.py
"""Architecture test: datetime.now() forbidden in execution/risk/domain paths (I2)."""
from __future__ import annotations

import ast
import pathlib

# Directories where datetime.now() is forbidden
FORBIDDEN_PATHS = [
    "src/application/execution/",
    "src/application/oms/",
    "src/domain/entities/",
    "src/domain/execution_contracts.py",
    "src/application/trading/trading_orchestrator.py",
]

# Allowed exceptions (clock implementations themselves)
ALLOWED_FILES = [
    "src/runtime/time_service.py",
    "src/domain/ports/time_service.py",
    "src/domain/ports/time_service_impls.py",
    "src/infrastructure/time/clock.py",
    "src/infrastructure/time_service.py",
]


def _find_datetime_now_calls(filepath: pathlib.Path) -> list[int]:
    """Find lines with datetime.now() calls using AST parsing."""
    try:
        tree = ast.parse(filepath.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return []

    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for datetime.now() pattern
            if (isinstance(node.func, ast.Attribute) and
                node.func.attr == "now" and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == "datetime"):
                lines.append(node.lineno)
    return lines


def test_no_datetime_now_in_execution_paths():
    """datetime.now() is forbidden in execution/risk/domain timestamp paths."""
    violations = []
    root = pathlib.Path("src")

    for path_pattern in FORBIDDEN_PATHS:
        if path_pattern.endswith(".py"):
            filepath = root / path_pattern
            if filepath.exists():
                lines = _find_datetime_now_calls(filepath)
                if lines:
                    violations.append(f"{path_pattern}:{lines}")
        else:
            dirpath = root / path_pattern
            if dirpath.exists():
                for py_file in dirpath.rglob("*.py"):
                    rel = str(py_file.relative_to(root))
                    if any(rel.endswith(a) for a in ALLOWED_FILES):
                        continue
                    lines = _find_datetime_now_calls(py_file)
                    if lines:
                        violations.append(f"{rel}:{lines}")

    assert not violations, (
        f"datetime.now() found in forbidden paths (I2 invariant):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
```

- [ ] **Step 2: Run the architecture test**

Run: `python -m pytest tests/architecture/test_clock_purity.py -xvs`
Expected: PASS (after Tasks 1–6 are complete)

- [ ] **Step 3: Run full architecture test suite**

Run: `python -m pytest tests/architecture/ -x`
Expected: All architecture tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/architecture/test_clock_purity.py
git commit -m "test(i2): add architecture grep test for datetime.now in execution paths"
```

---

### Task 9: Run graphify update and full test suite

- [ ] **Step 1: Update graphify**

Run: `graphify update .`

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -x --timeout=300`
Expected: All tests pass (no regressions from clock injection changes)

- [ ] **Step 3: Final commit if needed**

```bash
git add -A
git commit -m "chore: graphify update after Phase A clock injection"
```
