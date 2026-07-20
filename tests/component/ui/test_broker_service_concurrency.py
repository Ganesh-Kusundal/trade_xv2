"""Concurrency tests for the shared MockBroker (brokers.paper.PaperGateway).

``MockBroker`` is the product's paper gateway (see
``runtime.broker_accessors.get_mock_broker_class``), which requires an
``OrderManager`` to route fills through the OMS spine.  A minimal
``_MockOrderManager`` (mirroring ``tests/unit/brokers/paper/test_paper.py``)
delegates to the submit function so orders fill and ``PaperOrders`` keeps its
positions in sync.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from brokers.paper.paper_gateway import PaperGateway
from domain import Order, Trade


@dataclass
class _MockOrderResult:
    success: bool
    order: Order | None = None
    error: str | None = None


class _MockOrderManager:
    """Minimal OrderManager that delegates to submit_fn (like the real OMS)."""

    def __init__(self) -> None:
        self._orders: list[Order] = []
        self._trades: list[Trade] = []
        self.risk_manager = None

    def place_order(self, *, request, submit_fn) -> _MockOrderResult:
        order = submit_fn(request)
        self._orders.append(order)
        return _MockOrderResult(success=True, order=order)

    def upsert_order(self, order: Order) -> None:
        self._orders.append(order)

    def record_trade(self, trade: Trade) -> None:
        self._trades.append(trade)


def _make_broker() -> PaperGateway:
    """Create a paper gateway with a mock OrderManager for concurrency tests."""
    return PaperGateway(order_manager=_MockOrderManager())


class TestMockBrokerConcurrency:
    def test_concurrent_place_order_generates_unique_ids(self):
        broker = _make_broker()

        def place():
            return broker.place_order("RELIANCE", "NSE", "BUY", 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(100)]
            results = [f.result() for f in as_completed(futures)]

        ids = [o.order_id for o in results]
        assert len(ids) == len(set(ids)), "All order IDs must be unique"
        assert all(o.order_id for o in results), "All order IDs must be non-empty"

    def test_concurrent_place_order_updates_positions(self):
        broker = _make_broker()

        def place():
            return broker.place_order("RELIANCE", "NSE", "BUY", 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(20)]
            for f in as_completed(futures):
                f.result()

        positions = broker.positions()
        reliance_positions = [p for p in positions if p.symbol == "RELIANCE"]
        assert len(reliance_positions) >= 1
        total_qty = sum(p.quantity for p in reliance_positions)
        assert total_qty == 20, f"Expected 20 total quantity, got {total_qty}"

    def test_positions_reflect_fills(self):
        broker = _make_broker()
        broker.place_order("RELIANCE", "NSE", "BUY", 10)
        positions_after_first = broker.positions()
        reliance_1 = [p for p in positions_after_first if p.symbol == "RELIANCE"]
        assert len(reliance_1) >= 1

        broker.place_order("RELIANCE", "NSE", "BUY", 10)
        positions_after_second = broker.positions()
        reliance_2 = [p for p in positions_after_second if p.symbol == "RELIANCE"]
        assert len(reliance_2) >= 1

        qty_1 = sum(p.quantity for p in reliance_1)
        qty_2 = sum(p.quantity for p in reliance_2)
        assert qty_2 > qty_1, "Second fill should increase position quantity"
