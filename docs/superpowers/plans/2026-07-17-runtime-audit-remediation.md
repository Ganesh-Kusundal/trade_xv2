# Runtime Audit Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all runtime-audit-confirmed bugs and API contract violations across 4 independent task tracks that can execute in parallel.

**Architecture:** Surgical patching — fix each finding at its exact call site. No new abstractions invented. No speculative refactoring. Every task ends with a passing `pytest` gate.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest 9.1, PYTHONPATH=src

## Global Constraints

- Run all tests with: `PYTHONPATH=src python -m pytest <path> -q`
- Never change domain entity logic or broker wire adapters unless they are the direct cause of a failing test
- Never add `skip_parity_gate=True` — only from env
- Commit after every task; commit message format: `fix(<scope>): <description>`
- Branch: `refactor/structural-cleanup` (already checked out)

---

## Task Map

| Task | Track | Independent? | Files |
|------|-------|-------------|-------|
| T1 | BUG-002: Optimizer int/Quantity | ✅ Yes | `src/analytics/backtest/optimizer.py` |
| T2 | BUG-001: OpenAPI 500 | ✅ Yes | `src/interface/api/main.py` |
| T3 | CLI unknown_command hangs | ✅ Yes | `src/interface/ui/main.py` or CLI entry |
| T4 | API contract re-exports | ✅ Yes | 4 module files |

Tasks T1, T2, T3, T4 are **fully independent** — they touch different files with no shared state.

---

## Task T1: Fix BUG-002 — Optimizer `int / Quantity` Silent Drop

**Files:**
- Modify: `src/analytics/backtest/optimizer.py` (around line 181)
- Test: `tests/unit/analytics/backtest/test_optimizer.py::TestOptimizeRsiPeriod::test_default_periods`

**Interfaces:**
- Consumes: `Quantity` from `domain.entities.order` (has `.magnitude` Decimal attr)
- Produces: `OptimizationResult.results` — must always contain one entry per param value, never silently skip

**Context (read before touching code):**

The optimizer runs a grid search over RSI periods `[5, 7, 10, 14, 21, 28]`. For `rsi_period=5`, an arithmetic operation does `int / Quantity` which raises `TypeError`. The except clause silently logs a WARNING and skips that period. The test expects 6 results but gets 5.

Real evidence from pytest:
```
WARNING analytics.backtest.optimizer:optimizer.py:181
  Failed for params {'rsi_period': 5}: unsupported operand type(s) for /: 'int' and 'Quantity'
AssertionError: assert 5 == 6
```

- [ ] **Step 1: Read the failing line in optimizer.py**

```bash
PYTHONPATH=src python -m pytest tests/unit/analytics/backtest/test_optimizer.py::TestOptimizeRsiPeriod::test_default_periods -v --tb=long 2>&1 | grep -A5 "WARNING\|TypeError\|optimizer.py"
```

Then read the file:
```bash
sed -n '160,200p' src/analytics/backtest/optimizer.py
```

Expected: see the line doing arithmetic with `rsi_period` and a `Quantity`.

- [ ] **Step 2: Run the failing test to confirm baseline**

```bash
PYTHONPATH=src python -m pytest tests/unit/analytics/backtest/test_optimizer.py::TestOptimizeRsiPeriod::test_default_periods -v
```

Expected: `FAILED — assert 5 == 6`

- [ ] **Step 3: Fix the arithmetic — unwrap Quantity before division**

Find the offending line in `src/analytics/backtest/optimizer.py` near line 181. It will look like:

```python
# BROKEN — Quantity can't be divided by int or used in int arithmetic
something / rsi_period   # or rsi_period / something
```

Fix: coerce the period value to int at the point of use:

```python
# Pattern to find (approximate — read actual line first):
period_val = int(param_values[0]) if hasattr(param_values[0], '__int__') else param_values[0]
```

The correct fix depends on what `param_values[0]` is. Two possible forms:

**If the Quantity wraps the period value (it comes in as `Quantity`):**
```python
# Before:
result = base_value / rsi_period  

# After:
period_as_int = int(rsi_period.magnitude) if hasattr(rsi_period, 'magnitude') else int(rsi_period)
result = base_value / period_as_int
```

**If the period is already int but something else is a Quantity:**
```python
# Find what the Quantity is and unwrap it:
qty_val = float(some_quantity.magnitude) if hasattr(some_quantity, 'magnitude') else float(some_quantity)
```

- [ ] **Step 4: Run the test — must now return 6 results**

```bash
PYTHONPATH=src python -m pytest tests/unit/analytics/backtest/test_optimizer.py -v
```

Expected: All optimizer tests PASS, no WARNING about `int / Quantity`.

- [ ] **Step 5: Run the full optimizer test file**

```bash
PYTHONPATH=src python -m pytest tests/unit/analytics/backtest/ -q
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/analytics/backtest/optimizer.py
git commit -m "fix(optimizer): unwrap Quantity before arithmetic in grid search — rsi_period=5 no longer silently dropped"
```

---

## Task T2: Fix BUG-001 — `/openapi.json` HTTP 500

**Files:**
- Modify: `src/interface/api/main.py`
- Test: Inline via `FastAPI TestClient`

**Interfaces:**
- Consumes: `create_app()` from `interface.api.main`
- Produces: `GET /openapi.json` returns HTTP 200 with valid JSON schema

**Context:**

When `GET /openapi.json` is called, FastAPI attempts to generate the OpenAPI schema and hits a Pydantic error:

```
PydanticUserError: TypeAdapter[Annotated[ForwardRef('OrderRequest'), Query(...)]] 
  is not fully defined; you should define OrderRequest and all referenced types, 
  then call .rebuild() on the instance.
```

This means `OrderRequest` is referenced via a `ForwardRef` string (lazy import) inside a FastAPI route, but Pydantic never gets told to resolve it.

- [ ] **Step 1: Find the ForwardRef usage**

```bash
grep -rn "ForwardRef\|'OrderRequest'\|\"OrderRequest\"" src/interface/api/ | grep -v __pycache__
```

Expected: shows where `OrderRequest` is used as a string forward reference in a route schema.

Also check:
```bash
grep -rn "from domain.orders" src/interface/api/ | grep -v __pycache__
```

- [ ] **Step 2: Confirm the failure baseline**

```bash
PYTHONPATH=src python -c "
from interface.api.main import create_app
from fastapi.testclient import TestClient
client = TestClient(create_app(), raise_server_exceptions=False)
r = client.get('/openapi.json')
print('status:', r.status_code)
" 2>&1 | grep "status:\|PydanticUser\|ERROR"
```

Expected: `status: 500`

- [ ] **Step 3: Fix — force model_rebuild() before schema generation**

In `src/interface/api/main.py`, inside `create_app()` or at module level, add a direct import and rebuild call:

```python
# At top of src/interface/api/main.py (with other imports):
from domain.orders.requests import OrderRequest as _OrderRequest

# Inside create_app(), before returning app — add:
try:
    _OrderRequest.model_rebuild()
except Exception:
    pass  # Already built — idempotent
```

If the ForwardRef is in a router file (not main.py), apply the fix there instead. The grep in Step 1 will tell you exactly which file.

Alternative fix if ForwardRef comes from a route decorator:
```python
# Change the route parameter from:
order: Annotated[OrderRequest, Query()]  # ForwardRef string

# To a direct import at the top of the router file:
from domain.orders.requests import OrderRequest
# Then in route: order: Annotated[OrderRequest, Query()]
```

- [ ] **Step 4: Verify the fix**

```bash
PYTHONPATH=src python -c "
from interface.api.main import create_app
from fastapi.testclient import TestClient
client = TestClient(create_app(), raise_server_exceptions=False)
r = client.get('/openapi.json')
print('status:', r.status_code)
assert r.status_code == 200, f'Still broken: {r.status_code}'
import json; schema = r.json()
print('paths count:', len(schema.get('paths', {})))
print('PASS')
" 2>&1 | grep -v "^{"
```

Expected: `status: 200`, `PASS`

- [ ] **Step 5: Run API unit tests**

```bash
PYTHONPATH=src python -m pytest tests/unit/ -k "api or openapi or schema" -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/interface/api/main.py  # (or whichever file you modified)
git commit -m "fix(api): resolve Pydantic ForwardRef for OrderRequest — /openapi.json no longer returns 500"
```

---

## Task T3: Fix CLI `unknown_command` Hang (Timeout)

**Files:**
- Investigate: `src/interface/ui/main.py` and CLI entry point
- Modify: wherever unknown command handling lives
- Test: `tests/component/ui/test_cli_endpoint_matrix.py::test_cli_endpoint_offline[unknown_command]`

**Interfaces:**
- Consumes: CLI invocation with unknown command string
- Produces: `exit(1)` within the test's `timeout_s=10` with an error message (not a hang)

**Context:**

The test invokes the CLI with an unknown command and expects it to exit with code 1 and an error message within 10 seconds. Instead, the CLI hangs indefinitely (hits 10s timeout):

```
AssertionError: endpoint 'unknown_command' timed out after 10s
CliResult(returncode=-1, ..., timeout=True)
```

The CLI is hanging — likely trying to connect to a broker, start an event loop, or wait for user input when it should immediately fail.

- [ ] **Step 1: Find the unknown command handler**

```bash
# Find the CLI entry point
grep -rn "unknown\|no.*such.*command\|invalid.*command\|unrecognized" src/interface/ui/ --include="*.py" | grep -v __pycache__ | head -20
```

Also:
```bash
# Find where commands are dispatched
grep -rn "def main\|typer.run\|app.command\|@app" src/interface/ui/main.py | head -20
```

Then read the test to understand what "unknown_command" means:
```bash
grep -A5 "unknown_command" tests/component/ui/test_cli_endpoint_matrix.py | head -20
```

- [ ] **Step 2: Reproduce the hang locally**

```bash
# Run the CLI with an unknown command (check what the test uses):
PYTHONPATH=src timeout 5 python -m interface.ui.main UNKNOWN_CMD_XYZ 2>&1 || echo "EXIT: $?"
```

Expected: should print error and exit, but instead hangs or takes >5s.

- [ ] **Step 3: Identify the hang root cause**

Look for:
- An event loop (`asyncio.run(...)`) that starts before command dispatch
- A broker connection attempt in `__init__` before routing to the command
- A `input()` call or interactive prompt
- An infinite `while True` loop with no early exit

Common pattern in Typer/Click CLIs that hang on unknown commands:

```python
# BAD — starts infrastructure before checking if command exists:
def main():
    setup_broker()  # hangs here
    dispatch_command()

# GOOD — check command first:
def main(command: str):
    if command not in KNOWN_COMMANDS:
        print(f"Unknown command: {command}", file=sys.stderr)
        raise SystemExit(1)
    setup_broker()
    dispatch_command()
```

- [ ] **Step 4: Fix — add early exit for unknown commands**

The fix must make unknown commands exit with code 1 immediately, before any async/broker setup:

```python
# In the CLI entry point or command dispatcher:
import sys

KNOWN_COMMANDS = {"live", "backtest", "replay", ...}  # fill from actual code

def main():
    # At the very top, before any async or broker setup:
    if len(sys.argv) > 1 and sys.argv[1] not in KNOWN_COMMANDS:
        print(f"Error: Unknown command '{sys.argv[1]}'", file=sys.stderr)
        print("Run 'tradex --help' for available commands.", file=sys.stderr)
        sys.exit(1)
    # ... rest of main
```

If using Typer, it has built-in unknown command handling — check if it's being overridden.

- [ ] **Step 5: Run the failing test**

```bash
PYTHONPATH=src python -m pytest "tests/component/ui/test_cli_endpoint_matrix.py::test_cli_endpoint_offline[unknown_command]" -v --timeout=15
```

Expected: PASS within timeout.

- [ ] **Step 6: Run the full CLI offline matrix**

```bash
PYTHONPATH=src python -m pytest tests/component/ui/test_cli_endpoint_matrix.py -k "offline" -q --timeout=30
```

Expected: all offline tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/interface/ui/main.py  # (or whichever file you modified)
git commit -m "fix(cli): unknown command exits immediately with code 1 instead of hanging"
```

---

## Task T4: Fix API Contract Re-exports and Missing Methods

**Files:**
- Modify: `src/analytics/strategy/models.py` (re-export Candidate)
- Modify: `src/application/oms/position_manager.py` (add get_net_pnl or alias)
- Modify: `src/infrastructure/event_bus/dead_letter_queue.py` (add size() alias)
- Modify: `src/analytics/core/models.py` (accept datetime as alias for timestamp)
- Modify: `tests/unit/brokers/upstox/test_upstox_adapter.py` (delete stale skip)

**Interfaces:**
- Consumes: existing classes as discovered at runtime
- Produces: backward-compatible surface — callers using old names still work

**Context (9 API contract mismatches proven at runtime):**

| What | Wrong | Correct |
|------|-------|---------|
| Candidate import | `analytics.strategy.models` | `analytics.strategy.evaluator_bridge` |
| PositionManager.get_net_pnl() | assumed to exist | doesn't exist |
| DeadLetterQueue.size() | assumed method | doesn't exist; use `.stats()['size']` |
| normalize_ohlcv | accepts datetime col | requires timestamp col |
| RiskResult.passed | assumed field | `.allowed` field |
| Upstox adapter test | references deleted `UpstoxDataAdapter` | skip comment, should be deleted |

Note: `RiskManager.__init__` and `MarginChecker.__init__` signature changes are internal — they are already correct in source; the mismatches were in our audit scripts only. Do NOT change source for those.

- [ ] **Step 1: Add Candidate re-export to analytics.strategy.models**

Read current `src/analytics/strategy/models.py`:
```bash
grep -n "Candidate\|evaluator_bridge\|import" src/analytics/strategy/models.py | head -20
```

Add at the bottom of `src/analytics/strategy/models.py`:
```python
# Backward-compatible re-export — Candidate lives in evaluator_bridge
# but callers may import from models.
try:
    from analytics.strategy.evaluator_bridge import Candidate  # noqa: F401
except ImportError:
    pass  # evaluator_bridge not available in this context
```

Verify:
```bash
PYTHONPATH=src python -c "from analytics.strategy.models import Candidate; print('Candidate re-export OK:', Candidate)"
```

Expected: prints Candidate class without ImportError.

- [ ] **Step 2: Add get_net_pnl() to PositionManager**

Read the existing PositionManager to understand how PnL is computed:
```bash
grep -n "pnl\|profit\|loss\|get_position" src/application/oms/position_manager.py | head -30
```

Add a `get_net_pnl()` method that delegates to existing logic:
```python
def get_net_pnl(self) -> Decimal:
    """Return the net unrealized PnL across all open positions.
    
    Sums position.unrealized_pnl for all positions. Returns Decimal('0')
    if no positions exist.
    """
    positions = self.get_positions()
    total = Decimal("0")
    for pos in positions:
        pnl = getattr(pos, "unrealized_pnl", None) or getattr(pos, "pnl", None)
        if pnl is not None:
            total += Decimal(str(pnl))
    return total
```

Verify:
```bash
PYTHONPATH=src python -c "
from application.oms.position_manager import PositionManager
from infrastructure.event_bus.event_bus import EventBus
from decimal import Decimal
pm = PositionManager(event_bus=EventBus())
result = pm.get_net_pnl()
assert isinstance(result, Decimal)
print('get_net_pnl() OK:', result)
"
```

- [ ] **Step 3: Add size() alias to DeadLetterQueue**

Read `src/infrastructure/event_bus/dead_letter_queue.py`:
```bash
grep -n "def stats\|def size\|def peek\|def push" src/infrastructure/event_bus/dead_letter_queue.py
```

Add a `size()` convenience method:
```python
def size(self) -> int:
    """Convenience alias for stats()['size']. Avoids callers needing to know the stats key."""
    return self.stats()["size"]
```

Verify:
```bash
PYTHONPATH=src python -c "
from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
from domain.events.types import DomainEvent
dlq = DeadLetterQueue()
print('size before:', dlq.size())
dlq.push_failure(event=DomainEvent.now('X',{}), handler_id='t', exc=RuntimeError('x'), traceback='tb')
print('size after push:', dlq.size())
assert dlq.size() == 1
print('DeadLetterQueue.size() OK')
"
```

- [ ] **Step 4: Accept 'datetime' column as alias for 'timestamp' in normalize_ohlcv**

Read `src/analytics/core/models.py`:
```bash
grep -n "timestamp\|datetime\|required\|missing" src/analytics/core/models.py | head -30
```

Find the validation that raises `ValueError: OHLCV data missing required columns: ['timestamp']`.

Add a column aliasing step before validation:
```python
# In normalize_ohlcv(), before the missing-columns check, add:
# Allow 'datetime' as an alias for 'timestamp'
if "timestamp" not in data.columns and "datetime" in data.columns:
    data = data.copy()
    data["timestamp"] = data["datetime"]
```

Verify:
```bash
PYTHONPATH=src python -c "
import pandas as pd, numpy as np
from analytics.core.models import normalize_ohlcv
n=10
dates = pd.date_range('2026-01-01', periods=n, freq='1min')
df = pd.DataFrame({'datetime': dates, 'open': 1.0, 'high': 1.1, 'low': 0.9,
    'close': 1.0, 'volume': 100.0, 'symbol': 'X', 'exchange': 'NSE', 'timeframe': '1m'})
result = normalize_ohlcv(df, symbol='X')
assert 'timestamp' in result.columns
print('datetime->timestamp alias OK, columns:', list(result.columns))
"
```

- [ ] **Step 5: Delete stale Upstox adapter test**

```bash
# Read it first to confirm it's truly stale
cat tests/unit/brokers/upstox/test_upstox_adapter.py
```

If the entire file is skipped/stale (references deleted `UpstoxDataAdapter`), delete it:
```bash
git rm tests/unit/brokers/upstox/test_upstox_adapter.py
```

If only part of it is stale, delete only the stale test class and leave valid tests.

- [ ] **Step 6: Run the audit phase 2 script to verify all contracts**

```bash
PYTHONPATH=src python -m audit.phase2_leaf_components 2>&1 | tail -10
```

Expected: all 17 tests PASS.

- [ ] **Step 7: Run the full unit test suite**

```bash
PYTHONPATH=src python -m pytest tests/unit/ -q --tb=line 2>&1 | tail -10
```

Expected: 0 failures (or only pre-existing failures unrelated to this task).

- [ ] **Step 8: Commit**

```bash
git add src/analytics/strategy/models.py \
        src/application/oms/position_manager.py \
        src/infrastructure/event_bus/dead_letter_queue.py \
        src/analytics/core/models.py
git rm tests/unit/brokers/upstox/test_upstox_adapter.py 2>/dev/null || true
git commit -m "fix(contracts): add backward-compat re-exports and missing methods for 9 runtime-proven API mismatches"
```

---

## Final Integration Gate

After all 4 tasks are complete and committed, run the full verification:

- [ ] **Gate 1: All audit phases pass**

```bash
PYTHONPATH=src python -m audit.phase0_discovery && \
PYTHONPATH=src python -m audit.phase2_leaf_components && \
echo "Audit phases PASS"
```

- [ ] **Gate 2: Full pytest unit + component**

```bash
PYTHONPATH=src python -m pytest tests/unit tests/component -q --tb=line 2>&1 | tail -5
```

Expected: 0 failures.

- [ ] **Gate 3: Push**

```bash
git push origin refactor/structural-cleanup
```
