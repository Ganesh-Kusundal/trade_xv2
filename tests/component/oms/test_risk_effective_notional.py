"""C0.1 — RiskManager rejects MARKET with no ref price; sizes with LTP/multiplier."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms._internal.risk_manager import RiskConfig, RiskManager
from application.oms.position_manager import PositionManager
from domain.entities import Order
from domain.entities.position import Position
from domain.types import OrderType, Side


@pytest.fixture
def pm() -> PositionManager:
    return PositionManager()


@pytest.fixture
def rm(pm: PositionManager) -> RiskManager:
    return RiskManager(
        pm,
        RiskConfig(
            max_position_pct=Decimal("10"),
            max_gross_exposure_pct=Decimal("50"),
            enable_margin_check=False,
        ),
        capital_fn=lambda: Decimal("100000"),
    )


def _order(
    *,
    qty: int = 100,
    price: Decimal = Decimal("0"),
    order_type: OrderType = OrderType.MARKET,
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
) -> Order:
    return Order(
        order_id="o1",
        symbol=symbol,
        exchange=exchange,
        side=Side.BUY,
        order_type=order_type,
        quantity=qty,
        price=price,
    )


@pytest.mark.unit
def test_market_order_without_ref_price_rejected(rm: RiskManager) -> None:
    result = rm.check_order(_order(price=Decimal("0")))
    assert result.allowed is False
    assert (
        "ref price" in (result.reason or "").lower() or "no limit" in (result.reason or "").lower()
    )


@pytest.mark.unit
def test_market_order_uses_position_ltp(pm: PositionManager, rm: RiskManager) -> None:
    # Seed position with LTP so MARKET can be sized
    pm._positions["RELIANCE:NSE"] = Position(
        symbol="RELIANCE",
        exchange="NSE",
        quantity=0,
        avg_price=Decimal("0"),
        ltp=Decimal("2500"),
    )
    # 100 * 2500 = 250_000 on 100k capital → 250% position → reject if max 10%
    result = rm.check_order(_order(qty=100, price=Decimal("0")))
    assert result.allowed is False
    assert "position" in (result.reason or "").lower() or "gross" in (result.reason or "").lower()


@pytest.mark.unit
def test_limit_order_notional_blocks_large_size(rm: RiskManager) -> None:
    # 50 * 3000 = 150_000 > 10% of 100_000
    result = rm.check_order(_order(qty=50, price=Decimal("3000"), order_type=OrderType.LIMIT))
    assert result.allowed is False


@pytest.mark.unit
def test_small_limit_order_allowed(rm: RiskManager) -> None:
    # 1 * 1000 = 1000 = 1% of capital
    result = rm.check_order(_order(qty=1, price=Decimal("1000"), order_type=OrderType.LIMIT))
    assert result.allowed is True


@pytest.mark.unit
def test_multiplier_inflates_notional(pm: PositionManager) -> None:
    class _Inst:
        multiplier = Decimal("50")
        tick_size = Decimal("0.05")
        ltp = Decimal("100")

    class _Provider:
        def resolve(self, symbol: str, exchange: str):
            return _Inst()

    rm = RiskManager(
        pm,
        RiskConfig(
            max_position_pct=Decimal("10"),
            max_gross_exposure_pct=Decimal("50"),
            enable_margin_check=False,
        ),
        capital_fn=lambda: Decimal("100000"),
        instrument_provider=_Provider(),
    )
    # qty 3 * price 100 * mult 50 = 15_000 = 15% > 10%
    result = rm.check_order(
        Order(
            order_id="o2",
            symbol="NIFTY",
            exchange="NFO",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=3,
            price=Decimal("100"),
        )
    )
    assert result.allowed is False
