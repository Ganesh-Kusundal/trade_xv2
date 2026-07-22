"""FeeCalculator: known Indian equity STT / brokerage numbers."""

from decimal import Decimal

from domain.enums import OrderSide
from domain.services.fee_calculator import FeeCalculator, FeeBreakdown


def test_delivery_buy_stt() -> None:
    # STT delivery buy = 0% (STT only on sell side)
    fees = FeeCalculator.equity_delivery(
        side=OrderSide.BUY,
        price=Decimal("2500"),
        quantity=Decimal("10"),
    )
    assert fees.stt == Decimal("0")
    assert isinstance(fees, FeeBreakdown)


def test_delivery_sell_stt() -> None:
    fees = FeeCalculator.equity_delivery(
        side=OrderSide.SELL,
        price=Decimal("2500"),
        quantity=Decimal("10"),
    )
    assert fees.stt == Decimal("25.00")


def test_intraday_buy_stt_zero() -> None:
    fees = FeeCalculator.equity_intraday(
        side=OrderSide.BUY,
        price=Decimal("2500"),
        quantity=Decimal("10"),
    )
    assert fees.stt == Decimal("0")


def test_intraday_sell_stt() -> None:
    # STT intraday sell = 0.025% of turnover → 25000 * 0.00025 = 6.25
    fees = FeeCalculator.equity_intraday(
        side=OrderSide.SELL,
        price=Decimal("2500"),
        quantity=Decimal("10"),
    )
    assert fees.stt == Decimal("6.25")


def test_brokerage_simple_rate() -> None:
    # brokerage 0.03% of turnover, capped conceptually — simple uncapped rate
    # 25000 * 0.0003 = 7.50
    fees = FeeCalculator.equity_delivery(
        side=OrderSide.BUY,
        price=Decimal("2500"),
        quantity=Decimal("10"),
    )
    assert fees.brokerage == Decimal("7.50")
    assert fees.total == fees.stt + fees.brokerage + fees.exchange + fees.gst
