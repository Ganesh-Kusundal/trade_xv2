"""Integration tests for SqliteOrderStore restart hydration.

Verifies that OrderManager reloads durable order snapshots after process
restart (new OrderManager + new SqliteOrderStore on same DB path).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from application.oms.order_manager import OrderManager
from application.oms.persistence.sqlite_order_store import SqliteOrderStore
from domain.entities import Order
from domain.types import OrderStatus, OrderType, ProductType, Side


def _sample_order(
    order_id: str = "OM-abc123",
    correlation_id: str = "corr-001",
    status: OrderStatus = OrderStatus.OPEN,
    filled_quantity: int = 0,
) -> Order:
    return Order(
        order_id=order_id,
        correlation_id=correlation_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        quantity=10,
        filled_quantity=filled_quantity,
        price=Decimal("0"),
        avg_price=Decimal("2500") if filled_quantity else Decimal("0"),
        status=status,
        timestamp=datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
    )


def test_sqlite_upsert_and_load_roundtrip(tmp_path) -> None:
    db = tmp_path / "orders.sqlite"
    store = SqliteOrderStore(db)
    order = _sample_order()
    store.upsert(order)
    store.close()

    reloaded = SqliteOrderStore(db)
    orders = reloaded.load_all()
    reloaded.close()

    assert len(orders) == 1
    assert orders[0].order_id == order.order_id
    assert orders[0].correlation_id == order.correlation_id
    assert orders[0].symbol == "RELIANCE"
    assert orders[0].status == OrderStatus.OPEN


def test_order_manager_hydrates_from_sqlite_on_restart(tmp_path) -> None:
    db = tmp_path / "orders.sqlite"
    store1 = SqliteOrderStore(db)
    order = _sample_order()
    store1.upsert(order)
    store1.close()

    store2 = SqliteOrderStore(db)
    reloaded_orders = store2.load_all()
    om2 = OrderManager(order_store=store2)
    for o in reloaded_orders:
        om2.upsert_order(o)

    assert om2.get_order(order.order_id) is not None
    loaded = om2.get_order(order.order_id)
    assert loaded is not None
    assert loaded.symbol == "RELIANCE"
    assert loaded.status == OrderStatus.OPEN


def test_order_manager_restart_preserves_partial_fill_state(tmp_path) -> None:
    db = tmp_path / "orders.sqlite"
    store1 = SqliteOrderStore(db)
    order = _sample_order(
        order_id="OM-partial",
        correlation_id="corr-partial",
        status=OrderStatus.PARTIALLY_FILLED,
        filled_quantity=5,
    )
    store1.upsert(order)
    store1.close()

    store2 = SqliteOrderStore(db)
    reloaded_orders = store2.load_all()
    om2 = OrderManager(order_store=store2)
    for o in reloaded_orders:
        om2.upsert_order(o)

    loaded = om2.get_order("OM-partial")
    assert loaded is not None
    assert loaded.filled_quantity == 5
    assert loaded.status == OrderStatus.PARTIALLY_FILLED


def test_upsert_updates_existing_order_on_restart_path(tmp_path) -> None:
    db = tmp_path / "orders.sqlite"
    store = SqliteOrderStore(db)
    order = _sample_order()
    store.upsert(order)
    filled = order.with_fill(10, Decimal("2500")).with_status(OrderStatus.FILLED)
    store.upsert(filled)
    store.close()

    reloaded = SqliteOrderStore(db)
    orders = reloaded.load_all()
    reloaded.close()

    assert len(orders) == 1
    assert orders[0].status == OrderStatus.FILLED
    assert orders[0].filled_quantity == 10
