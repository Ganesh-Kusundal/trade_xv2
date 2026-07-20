"""OrderRequest algo-exec fields + SliceOrderRequest consumer path."""

from __future__ import annotations

from decimal import Decimal

from domain.enums import OrderType, ProductType, Side
from domain.orders.execution_plan import SlicingAlgo, SlicingPlan
from domain.orders.placement import plan_to_order_requests, slice_order_request
from domain.orders.requests import OrderRequest, SliceOrderRequest, expand_slice_request


def test_order_request_carries_algo_fields():
    req = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=10,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        slicing_algo="TWAP",
        slice_count=4,
        slice_interval=30,
        twap_duration=120,
        vwap_participation_rate=Decimal("0.1"),
        disclosed_quantity=2,
    )
    assert req.slicing_algo == "TWAP"
    assert req.slice_count == 4
    assert req.slice_interval == 30
    assert req.twap_duration == 120
    assert req.vwap_participation_rate == Decimal("0.1")
    assert req.disclosed_quantity == 2


def test_expand_slice_request_splits_into_twap_children():
    req = SliceOrderRequest(
        symbol="RELIANCE", exchange="NSE", side=Side.BUY, quantity=10, order_type=OrderType.MARKET
    )
    children = expand_slice_request(req, slice_count=4)
    assert len(children) == 4
    assert sum(c.quantity for c in children) == 10
    assert all(c.slicing_algo == "TWAP" and c.slice for c in children)
    assert all(c.correlation_id is None or ":slice" not in c.correlation_id for c in children)


def test_expand_slice_request_iceberg_uses_disclosed_qty():
    req = SliceOrderRequest(symbol="X", exchange="NSE", side=Side.SELL, quantity=10)
    children = expand_slice_request(req, slice_count=4, disclosed_qty=3)
    # 10 -> 3,3,3,1
    assert [c.quantity for c in children] == [3, 3, 3, 1]
    assert all(c.slicing_algo == "ICEBERG" for c in children)
    assert all(c.disclosed_quantity == 3 for c in children)


def test_slice_order_request_consumer_via_placement():
    req = SliceOrderRequest(symbol="X", exchange="NSE", side=Side.BUY, quantity=9)
    plan = SlicingPlan(algo=SlicingAlgo.TWAP, slice_count=3)
    children = slice_order_request(req, plan)
    assert [c.quantity for c in children] == [3, 3, 3]


def test_plan_to_order_requests_carries_slicing():
    from domain.models.trading import SignalDTO
    from domain.orders.execution_plan import ExecutionPlan, PlanContext

    signal = SignalDTO(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        signal_type="BUY",
        confidence=Decimal("0.9"),
        quantity=8,
        entry_price=Decimal("100"),
    )
    ctx = PlanContext(
        equity=Decimal("100000"),
        default_exchange="NSE",
        slicing=SlicingPlan(algo=SlicingAlgo.VWAP, slice_count=2),
    )
    plan = ExecutionPlan.from_signal(signal, ctx)
    requests = plan_to_order_requests(plan)
    assert len(requests) == 1
    assert requests[0].slicing_algo == "VWAP"
    assert requests[0].slice_count == 2
    assert requests[0].quantity == 8
