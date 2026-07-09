"""OrderBlockedError — kill-switch / OMS enforcement error."""

from __future__ import annotations

from application.oms.errors import OrderBlockedError


def test_order_blocked_error_fields() -> None:
    err = OrderBlockedError("blocked", operation="place_order", reason="kill switch")
    assert err.operation == "place_order"
    assert err.reason == "kill switch"
    assert err.timestamp > 0
