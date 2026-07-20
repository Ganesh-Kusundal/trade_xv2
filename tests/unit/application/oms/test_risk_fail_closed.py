from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from application.oms._internal.risk_manager import RiskManager
from application.oms._internal.risk_types import RiskConfig
from application.oms.capital_provider import FixedCapitalProvider
from application.oms.position_manager import PositionManager
from domain import Order
from domain.enums import OrderStatus
from domain.types import OrderType, ProductType, Side, Validity


def _make_order(symbol: str = "RELIANCE") -> Order:
    return Order(
        order_id="test-1",
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=2500.0,
        trigger_price=0.0,
        product_type=ProductType.CNC,
        validity=Validity.DAY,
        status=OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
    )


def test_instrument_lookup_failure_skips_check():
    """When instrument provider raises, risk must skip the tick check (not
    deny/crash). A transient lookup error must not reject every order."""
    provider = MagicMock()
    provider.resolve.side_effect = ValueError("Instrument not found")

    position_manager = PositionManager()
    capital = FixedCapitalProvider(Decimal("1000000"))

    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("100"),
        enable_margin_check=False,
    )

    risk = RiskManager(
        position_manager=position_manager,
        config=config,
        capital_provider=capital,
        instrument_provider=provider,
    )

    result = risk.check_order(_make_order())
    assert result.allowed is True


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
