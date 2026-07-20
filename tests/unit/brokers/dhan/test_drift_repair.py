"""Tests for M3: drift-aware repair in DhanReconciliationService._repair_local_oms.

Verifies that repair only touches drifted items, not the full broker snapshot.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.dhan.portfolio.reconciliation import DhanReconciliationService
from domain import DriftItem


class _FakeOrder:
    def __init__(self, order_id: str, symbol: str = "RELIANCE", status: str = "OPEN"):
        self.order_id = order_id
        self.symbol = symbol
        self.status = status


class _FakePosition:
    def __init__(self, symbol: str, exchange: str = "NSE", quantity: int = 10):
        self.symbol = symbol
        self.exchange = exchange
        self.quantity = quantity
        self.avg_price = 100
        self.ltp = 100


class _FakeOms:
    def __init__(self):
        self.upserted_orders = []
        self.upserted_positions = []
        self.existing_orders = {}

    def upsert_order(self, order):
        self.upserted_orders.append(order)

    def upsert_position(self, data):
        self.upserted_positions.append(data)

    def get_order(self, order_id):
        return self.existing_orders.get(order_id)


class TestDriftRepair:
    """M3: _repair_local_oms only touches drift items, not full snapshot."""

    def _make_service(self, oms=None, auto_repair=True):
        orders = MagicMock()
        portfolio = MagicMock()
        return DhanReconciliationService(
            orders=orders,
            portfolio=portfolio,
            oms=oms or _FakeOms(),
            auto_repair=auto_repair,
        )

    def test_repair_only_drifted_orders(self):
        """When 5 broker orders exist but only 1 has drift, only 1 is repaired."""
        oms = _FakeOms()
        svc = self._make_service(oms=oms)

        broker_orders = [
            _FakeOrder("O1"),
            _FakeOrder("O2"),
            _FakeOrder("O3"),
            _FakeOrder("O4"),
            _FakeOrder("O5"),
        ]
        broker_positions = []

        # Only O3 has a drift item
        drift = [
            DriftItem(
                kind="missing_local_order",
                severity="HIGH",
                symbol="RELIANCE",
                details="Broker order O3 not present in local OMS",
                payload={"order_id": "O3", "symbol": "RELIANCE"},
            )
        ]

        repaired_o, repaired_p = svc._repair_local_oms(broker_orders, broker_positions, drift)

        assert repaired_o == 1
        assert len(oms.upserted_orders) == 1
        assert oms.upserted_orders[0].order_id == "O3"

    def test_no_repair_when_no_drift(self):
        """Empty drift list → no mutations."""
        oms = _FakeOms()
        svc = self._make_service(oms=oms)

        broker_orders = [_FakeOrder("O1"), _FakeOrder("O2")]
        broker_positions = [_FakePosition("RELIANCE")]

        repaired_o, repaired_p = svc._repair_local_oms(broker_orders, broker_positions, [])

        assert repaired_o == 0
        assert repaired_p == 0
        assert len(oms.upserted_orders) == 0
        assert len(oms.upserted_positions) == 0

    def test_repair_position_drift(self):
        """Position drift items are repaired."""
        oms = _FakeOms()
        svc = self._make_service(oms=oms)

        broker_orders = []
        broker_positions = [_FakePosition("RELIANCE", quantity=20)]

        drift = [
            DriftItem(
                kind="position_quantity_mismatch",
                severity="HIGH",
                symbol="RELIANCE",
                details="Position RELIANCE: local_qty=10, broker_qty=20",
                payload={"symbol": "RELIANCE", "exchange": "NSE"},
            )
        ]

        repaired_o, repaired_p = svc._repair_local_oms(broker_orders, broker_positions, drift)

        assert repaired_p == 1
        assert len(oms.upserted_positions) == 1
        assert oms.upserted_positions[0]["symbol"] == "RELIANCE"
        assert oms.upserted_positions[0]["quantity"] == 20

    def test_repair_status_mismatch(self):
        """Order status mismatch drift is repaired."""
        oms = _FakeOms()
        svc = self._make_service(oms=oms)

        broker_orders = [_FakeOrder("O1", status="FILLED")]
        broker_positions = []

        drift = [
            DriftItem(
                kind="order_status_mismatch",
                severity="MEDIUM",
                symbol="RELIANCE",
                details="Order O1: local=OPEN, broker=FILLED",
                payload={"order_id": "O1", "symbol": "RELIANCE"},
            )
        ]

        repaired_o, repaired_p = svc._repair_local_oms(broker_orders, broker_positions, drift)

        assert repaired_o == 1
        assert oms.upserted_orders[0].status == "FILLED"
