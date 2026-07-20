"""Tests for unified ExecutionEngine."""

from unittest.mock import MagicMock

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_source import BrokerFillSource, SimulatedFillSource
from application.oms.order_manager import OmsOrderCommand
from domain.enums import OrderType, ProductType, Side


def _make_command() -> OmsOrderCommand:
    return OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=2500.0,
        product_type=ProductType.CNC,
        correlation_id="test-corr-1",
    )


def _make_trading_context():
    ctx = MagicMock()
    ctx.order_manager = MagicMock()
    ctx.order_manager.place_order.return_value = MagicMock(success=True)
    return ctx


def test_broker_fill_source_creates_submit_fn():
    gateway = MagicMock()
    fill_source = BrokerFillSource(gateway)
    fn = fill_source.submit_fn()
    assert callable(fn)


def test_simulated_fill_source_creates_submit_fn():
    fill_source = SimulatedFillSource(order_id_prefix="test")
    fn = fill_source.submit_fn()
    assert callable(fn)


def test_execution_engine_place_order_delegates_to_oms():
    ctx = _make_trading_context()
    fill_source = MagicMock()
    fill_source.submit_fn.return_value = lambda cmd: MagicMock()

    engine = ExecutionEngine(fill_source=fill_source, trading_context=ctx)
    result = engine.place_order(_make_command())

    ctx.order_manager.place_order.assert_called_once()
    assert result.success


def test_execution_engine_uses_fill_source_submit_fn():
    ctx = _make_trading_context()

    def sentinel_fn(cmd):
        return MagicMock()

    fill_source = MagicMock()
    fill_source.submit_fn.return_value = sentinel_fn

    engine = ExecutionEngine(fill_source=fill_source, trading_context=ctx)
    engine.place_order(_make_command())

    fill_source.submit_fn.assert_called_once()
    call_kwargs = ctx.order_manager.place_order.call_args
    assert (
        call_kwargs.kwargs.get("submit_fn") is sentinel_fn
        or call_kwargs[1].get("submit_fn") is sentinel_fn
    )


def test_both_fill_sources_satisfy_protocol():
    """Both BrokerFillSource and SimulatedFillSource satisfy FillSource protocol."""
    from application.execution.fill_source import FillSource

    broker = BrokerFillSource(MagicMock())
    sim = SimulatedFillSource()

    assert isinstance(broker, FillSource)
    assert isinstance(sim, FillSource)
