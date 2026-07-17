"""R2 / Q1 — daily PnL feed wiring regression test.

Proves that live fills (via TRADE_APPLIED -> PositionManager -> POSITION_UPDATED)
are observed by ``RiskManager.update_daily_pnl``, so the daily loss limit and
rolling loss circuit breaker actually trip on real trading activity.

Before this wiring, ``update_daily_pnl`` had no production callers: the daily
loss limit and loss circuit breaker never saw live fills/MTM.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from domain.entities.order import Order
from domain.entities.trade import Trade
from domain.enums import OrderType, ProductType, Side
from domain.events.types import DomainEvent, EventType

from application.oms import PositionManager, RiskManager, TradingContext
from application.oms._internal.loss_circuit_breaker import LossCircuitBreakerConfig
from application.oms.risk_manager import RiskConfig
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.event_bus.processed_trade_repository import ProcessedTradeRepository


def _make_trade(trade_id: str, side: Side, price: Decimal, qty: int = 10) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id="ORD-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=side,
        quantity=qty,
        price=price,
        timestamp=datetime.now(),
    )


def _publish_trade_applied(bus: EventBus, trade: Trade) -> None:
    bus.publish(
        DomainEvent.now(
            EventType.TRADE_APPLIED.value,
            {"trade": trade},
        )
    )


def _build_context(capital: Decimal, loss_threshold_pct: Decimal, bus: EventBus, processed_trade_repository: ProcessedTradeRepository) -> TradingContext:
    risk_config = RiskConfig(max_daily_loss_pct=loss_threshold_pct)
    loss_cb_config = LossCircuitBreakerConfig(
        loss_threshold_pct=loss_threshold_pct,
        cooldown_seconds=5,
        window_seconds=60,
    )
    risk_manager = RiskManager(
        PositionManager(event_bus=bus),
        risk_config,
        capital_fn=lambda: capital,
        loss_cb_config=loss_cb_config,
    )
    return TradingContext(
        event_bus=bus,
        risk_manager=risk_manager,
        risk_config=risk_config,
        capital_fn=lambda: capital,
        processed_trade_repository=processed_trade_repository,
    )


def test_daily_pnl_observes_live_fills(event_bus, processed_trade_repository):
    """A realized loss from live fills must reach the risk engine."""
    capital = Decimal("1_000_000")
    ctx = _build_context(capital, Decimal("5.0"), event_bus, processed_trade_repository)

    # Opening BUY at 2500, then closing SELL at 2400 -> 100 * 10 = 1000 loss.
    _publish_trade_applied(ctx.event_bus, _make_trade("T1", Side.BUY, Decimal("2500")))
    _publish_trade_applied(ctx.event_bus, _make_trade("T2", Side.SELL, Decimal("2400")))

    # The risk engine must now report the realized loss as daily PnL.
    assert ctx.risk_manager.daily_pnl == Decimal("-1000"), ctx.risk_manager.daily_pnl


def test_loss_circuit_breaker_trips_on_live_loss(event_bus, processed_trade_repository):
    """Once the daily loss exceeds the threshold, orders are blocked (P0)."""
    capital = Decimal("1_000_000")
    # 0.2% threshold -> a 1000 INR loss (0.1%) is below; use a tighter one.
    ctx = _build_context(capital, Decimal("0.05"), event_bus, processed_trade_repository)

    # A single 1000 INR loss is 0.1% of capital -> exceeds 0.05% threshold.
    _publish_trade_applied(ctx.event_bus, _make_trade("T1", Side.BUY, Decimal("2500")))
    _publish_trade_applied(ctx.event_bus, _make_trade("T2", Side.SELL, Decimal("2400")))

    from domain.entities.order import Order

    order = Order(
        order_id="ORD-X",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=Decimal("2400"),
        product_type=ProductType.INTRADAY,
    )
    # order_type/product_type are enums in real usage; the risk manager only
    # reads .value when present, so MagicMock is fine for this gate check.
    result = ctx.risk_manager.check_order(order)
    assert result.allowed is False, "loss circuit breaker must block after live loss"
    assert "loss" in result.reason.lower()
