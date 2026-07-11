"""TOS-P5-011 — stream→OMS mutation lock discipline.

PositionManager and OrderManager must hold a threading lock around book
mutations so stream callbacks cannot race the place path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.architecture
def test_position_manager_uses_rlock() -> None:
    text = (SRC / "application/oms/position_manager.py").read_text(encoding="utf-8")
    assert "threading.RLock" in text or "RLock()" in text
    assert "with self._lock" in text
    assert "def apply_trade" in text


@pytest.mark.architecture
def test_order_manager_uses_lock_around_book() -> None:
    text = (SRC / "application/oms/order_manager.py").read_text(encoding="utf-8")
    assert "_lock" in text
    assert "def place_order" in text


@pytest.mark.architecture
def test_order_lifecycle_book_writes_under_lock_param() -> None:
    """Lifecycle methods accept lock and mutate maps under it."""
    text = (SRC / "application/oms/_internal/order_lifecycle.py").read_text(
        encoding="utf-8"
    )
    assert "with lock" in text
