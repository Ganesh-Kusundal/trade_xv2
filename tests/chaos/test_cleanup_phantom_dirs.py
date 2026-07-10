"""Regression tests for phantom directory cleanup (F1, F9 remediation)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class TestPhantomDirectoryCleanup:
    def test_brokers_common_event_bus_removed(self):
        phantom = ROOT / "src" / "brokers" / "common" / "event_bus"
        assert not phantom.exists(), (
            f"Phantom directory {phantom} still exists. "
            "EventBus lives at infrastructure/event_bus/ — remove the phantom."
        )

    def test_brokers_common_strategy_removed(self):
        phantom = ROOT / "src" / "brokers" / "common" / "strategy"
        assert not phantom.exists(), (
            f"Phantom directory {phantom} still exists. "
            "Strategy lives at analytics/strategy/ — remove the phantom."
        )
