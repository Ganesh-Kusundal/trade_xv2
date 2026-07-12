import pytest
from unittest.mock import MagicMock
from decimal import Decimal

from domain import Order
from domain.enums import OrderStatus
from domain.types import Side, OrderType, ProductType, Validity
from application.oms._internal.risk_manager import RiskManager
from application.oms._internal.risk_types import RiskConfig, RiskResult
from application.oms.position_manager import PositionManager
from datetime import datetime, timezone


def _make_order(symbol: str = "RELIANCE") -> Order:
    return Order(
        order_id="test-1", symbol=symbol, exchange="NSE",
        side=Side.BUY, order_type=OrderType.LIMIT, quantity=10,
        price=2500.0, trigger_price=0.0, product_type=ProductType.CNC,
        validity=Validity.DAY, status=OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
    )


def test_instrument_lookup_failure_denies_order():
    """When instrument provider raises, risk must deny the order (fail-closed)."""
    provider = MagicMock()
    provider.resolve.side_effect = ValueError("Instrument not found")

    position_manager = MagicMock(spec=PositionManager)
    position_manager.get_position.return_value = None
    position_manager.get_positions.return_value = []

    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("100"),
        enable_margin_check=False,
    )

    risk = RiskManager(
        position_manager=position_manager,
        config=config,
        instrument_provider=provider,
    )

    result = risk.check_order(_make_order())
    assert not result.allowed
    assert "instrument" in (result.reason or "").lower() or "lookup" in (result.reason or "").lower() or "resolve" in (result.reason or "").lower()


def test_instrument_lookup_success_continues_to_tick_check():
    """When instrument provider succeeds with a tick size, misaligned prices are denied."""
    instrument = MagicMock()
    instrument.tick_size = Decimal("0.05")

    provider = MagicMock()
    provider.resolve.return_value = instrument

    position_manager = MagicMock(spec=PositionManager)
    position_manager.get_position.return_value = None
    position_manager.get_positions.return_value = []

    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("100"),
        enable_margin_check=False,
    )

    risk = RiskManager(
        position_manager=position_manager,
        config=config,
        instrument_provider=provider,
    )

    order = _make_order()
    order = order.with_price(Decimal("2500.03"))
    result = risk.check_order(order)
    assert not result.allowed
    assert "tick" in (result.reason or "").lower()
