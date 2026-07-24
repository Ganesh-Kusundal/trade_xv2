"""Contract tests for OrderStore protocol implementations.

These tests verify that all OrderStore implementations conform to the
OrderStore protocol defined in application.execution.protocols.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from application.execution.order_store import InMemoryOrderStore
from application.execution.protocols import OrderStore
from application.oms.trading_cache import TradingCache
from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


def _make_command(
    cid: CorrelationId | None = None,
    qty: str = "10",
    price: str = "2500",
) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal(price)),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid or CorrelationId(value=uuid4()),
    )


def _make_order(cid: CorrelationId | None = None, order_id: str = "test-1") -> Order:
    """Create a basic order for testing."""
    cid = cid or CorrelationId(value=uuid4())
    return Order(
        order_id=OrderId(value=order_id),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        status=OrderStatus.PENDING,
        correlation_id=cid,
    )


class _TradingCacheStore:
    """Adapter from TradingCache to OrderStore (copied from execution_engine for testing)."""

    def __init__(self, cache: TradingCache) -> None:
        self._cache = cache
        self._by_corr: dict[str, Order] = {}

    def upsert(self, order: Order) -> None:
        self._cache.set_order(order)
        self._by_corr[str(order.correlation_id.value)] = order

    def get(self, order_id: OrderId) -> Order | None:
        return self._cache.get_order(order_id)

    def get_by_correlation(self, correlation_id: CorrelationId) -> Order | None:
        return self._by_corr.get(str(correlation_id.value))

    def all_orders(self) -> list[Order]:
        snap = self._cache.snapshot()
        return list(snap.get("orders", {}).values())


class _TestOrderStoreProtocol:
    """Protocol contract tests - each implementation must pass these."""

    @pytest.fixture
    def order_store(self) -> OrderStore:
        raise NotImplementedError

    def test_upsert_and_get_by_id(self, order_store: OrderStore) -> None:
        order = _make_order(order_id="test-order-1")
        order_store.upsert(order)

        retrieved = order_store.get(OrderId(value="test-order-1"))
        assert retrieved is not None
        assert retrieved.order_id.value == "test-order-1"
        assert retrieved.instrument_id == order.instrument_id
        assert retrieved.side == order.side
        assert retrieved.quantity == order.quantity

    def test_get_returns_none_for_missing_order(self, order_store: OrderStore) -> None:
        result = order_store.get(OrderId(value="non-existent"))
        assert result is None

    def test_upsert_and_get_by_correlation(self, order_store: OrderStore) -> None:
        cid = CorrelationId(value=uuid4())
        order = _make_order(cid=cid, order_id="corr-order-1")
        order_store.upsert(order)

        retrieved = order_store.get_by_correlation(cid)
        assert retrieved is not None
        assert retrieved.correlation_id == cid
        assert retrieved.order_id.value == "corr-order-1"

    def test_get_by_correlation_returns_none_for_missing(self, order_store: OrderStore) -> None:
        cid = CorrelationId(value=uuid4())
        result = order_store.get_by_correlation(cid)
        assert result is None

    def test_all_orders_returns_all_upserted(self, order_store: OrderStore) -> None:
        o1 = _make_order(order_id="order-1")
        o2 = _make_order(order_id="order-2")
        o3 = _make_order(order_id="order-3")

        order_store.upsert(o1)
        order_store.upsert(o2)
        order_store.upsert(o3)

        all_orders = order_store.all_orders()
        assert len(all_orders) == 3
        ids = {o.order_id.value for o in all_orders}
        assert ids == {"order-1", "order-2", "order-3"}

    def test_upsert_updates_existing_order(self, order_store: OrderStore) -> None:
        """Upsert with same order_id should update the stored order."""
        order1 = _make_order(order_id="update-test")
        order_store.upsert(order1)

        # Create updated order with same ID but different status
        updated = order1.transition_to(OrderStatus.SUBMITTED)
        order_store.upsert(updated)

        retrieved = order_store.get(OrderId(value="update-test"))
        assert retrieved is not None
        assert retrieved.status is OrderStatus.SUBMITTED

    def test_upsert_updates_correlation_index(self, order_store: OrderStore) -> None:
        """Upsert with same correlation_id should update correlation index."""
        cid = CorrelationId(value=uuid4())
        order1 = _make_order(cid=cid, order_id="corr-update-1")
        order_store.upsert(order1)

        order2 = _make_order(cid=cid, order_id="corr-update-2")
        order_store.upsert(order2)

        # Correlation index should point to the latest order
        retrieved = order_store.get_by_correlation(cid)
        assert retrieved is not None
        assert retrieved.order_id.value == "corr-update-2"

    def test_is_runtime_checkable_protocol(self, order_store: OrderStore) -> None:
        assert isinstance(order_store, OrderStore)


class TestInMemoryOrderStoreContract(_TestOrderStoreProtocol):
    @pytest.fixture
    def order_store(self) -> OrderStore:
        return InMemoryOrderStore()


class TestTradingCacheStoreContract(_TestOrderStoreProtocol):
    @pytest.fixture
    def order_store(self) -> OrderStore:
        cache = TradingCache()
        return _TradingCacheStore(cache)


class TestOrderStoreProtocolCompliance:
    """Verify all implementations are runtime-checkable OrderStore protocols."""

    def test_inmemory_is_runtime_checkable(self) -> None:
        store = InMemoryOrderStore()
        assert isinstance(store, OrderStore)

    def test_trading_cache_store_is_runtime_checkable(self) -> None:
        cache = TradingCache()
        store = _TradingCacheStore(cache)
        assert isinstance(store, OrderStore)