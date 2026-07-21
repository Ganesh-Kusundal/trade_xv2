"""cancel_all_orders: per-order success/failure parsing from broker response."""

from __future__ import annotations

import pytest

from brokers.providers.dhan.execution.order_cancellation import OrderCanceller


def _canceller(client, *, allow_live: bool = True) -> OrderCanceller:
    return OrderCanceller(client=client, allow_live_orders=allow_live)


class _FakeClient:
    def __init__(self, response):
        self._response = response

    def delete(self, endpoint, json=None):
        return self._response


class TestCancelAllPerOrderStatus:
    """Each item's ``status`` field drives its bool in the result list."""

    def test_successful_items_marked_true(self):
        """Items with status='success' return (id, True)."""
        client = _FakeClient({
            "data": [
                {"orderId": "100", "status": "success"},
                {"orderId": "101", "status": "success"},
            ],
        })
        result = _canceller(client).cancel_all_orders()
        assert result == [("100", True), ("101", True)]

    def test_failed_items_marked_false(self):
        """Items with a non-success status return (id, False)."""
        client = _FakeClient({
            "data": [
                {"orderId": "200", "status": "success"},
                {"orderId": "201", "status": "failed"},
                {"orderId": "202", "status": "rejected"},
            ],
        })
        result = _canceller(client).cancel_all_orders()
        assert result == [("200", True), ("201", False), ("202", False)]

    def test_missing_status_defaults_to_false(self):
        """Items without a ``status`` key are treated as failures."""
        client = _FakeClient({
            "data": [
                {"orderId": "300"},
                {"orderId": "301", "status": "success"},
            ],
        })
        result = _canceller(client).cancel_all_orders()
        assert result == [("300", False), ("301", True)]

    def test_ok_status_counts_as_success(self):
        """Dhan sometimes returns 'ok' instead of 'success'."""
        client = _FakeClient({
            "data": [
                {"orderId": "400", "status": "ok"},
                {"orderId": "401", "status": "OK"},
            ],
        })
        result = _canceller(client).cancel_all_orders()
        assert result == [("400", True), ("401", True)]

    def test_mixed_success_and_failure(self):
        """Realistic mixed batch: some succeed, some fail."""
        client = _FakeClient({
            "status": "success",
            "data": [
                {"orderId": "500", "status": "success"},
                {"orderId": "501", "status": "failed", "errorCode": "E101", "errorMessage": "Order not found"},
                {"orderId": "502", "status": "success"},
                {"orderId": "503", "status": "cancelled"},
            ],
        })
        result = _canceller(client).cancel_all_orders()
        assert result == [
            ("500", True),
            ("501", False),
            ("502", True),
            ("503", False),
        ]

    def test_empty_data_returns_empty_list(self):
        """Empty data list yields an empty result."""
        client = _FakeClient({"data": []})
        assert _canceller(client).cancel_all_orders() == []

    def test_guard_rejects_when_live_orders_disabled(self):
        """cancel_all_orders raises when allow_live_orders is False."""
        client = _FakeClient({"data": []})
        with pytest.raises(Exception, match="Live orders are disabled"):
            _canceller(client, allow_live=False).cancel_all_orders()
