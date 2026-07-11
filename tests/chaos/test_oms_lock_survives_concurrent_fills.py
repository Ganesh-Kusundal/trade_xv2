"""TOS-P7-001 polish — concurrent fills do not corrupt position book."""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from application.oms.position_manager import PositionManager
from domain import Side, Trade


@pytest.mark.chaos
def test_concurrent_apply_trade_is_thread_safe():
    pm = PositionManager(enforce_state_transitions=False)
    errors: list[BaseException] = []

    def _worker(n: int) -> None:
        try:
            for i in range(50):
                pm.apply_trade(
                    Trade(
                        trade_id=f"t-{n}-{i}",
                        order_id=f"o-{n}-{i}",
                        symbol="RELIANCE",
                        exchange="NSE",
                        side=Side.BUY,
                        quantity=1,
                        price=Decimal("100"),
                    )
                )
        except BaseException as exc:  # noqa: BLE001 — collect for assert
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    pos = pm.get_position("RELIANCE", "NSE") if hasattr(pm, "get_position") else None
    if pos is None:
        # Fall back to internal book snapshot if public API differs.
        positions = getattr(pm, "_positions", {})
        assert any("RELIANCE" in str(k) for k in positions)
        qty = sum(p.quantity for p in positions.values() if p.symbol == "RELIANCE")
        assert qty == 8 * 50
    else:
        assert pos.quantity == 8 * 50
