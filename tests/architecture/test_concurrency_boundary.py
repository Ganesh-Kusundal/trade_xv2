"""DR-E2 / TOS-P5-010 concurrency boundary enforcement (mixed thread/asyncio).

Exactly ONE module in the tree — ``src/runtime/event_loop.py`` — may call
``asyncio.new_event_loop()``. All other call sites must use
``run_coro_sync`` / ``get_runtime_loop`` / ``new_dedicated_loop``.

Run:
    PYTHONPATH=src pytest tests/architecture/test_concurrency_boundary.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
CENTRAL_MODULE = SRC_ROOT / "runtime" / "event_loop.py"


def _grep_new_event_loop_files() -> list[Path]:
    """Return all .py files under src/ containing ``new_event_loop(``."""
    out = subprocess.run(
        ["grep", "-rl", "--include=*.py", "new_event_loop(", str(SRC_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if not out.stdout.strip():
        return []
    return [Path(p) for p in out.stdout.splitlines()]


def _count_new_event_loop_lines_under(root: Path, exclude: Path) -> int:
    out = subprocess.run(
        ["grep", "-rn", "--include=*.py", "new_event_loop(", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    count = 0
    for line in out.stdout.splitlines():
        path = line.split(":", 1)[0]
        if Path(path).resolve() == exclude.resolve():
            continue
        count += 1
    return count


class TestConcurrencyBoundary:
    """Enforce the single event-loop boundary."""

    def test_central_module_exists_and_is_sanctioned_site(self):
        assert CENTRAL_MODULE.exists()
        text = CENTRAL_MODULE.read_text()
        assert "asyncio.new_event_loop()" in text

    def test_no_new_event_loop_outside_central_module(self):
        """Zero ad-hoc loop creation outside runtime.event_loop (TOS-P5-010)."""
        files = _grep_new_event_loop_files()
        central_present = any(f.resolve() == CENTRAL_MODULE.resolve() for f in files)
        stray = [f for f in files if f.resolve() != CENTRAL_MODULE.resolve()]
        assert central_present, "central module must contain new_event_loop()"
        assert not stray, (
            f"Ad-hoc new_event_loop() outside runtime.event_loop (TOS-P5-010): "
            f"{[str(f) for f in stray]}"
        )

    def test_legacy_line_count_is_zero(self):
        """No legacy new_event_loop() lines remain outside the central module."""
        count = _count_new_event_loop_lines_under(SRC_ROOT, CENTRAL_MODULE)
        assert count == 0, (
            f"Found {count} new_event_loop() lines outside "
            f"src/runtime/event_loop.py — route them through the boundary."
        )


class TestRuntimeLoopBoundaryHelpers:
    """Exercise the centralized acquire/guard helpers (unit level)."""

    def test_ensure_returns_same_loop(self):
        from runtime.event_loop import ensure_runtime_loop, get_runtime_loop

        loop = ensure_runtime_loop()
        assert loop is not None
        assert ensure_runtime_loop() is loop
        assert get_runtime_loop() is loop

    def test_get_before_establish_raises(self):
        from runtime import event_loop as mod

        prior = mod._RUNTIME_LOOP
        mod._RUNTIME_LOOP = None
        try:
            with pytest.raises(RuntimeError):
                mod.get_runtime_loop()
        finally:
            mod._RUNTIME_LOOP = prior

    def test_set_runtime_loop_is_acquired(self):
        from runtime import event_loop as mod

        prior = mod._RUNTIME_LOOP
        loop = mod.new_dedicated_loop()
        try:
            mod.set_runtime_loop(loop)
            assert mod.get_runtime_loop() is loop
        finally:
            mod._RUNTIME_LOOP = prior
            if not loop.is_closed():
                loop.close()

    def test_run_coro_sync_simple(self):
        from runtime.event_loop import run_coro_sync

        async def _one() -> int:
            return 1

        assert run_coro_sync(_one()) == 1

    def test_assert_single_loop_boundary_clean_when_no_stray(self):
        from runtime.event_loop import assert_single_loop_boundary

        violations = assert_single_loop_boundary()
        assert violations == []
