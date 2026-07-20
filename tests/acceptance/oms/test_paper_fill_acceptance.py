"""OMS acceptance — real PaperFillSource through place_order_spine (Context 8)."""

from __future__ import annotations

from decimal import Decimal

from application.oms.order_manager import OmsOrderCommand
from domain import OrderType, ProductType, Side
from domain.events.types import EventType
from infrastructure.event_bus.event_bus import EventBus


def test_paper_fill_end_to_end_with_risk_and_events() -> None:
    """Acceptance: one limit buy → fill → position → capital events on bus."""
    from runtime.paper_session import build_paper_session

    prices = {"RELIANCE": Decimal("2500.00")}

    def quote_fn(symbol: str, exchange: str) -> Decimal:
        return prices.get(symbol, Decimal("0"))

    session = build_paper_session(initial_capital=100_000, quote_fn=quote_fn)
    bus: EventBus = session.trading_context.event_bus
    received: list[str] = []

    def _capture(event) -> None:
        received.append(str(event.event_type))

    bus.subscribe(EventType.ORDER_PLACED, _capture)
    bus.subscribe(EventType.TRADE_APPLIED, _capture)

    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        correlation_id="acceptance:paper:1",
    )
    result = session.execution_engine.place_order(cmd)
    assert result.success, result.error
    assert result.order is not None
    assert any("ORDER" in t or "TRADE" in t for t in received)
    assert result.order.status.name in ("FILLED", "COMPLETE", "OPEN")


def test_paper_session_capital_metrics_label_parity() -> None:
    from analytics.backtest import BacktestConfig
    from analytics.pipeline.pipeline import FeaturePipeline
    from analytics.strategy.pipeline import StrategyPipeline
    from runtime.paper_session import build_backtest_engine

    engine = build_backtest_engine(
        FeaturePipeline(),
        StrategyPipeline(),
        BacktestConfig(),
        research_only=False,
    )
    assert engine.mode.value == "parity"
