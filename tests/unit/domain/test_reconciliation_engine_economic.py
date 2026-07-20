"""Economic-field reconciliation — fill quantity and average price drift."""

from __future__ import annotations

from decimal import Decimal

from domain.entities import Position
from domain.reconciliation_engine import ReconciliationEngine
from domain.types import OrderStatus
from tests.fixtures.domain_helpers import make_order


def _make_order(**overrides):
    defaults = {
        "order_id": "ORD-001",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 10,
        "filled_quantity": 0,
        "status": OrderStatus.OPEN,
        "product_type": "INTRADAY",
        "validity": "DAY",
    }
    defaults.update(overrides)
    return make_order(**defaults)


def _make_position(**overrides) -> Position:
    defaults = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "quantity": 10,
        "avg_price": Decimal("2500"),
    }
    defaults.update(overrides)
    return Position(**defaults)


def test_compare_orders_detects_fill_quantity_mismatch():
    engine = ReconciliationEngine()
    local = [_make_order(filled_quantity=5, status=OrderStatus.PARTIALLY_FILLED)]
    broker = [_make_order(filled_quantity=8, status=OrderStatus.PARTIALLY_FILLED)]

    drift = engine.compare_orders(local, broker)

    assert len(drift) == 1
    assert drift[0].kind == "fill_quantity_mismatch"
    assert drift[0].severity == "HIGH"
    assert drift[0].payload["local_filled"] == 5
    assert drift[0].payload["broker_filled"] == 8


def test_compare_orders_detects_avg_price_mismatch_when_filled():
    engine = ReconciliationEngine()
    local = [
        _make_order(
            filled_quantity=10,
            avg_price=Decimal("2500.00"),
            status=OrderStatus.FILLED,
        )
    ]
    broker = [
        _make_order(
            filled_quantity=10,
            avg_price=Decimal("2505.00"),
            status=OrderStatus.FILLED,
        )
    ]

    drift = engine.compare_orders(local, broker)

    assert len(drift) == 1
    assert drift[0].kind == "avg_price_mismatch"
    assert drift[0].severity == "HIGH"


def test_compare_orders_ignores_avg_price_within_tolerance():
    engine = ReconciliationEngine()
    base = {
        "filled_quantity": 10,
        "status": OrderStatus.FILLED,
    }
    local = [_make_order(**base, avg_price=Decimal("2500.00"))]
    broker = [_make_order(**base, avg_price=Decimal("2500.005"))]

    drift = engine.compare_orders(local, broker)

    assert drift == []


def test_compare_positions_detects_avg_price_mismatch_when_qty_matches():
    engine = ReconciliationEngine()
    local = [_make_position(quantity=10, avg_price=Decimal("2500.00"))]
    broker = [_make_position(quantity=10, avg_price=Decimal("2510.00"))]

    drift = engine.compare_positions(local, broker)

    assert len(drift) == 1
    assert drift[0].kind == "position_avg_price_mismatch"
    assert drift[0].severity == "HIGH"
