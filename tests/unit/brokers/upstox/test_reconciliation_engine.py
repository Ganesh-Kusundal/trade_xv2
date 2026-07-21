"""Upstox reconciliation uses shared ReconciliationEngine."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from brokers.providers.upstox.reconciliation.service import UpstoxReconciliationService
from domain import Position


def test_upstox_uses_shared_engine_for_position_drift() -> None:
    order_client = MagicMock()
    order_client.get_order_list.return_value = []
    portfolio_client = MagicMock()
    portfolio_client.get_short_term_positions.return_value = [{"raw": True}]

    broker_pos = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("2500"))
    with patch(
        "brokers.providers.upstox.reconciliation.service.UpstoxDomainMapper.to_position",
        return_value=broker_pos,
    ):
        svc = UpstoxReconciliationService(order_client, portfolio_client)
        local = [Position(symbol="RELIANCE", exchange="NSE", quantity=5)]
        report = svc.reconcile(local_orders=[], local_positions=local)

    kinds = {item.kind for item in report.drift_items}
    assert "position_quantity_mismatch" in kinds
