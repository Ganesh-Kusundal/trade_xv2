"""Upstox reconciliation must satisfy IReconciliationService reconcile()."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.oms.protocols import IReconciliationService
from brokers.upstox.reconciliation.service import UpstoxReconciliationService


def test_upstox_reconcile_accepts_local_orders_and_positions():
    order_client = MagicMock()
    order_client.get_order_list.return_value = []
    portfolio_client = MagicMock()
    portfolio_client.get_short_term_positions.return_value = []

    svc = UpstoxReconciliationService(order_client, portfolio_client)
    assert isinstance(svc, IReconciliationService)

    report = svc.reconcile(
        local_orders=[{"order_id": "1", "status": "OPEN"}],
        local_positions=[{"exchange_segment": "NSE", "trading_symbol": "RELIANCE", "quantity": 0}],
    )
    assert report is not None
    assert hasattr(report, "drift_items")
