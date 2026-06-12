"""Regression tests for ``DhanOrderCommandAdapter.cancel_order``.

Pre-fix: ``cancel_order`` returned ``True`` whenever the response had a
``"data"`` key, even if ``status == "error"``. A failed cancel looked like
a successful one.

Post-fix: ``cancel_order`` only returns ``True`` when ``status == "success"``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.dhan.orders.order_command_adapter import DhanOrderCommandAdapter

pytestmark = pytest.mark.unit


def _build_adapter(cancel_return):
    """Build an adapter whose underlying ``cancel_order`` returns ``cancel_return``."""
    order_client = MagicMock()
    order_client.cancel_order.return_value = cancel_return
    instrument_service = MagicMock()
    instrument_service.resolve_to_wire.return_value = MagicMock(
        security_id="2885",
        wire_segment="NSE_EQ",
    )
    validator = MagicMock()
    validator.validate.return_value = MagicMock(valid=True, errors=())
    return DhanOrderCommandAdapter(
        order_client=order_client,
        instrument_service=instrument_service,
        validator=validator,
    )


class TestCancelOrderStatusCheck:
    """``cancel_order`` must inspect ``status``, not just the presence of ``"data"``."""

    def test_cancel_order_returns_false_on_error_status(self) -> None:
        # Bug: had "data" key, so old check returned True even though status is "error".
        adapter = _build_adapter({"data": {"orderId": "123"}, "status": "error"})
        assert adapter.cancel_order("123") is False

    def test_cancel_order_returns_true_on_success_status(self) -> None:
        adapter = _build_adapter({"data": {"orderId": "123"}, "status": "success"})
        assert adapter.cancel_order("123") is True

    def test_cancel_order_returns_false_on_unexpected_response_type(self) -> None:
        # Non-dict responses (e.g. None on network failure) must not be treated as success.
        adapter = _build_adapter(None)
        assert adapter.cancel_order("123") is False
