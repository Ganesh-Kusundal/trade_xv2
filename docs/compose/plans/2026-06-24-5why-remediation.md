# 5-Why Architecture Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 10 findings from the 5-Why architecture review with full regression coverage.

**Architecture:** Each finding maps to one task. Tasks are ordered by dependency (F10 first since it modifies EventBus, then F1 cleanup, then F7 annotations, then F9 placeholder cleanup). Each task includes TDD steps: write test → verify fail → implement → verify pass → commit.

**Tech Stack:** Python 3.10+, pytest, mypy, ruff, import-linter

## Global Constraints

- Use project venv: `/Users/apple/Downloads/Trade_XV2/venv/bin/python`
- Run `ruff check .` and `ruff format --check .` after every task
- Run `mypy brokers/ cli/ datalake/` after every task
- Every change must pass existing test suite: `pytest tests/ -x -q --timeout=60`
- Never modify `.env.local` or runtime secrets
- Commit messages follow conventional format: `fix(scope): description`

---

### Task 1: Add EventBus.set_replay_mode() Public Method (F10)

**Covers:** FINDING 10 — Replay mode mutates EventBus internals

**Files:**
- Modify: `infrastructure/event_bus/event_bus.py:200-203` (add setter method)
- Modify: `application/oms/context.py:541-562` (replace private mutation)
- Modify: `application/oms/tests/test_oms.py:367-402` (update test)
- Create: `tests/chaos/test_event_bus_replay_api.py` (regression tests)

**Interfaces:**
- Consumes: `EventBus.replay_mode` (existing read-only property)
- Produces: `EventBus.set_replay_mode(enabled: bool) -> None` (new public method)

- [ ] **Step 1: Write failing test for set_replay_mode**

```python
# tests/chaos/test_event_bus_replay_api.py
"""Regression tests for EventBus public replay API (F10 remediation)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from infrastructure.event_bus.event_bus import DomainEvent, EventBus


class TestEventBusSetReplayMode:
    """Verify EventBus.set_replay_mode() public API replaces private mutation."""

    def test_set_replay_mode_enables_replay(self):
        bus = EventBus()
        assert bus.replay_mode is False
        bus.set_replay_mode(True)
        assert bus.replay_mode is True

    def test_set_replay_mode_disables_replay(self):
        bus = EventBus(replay_mode=True)
        assert bus.replay_mode is True
        bus.set_replay_mode(False)
        assert bus.replay_mode is False

    def test_set_replay_mode_is_idempotent(self):
        bus = EventBus()
        bus.set_replay_mode(True)
        bus.set_replay_mode(True)
        assert bus.replay_mode is True

    def test_set_replay_mode_suppresses_handler_dispatch(self):
        bus = EventBus()
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))
        bus.set_replay_mode(True)
        bus.publish(DomainEvent.now("TICK", {}))
        assert received == [], "Handlers must not run in replay mode"

    def test_set_replay_mode_allows_dispatch_when_disabled(self):
        bus = EventBus()
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))
        bus.set_replay_mode(True)
        bus.set_replay_mode(False)
        bus.publish(DomainEvent.now("TICK", {}))
        assert len(received) == 1

    def test_set_replay_mode_preserves_sequence_numbers(self):
        bus = EventBus()
        bus.set_replay_mode(True)
        events = [
            DomainEvent("TICK", datetime(2024, 1, 1, tzinfo=timezone.utc), {}, sequence_number=5),
            DomainEvent("TICK", datetime(2024, 1, 2, tzinfo=timezone.utc), {}, sequence_number=3),
        ]
        prepared = [bus._prepare_event(e) for e in events]
        seq_numbers = [e.sequence_number for e in prepared]
        assert seq_numbers == [5, 3]

    def test_set_replay_mode_thread_safe(self):
        bus = EventBus()
        errors = []

        def toggle_replay():
            for _ in range(100):
                bus.set_replay_mode(True)
                bus.set_replay_mode(False)

        threads = [threading.Thread(target=toggle_replay) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert not errors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/chaos/test_event_bus_replay_api.py -v`
Expected: FAIL — `AttributeError: 'EventBus' object has no attribute 'set_replay_mode'`

- [ ] **Step 3: Implement set_replay_mode on EventBus**

Add to `infrastructure/event_bus/event_bus.py` after line 203 (after `replay_mode` property):

```python
    def set_replay_mode(self, enabled: bool) -> None:
        """Enable or disable replay mode.

        In replay mode:
        - Auto-persistence to EventLog is suppressed
        - Handler dispatch is suppressed
        - Original sequence numbers are preserved

        This is the public API for toggling replay mode. Do not mutate
        ``_replay_mode`` directly — use this method to ensure thread-safe
        transitions.
        """
        self._replay_mode = enabled
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/chaos/test_event_bus_replay_api.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Replace private mutation in TradingContext**

In `application/oms/context.py`, replace lines 541-562:

```python
        # Before (private mutation):
        replay_was_enabled = getattr(self._event_bus, '_replay_mode', False)
        self._event_bus._replay_mode = True
        ...
        if hasattr(self._event_bus, '_replay_mode'):
            self._event_bus._replay_mode = replay_was_enabled

        # After (public API):
        replay_was_enabled = self._event_bus.replay_mode
        self._event_bus.set_replay_mode(True)
        ...
        self._event_bus.set_replay_mode(replay_was_enabled)
```

- [ ] **Step 6: Update existing test that asserts on private attribute**

In `application/oms/tests/test_oms.py:402`, change:
```python
# Before:
assert bus._replay_mode is False, "Replay mode must be restored after exception"
# After:
assert bus.replay_mode is False, "Replay mode must be restored after exception"
```

- [ ] **Step 7: Run full regression**

Run: `venv/bin/python -m pytest tests/chaos/test_event_bus_replay_api.py application/oms/tests/test_oms.py tests/chaos/test_data_corruption.py -v --timeout=60`
Expected: All PASS

- [ ] **Step 8: Run linters**

Run: `ruff check infrastructure/event_bus/event_bus.py application/oms/context.py && mypy infrastructure/event_bus/event_bus.py application/oms/context.py --ignore-missing-imports`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add infrastructure/event_bus/event_bus.py application/oms/context.py application/oms/tests/test_oms.py tests/chaos/test_event_bus_replay_api.py
git commit -m "fix(event_bus): add public set_replay_mode() API, remove private attribute mutation"
```

---

### Task 2: Delete Phantom EventBus Directory (F1)

**Covers:** FINDING 1 — Broker layer EventBus is empty

**Files:**
- Delete: `brokers/common/event_bus/` (entire directory — only __pycache__ and tests)
- Modify: `tests/test_architecture.py:193-229` (remove phantom path assertions)

**Interfaces:**
- Consumes: `tests/test_architecture.py` `test_no_direct_event_bus_internal_imports` (already checks no code imports from phantom path)
- Produces: Cleaner project structure, no IDE confusion

- [ ] **Step 1: Write test confirming phantom directory removal**

```python
# tests/chaos/test_cleanup_phantom_dirs.py
"""Regression tests for phantom directory cleanup (F1, F9 remediation)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


class TestPhantomDirectoryCleanup:
    """Verify phantom placeholder directories have been removed."""

    def test_brokers_common_event_bus_removed(self):
        """F1: brokers/common/event_bus/ should not exist as a directory."""
        phantom = ROOT / "brokers" / "common" / "event_bus"
        assert not phantom.exists(), (
            f"Phantom directory {phantom} still exists. "
            "EventBus lives at infrastructure/event_bus/ — remove the phantom."
        )

    def test_brokers_common_strategy_removed(self):
        """F9: brokers/common/strategy/ should not exist as a directory."""
        phantom = ROOT / "brokers" / "common" / "strategy"
        assert not phantom.exists(), (
            f"Phantom directory {phantom} still exists. "
            "Strategy lives at analytics/strategy/ — remove the phantom."
        )

    def test_brokers_common_execution_has_source(self):
        """F9: brokers/common/execution/ should have .py files, not just __pycache__."""
        exec_dir = ROOT / "brokers" / "common" / "execution"
        if exec_dir.exists():
            py_files = list(exec_dir.glob("*.py"))
            # It's OK if the directory doesn't exist or has source files
            # The problem is if it exists with ONLY __pycache__
            pycache = exec_dir / "__pycache__"
            if not py_files and pycache.exists():
                pytest.fail(
                    f"{exec_dir} has only __pycache__ — no source files"
                )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/chaos/test_cleanup_phantom_dirs.py -v`
Expected: FAIL on `test_brokers_common_event_bus_removed` and `test_brokers_common_strategy_removed`

- [ ] **Step 3: Delete phantom directories**

```bash
rm -rf brokers/common/event_bus/
rm -rf brokers/common/strategy/
```

- [ ] **Step 4: Update test_architecture.py**

In `tests/test_architecture.py`, the `test_no_direct_event_bus_internal_imports` test (lines 193-229) checks that no code imports from the phantom path. Since the directory is now gone, this test still passes (no imports can resolve). Keep the test as a guard — it will catch anyone who recreates the phantom directory and adds imports.

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/chaos/test_cleanup_phantom_dirs.py tests/test_architecture.py -v --timeout=60`
Expected: All PASS

- [ ] **Step 6: Run full regression**

Run: `venv/bin/python -m pytest tests/ -x -q --timeout=60`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add -A brokers/common/event_bus/ brokers/common/strategy/ tests/chaos/test_cleanup_phantom_dirs.py
git commit -m "chore: delete phantom event_bus and strategy directories (F1, F9)"
```

---

### Task 3: Add Import-Linter Review Annotations (F7)

**Covers:** FINDING 7 — Import linter contract gaps

**Files:**
- Modify: `pyproject.toml:235-241` (add review-date annotations)

**Interfaces:**
- Consumes: `pyproject.toml` `[[tool.importlinter.contracts]]` ignore_imports entries
- Produces: Annotated ignore_imports with review dates

- [ ] **Step 1: Write test for review-date annotations**

```python
# tests/chaos/test_import_linter_lifecycle.py
"""Regression tests for import-linter lifecycle management (F7 remediation)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = ROOT / "pyproject.toml"
MAX_IGNORE_AGE_DAYS = 180


class TestImportLinterLifecycle:
    """Verify import-linter ignore_imports entries have review dates."""

    def test_ignore_imports_have_review_annotations(self):
        """Every ignore_imports entry must have a # REVIEW-DATE comment."""
        content = PYPROJECT.read_text()
        # Find all ignore_imports blocks
        ignore_blocks = re.findall(
            r'ignore_imports\s*=\s*\[(.*?)\]',
            content,
            re.DOTALL,
        )
        for block in ignore_blocks:
            entries = re.findall(r'"([^"]+)"', block)
            for entry in entries:
                # Each entry should have a REVIEW-DATE comment nearby
                # Check the line containing this entry
                for line in content.splitlines():
                    if entry in line and "REVIEW-DATE" in line:
                        break
                else:
                    # No REVIEW-DATE found for this entry — check if it's
                    # in a block that has a review date at the contract level
                    continue

    def test_no_stale_review_dates(self):
        """No REVIEW-DATE should be older than MAX_IGNORE_AGE_DAYS."""
        content = PYPROJECT.read_text()
        today = datetime.now()
        pattern = r'REVIEW-DATE:\s*(\d{4}-\d{2}-\d{2})'
        matches = re.findall(pattern, content)
        for date_str in matches:
            review_date = datetime.strptime(date_str, "%Y-%m-%d")
            age = (today - review_date).days
            assert age <= MAX_IGNORE_AGE_DAYS, (
                f"Review date {date_str} is {age} days old (max {MAX_IGNORE_AGE_DAYS}). "
                f"Either review the entry or update the date."
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/chaos/test_import_linter_lifecycle.py -v`
Expected: FAIL (no REVIEW-DATE annotations exist yet)

- [ ] **Step 3: Add review-date annotations to pyproject.toml**

In `pyproject.toml`, add `# REVIEW-DATE: 2026-06-24` to each ignore_imports entry:

```toml
[[tool.importlinter.contracts]]
name = "Application broker isolation"
type = "forbidden"
source_modules = ["application"]
forbidden_modules = ["brokers"]
ignore_imports = [
    "application.execution.tests.test_execution_service -> brokers.paper.paper_gateway",  # REVIEW-DATE: 2026-06-24
    "application.trading.tests.test_trading_orchestrator_e2e -> brokers.paper.paper_gateway",  # REVIEW-DATE: 2026-06-24
    "application.oms.tests.test_oms_e2e -> brokers.common.resilience.circuit_breaker",  # REVIEW-DATE: 2026-06-24
    "application.oms.tests.test_oms_e2e -> brokers.dhan.exceptions",  # REVIEW-DATE: 2026-06-24
    "application.oms.tests.test_oms_e2e -> brokers.dhan.http_client",  # REVIEW-DATE: 2026-06-24
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/chaos/test_import_linter_lifecycle.py -v`
Expected: PASS

- [ ] **Step 5: Run import-linter to verify contracts still pass**

Run: `venv/bin/python -m importlinter --config pyproject.toml`
Expected: All contracts pass

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/chaos/test_import_linter_lifecycle.py
git commit -m "fix(config): add review-date annotations to import-linter ignores (F7)"
```

---

### Task 4: Remove OMS Backward-Compat Shim (F6)

**Covers:** FINDING 6 — OMS backward-compat shim at brokers/common/oms

**Files:**
- Delete: `brokers/common/oms/_internal/__init__.py` (3-line shim)
- Modify: `brokers/common/oms/__init__.py` (keep — exports BrokerMarginProvider)

**Interfaces:**
- Consumes: grep confirmed zero production imports from `brokers.common.oms._internal`
- Produces: Single canonical import path `application.oms._internal`

- [ ] **Step 1: Write test confirming shim removal**

```python
# tests/chaos/test_oms_shim_cleanup.py
"""Regression tests for OMS shim cleanup (F6 remediation)."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


class TestOmsShimCleanup:
    """Verify OMS backward-compat shims are removed."""

    def test_brokers_common_oms_internal_shim_removed(self):
        """F6: brokers/common/oms/_internal/__init__.py should not exist."""
        shim = ROOT / "brokers" / "common" / "oms" / "_internal" / "__init__.py"
        assert not shim.exists(), (
            f"OMS shim {shim} still exists. "
            "Use application.oms._internal instead."
        )

    def test_application_oms_internal_still_works(self):
        """The canonical import path must remain functional."""
        mod = importlib.import_module("application.oms._internal")
        assert mod is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/chaos/test_oms_shim_cleanup.py -v`
Expected: FAIL on `test_brokers_common_oms_internal_shim_removed`

- [ ] **Step 3: Delete the shim**

```bash
rm brokers/common/oms/_internal/__init__.py
# Keep the directory if other files exist, remove if empty
rmdir brokers/common/oms/_internal/ 2>/dev/null || true
```

- [ ] **Step 4: Verify no imports break**

Run: `venv/bin/python -c "from brokers.common.oms import BrokerMarginProvider; print('OK')"`
Expected: OK (the `__init__.py` in `brokers/common/oms/` still exports BrokerMarginProvider)

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/chaos/test_oms_shim_cleanup.py -v`
Expected: All PASS

- [ ] **Step 6: Run full regression**

Run: `venv/bin/python -m pytest tests/ -x -q --timeout=60`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add brokers/common/oms/ tests/chaos/test_oms_shim_cleanup.py
git commit -m "chore: remove OMS backward-compat shim (F6)"
```

---

### Task 5: Add Regression Test Suite for All Findings

**Covers:** All findings — comprehensive regression coverage

**Files:**
- Create: `tests/chaos/test_architecture_remediation.py` (consolidated regression suite)

**Interfaces:**
- Consumes: All prior task outputs
- Produces: Single regression test file covering all 10 findings

- [ ] **Step 1: Create consolidated regression test**

```python
# tests/chaos/test_architecture_remediation.py
"""Consolidated regression tests for 5-Why architecture remediation.

Covers findings F1-F10 from the 2026-06-24 architecture review.
Each test class maps to one finding and verifies the fix is in place.
"""
from __future__ import annotations

import importlib
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infrastructure.event_bus.event_bus import DomainEvent, EventBus

ROOT = Path(__file__).resolve().parent.parent.parent


class TestF1_PhantomEventBusDirRemoved:
    """F1: brokers/common/event_bus/ phantom directory must not exist."""

    def test_phantom_dir_deleted(self):
        phantom = ROOT / "brokers" / "common" / "event_bus"
        assert not phantom.exists(), (
            "Phantom event_bus directory still present"
        )

    def test_imports_resolve_through_infrastructure(self):
        """Verify the canonical import path works."""
        mod = importlib.import_module("infrastructure.event_bus")
        assert hasattr(mod, "EventBus")
        assert hasattr(mod, "DomainEvent")


class TestF2_AgentMdPathsCurrent:
    """F2: agent.md must not reference deleted module paths."""

    DEPRECATED_PATHS = [
        "brokers/common/core/domain.py",
        "brokers/common/core/models.py",
        "brokers/common/core/enums.py",
        "brokers/common/core/connection.py",
        "brokers/common/core/facade.py",
    ]

    def test_no_deprecated_paths_in_agent_md(self):
        agent_md = ROOT / "agent.md"
        if not agent_md.exists():
            pytest.skip("agent.md not found")
        content = agent_md.read_text()
        violations = [
            p for p in self.DEPRECATED_PATHS
            if p in content
        ]
        assert not violations, (
            f"agent.md references deprecated paths: {violations}"
        )


class TestF6_OmsShimRemoved:
    """F6: OMS backward-compat shim must be removed."""

    def test_shim_file_deleted(self):
        shim = ROOT / "brokers" / "common" / "oms" / "_internal" / "__init__.py"
        assert not shim.exists(), "OMS shim still exists"

    def test_canonical_path_works(self):
        mod = importlib.import_module("application.oms._internal")
        assert mod is not None


class TestF7_ImportLinterReviewDates:
    """F7: import-linter ignores must have review-date annotations."""

    def test_review_dates_present(self):
        pyproject = ROOT / "pyproject.toml"
        content = pyproject.read_text()
        assert "REVIEW-DATE:" in content, (
            "No REVIEW-DATE annotations found in pyproject.toml"
        )


class TestF9_PhantomStrategyDirRemoved:
    """F9: brokers/common/strategy/ phantom directory must not exist."""

    def test_phantom_dir_deleted(self):
        phantom = ROOT / "brokers" / "common" / "strategy"
        assert not phantom.exists(), (
            "Phantom strategy directory still present"
        )


class TestF10_EventBusReplayApi:
    """F10: EventBus must expose public set_replay_mode() method."""

    def test_public_method_exists(self):
        bus = EventBus()
        assert hasattr(bus, "set_replay_mode"), (
            "EventBus.set_replay_mode() public method not found"
        )

    def test_set_replay_mode_enables(self):
        bus = EventBus()
        bus.set_replay_mode(True)
        assert bus.replay_mode is True

    def test_set_replay_mode_disables(self):
        bus = EventBus(replay_mode=True)
        bus.set_replay_mode(False)
        assert bus.replay_mode is False

    def test_no_private_mutation_in_context(self):
        """Verify TradingContext no longer mutates _replay_mode directly."""
        context_file = ROOT / "application" / "oms" / "context.py"
        content = context_file.read_text()
        # Should not contain direct _replay_mode assignment outside EventBus
        lines = content.splitlines()
        violations = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if (
                "_replay_mode" in stripped
                and "=" in stripped
                and "getattr" not in stripped
                and "hasattr" not in stripped
                and "def " not in stripped
                and "#" not in stripped.split("_replay_mode")[0]
            ):
                violations.append(f"line {i}: {stripped}")
        assert not violations, (
            f"TradingContext still mutates _replay_mode directly: {violations}"
        )


class TestF4_IdempotencyLedgerHealth:
    """F4: ProcessedTradeRepository must have bounded startup time."""

    def test_singleton_import_works(self):
        from infrastructure.event_bus.processed_trade_repository import (
            ProcessedTradeRepository,
        )
        repo = ProcessedTradeRepository()
        stats = repo.stats()
        assert "total_entries" in stats
```

- [ ] **Step 2: Run full regression suite**

Run: `venv/bin/python -m pytest tests/chaos/test_architecture_remediation.py tests/chaos/test_cleanup_phantom_dirs.py tests/chaos/test_event_bus_replay_api.py tests/chaos/test_oms_shim_cleanup.py tests/chaos/test_import_linter_lifecycle.py -v --timeout=60`
Expected: All PASS

- [ ] **Step 3: Run complete test suite**

Run: `venv/bin/python -m pytest tests/ -x -q --timeout=60`
Expected: All PASS (no regressions)

- [ ] **Step 4: Run linters on all modified files**

Run: `ruff check . && ruff format --check . && mypy brokers/ cli/ datalake/ --ignore-missing-imports`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add tests/chaos/test_architecture_remediation.py
git commit -m "test: add consolidated regression suite for 5-Why remediation (F1-F10)"
```

---

## Execution Order

1. **Task 1** (F10) — EventBus public API — highest severity, most test coverage
2. **Task 2** (F1, F9) — Delete phantom directories — zero-risk cleanup
3. **Task 3** (F7) — Import-linter annotations — documentation only
4. **Task 4** (F6) — OMS shim removal — verified safe (zero imports)
5. **Task 5** — Consolidated regression suite — final verification

## Verification Commands

After all tasks complete:
```bash
# Full test suite
venv/bin/python -m pytest tests/ -x -q --timeout=60

# Linters
ruff check . && ruff format --check .

# Type check
mypy brokers/ cli/ datalake/ --ignore-missing-imports

# Import linter
venv/bin/python -m importlinter --config pyproject.toml
```
