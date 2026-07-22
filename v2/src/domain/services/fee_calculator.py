"""Indian equity fee calculator — pure Decimal math, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from domain.enums import OrderSide

# Indian market fee rates (equity cash segment)
_STT_DELIVERY_SELL = Decimal("0.001")  # 0.1% on delivery sell only
_STT_INTRADAY_SELL = Decimal("0.00025")  # 0.025% on intraday sell only
_BROKERAGE_RATE = Decimal("0.0003")  # 0.03%
_BROKERAGE_CAP = Decimal("20")  # Rs 20 per order cap
_EXCHANGE_RATE = Decimal("0.0000345")  # 0.00345% NSE txn charges
_GST_RATE = Decimal("0.18")  # 18% on (brokerage + exchange)


def _q2(value: Decimal) -> Decimal:
    """Quantize to 2 decimal places (paisa precision)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class FeeBreakdown:
    stt: Decimal
    brokerage: Decimal
    exchange: Decimal
    gst: Decimal

    @property
    def total(self) -> Decimal:
        return self.stt + self.brokerage + self.exchange + self.gst


class FeeCalculator:
    """STT + brokerage + exchange + GST for Indian equities."""

    @staticmethod
    def equity_delivery(
        *,
        side: OrderSide,
        price: Decimal,
        quantity: Decimal,
    ) -> FeeBreakdown:
        turnover = price * quantity
        stt = (
            Decimal("0")
            if side is OrderSide.BUY
            else _q2(turnover * _STT_DELIVERY_SELL)
        )
        return FeeCalculator._common(turnover, stt)

    @staticmethod
    def equity_intraday(
        *,
        side: OrderSide,
        price: Decimal,
        quantity: Decimal,
    ) -> FeeBreakdown:
        turnover = price * quantity
        stt = (
            Decimal("0")
            if side is OrderSide.BUY
            else _q2(turnover * _STT_INTRADAY_SELL)
        )
        return FeeCalculator._common(turnover, stt)

    @staticmethod
    def _common(turnover: Decimal, stt: Decimal) -> FeeBreakdown:
        brokerage_raw = turnover * _BROKERAGE_RATE
        brokerage = _q2(min(brokerage_raw, _BROKERAGE_CAP))
        exchange = _q2(turnover * _EXCHANGE_RATE)
        gst = _q2((brokerage + exchange) * _GST_RATE)
        return FeeBreakdown(stt=stt, brokerage=brokerage, exchange=exchange, gst=gst)
