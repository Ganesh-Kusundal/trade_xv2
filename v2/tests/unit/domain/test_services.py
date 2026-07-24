"""Domain services: FeeCalculator, PricingService, InstrumentRegistry."""

from decimal import Decimal

import pytest

from domain.enums import (
    AssetClass,
    ExchangeId,
    InstrumentType,
    OrderSide,
)
from domain.entities import Instrument
from domain.services.fee_calculator import FeeCalculator
from domain.services.instrument_registry import InstrumentRegistry
from domain.services.pricing import PricingService
from domain.value_objects import InstrumentId


# ---------------------------------------------------------------------------
# FeeCalculator — Indian equity delivery
# ---------------------------------------------------------------------------

class TestDeliveryFees:
    def test_delivery_buy_stt_is_zero(self) -> None:
        """STT on delivery BUY is 0%."""
        fees = FeeCalculator.equity_delivery(
            side=OrderSide.BUY,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        assert fees.stt == Decimal("0")

    def test_delivery_sell_stt_is_01_percent(self) -> None:
        """STT on delivery SELL is 0.1% of turnover."""
        # turnover = 2500 * 10 = 25000 → STT = 25.00
        fees = FeeCalculator.equity_delivery(
            side=OrderSide.SELL,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        assert fees.stt == Decimal("25.00")

    def test_delivery_brokerage_rate(self) -> None:
        """Brokerage is 0.03% of turnover (below Rs 20 cap)."""
        # 25000 * 0.0003 = 7.50
        fees = FeeCalculator.equity_delivery(
            side=OrderSide.BUY,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        assert fees.brokerage == Decimal("7.50")

    def test_delivery_brokerage_cap_at_20(self) -> None:
        """Brokerage capped at Rs 20 per order."""
        # turnover = 100000 → 0.03% = 30 → capped to 20
        fees = FeeCalculator.equity_delivery(
            side=OrderSide.BUY,
            price=Decimal("1000"),
            quantity=Decimal("100"),
        )
        assert fees.brokerage == Decimal("20.00")


# ---------------------------------------------------------------------------
# FeeCalculator — Indian equity intraday
# ---------------------------------------------------------------------------

class TestIntradayFees:
    def test_intraday_buy_stt_is_zero(self) -> None:
        """STT on intraday BUY is 0%."""
        fees = FeeCalculator.equity_intraday(
            side=OrderSide.BUY,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        assert fees.stt == Decimal("0")

    def test_intraday_sell_stt_is_0025_percent(self) -> None:
        """STT on intraday SELL is 0.025% of turnover."""
        # turnover = 25000 → STT = 6.25
        fees = FeeCalculator.equity_intraday(
            side=OrderSide.SELL,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        assert fees.stt == Decimal("6.25")


# ---------------------------------------------------------------------------
# FeeCalculator — total fee calculation
# ---------------------------------------------------------------------------

class TestTotalFees:
    def test_total_is_sum_of_components(self) -> None:
        fees = FeeCalculator.equity_delivery(
            side=OrderSide.SELL,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        assert fees.total == fees.stt + fees.brokerage + fees.exchange + fees.gst

    def test_gst_is_18_percent_on_brokerage_plus_exchange(self) -> None:
        """GST = 18% on (brokerage + exchange charges)."""
        fees = FeeCalculator.equity_delivery(
            side=OrderSide.SELL,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        expected_gst = ((fees.brokerage + fees.exchange) * Decimal("0.18")).quantize(
            Decimal("0.01")
        )
        assert fees.gst == expected_gst

    def test_exchange_charge_is_nonzero(self) -> None:
        fees = FeeCalculator.equity_delivery(
            side=OrderSide.BUY,
            price=Decimal("2500"),
            quantity=Decimal("10"),
        )
        assert fees.exchange > Decimal("0")


# ---------------------------------------------------------------------------
# PricingService — pure calculations
# ---------------------------------------------------------------------------

class TestPricingService:
    def test_vwap(self) -> None:
        prices = [Decimal("100"), Decimal("102"), Decimal("104")]
        quantities = [Decimal("10"), Decimal("20"), Decimal("30")]
        result = PricingService.vwap(prices, quantities)
        # (100*10 + 102*20 + 104*30) / (10+20+30) = (1000+2040+3120)/60 = 6160/60
        expected = (Decimal("100") * Decimal("10") + Decimal("102") * Decimal("20") + Decimal("104") * Decimal("30")) / (Decimal("10") + Decimal("20") + Decimal("30"))
        assert result == expected

    def test_vwap_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            PricingService.vwap([], [])

    def test_slippage_bps(self) -> None:
        """Slippage in basis points between expected and fill price."""
        result = PricingService.slippage_bps(
            expected_price=Decimal("100"),
            fill_price=Decimal("100.50"),
        )
        # 0.50 / 100 * 10000 = 50 bps
        assert result == Decimal("50")

    def test_slippage_bps_zero(self) -> None:
        result = PricingService.slippage_bps(
            expected_price=Decimal("100"),
            fill_price=Decimal("100"),
        )
        assert result == Decimal("0")


# ---------------------------------------------------------------------------
# InstrumentRegistry — symbol → InstrumentId mapping
# ---------------------------------------------------------------------------

class TestInstrumentRegistry:
    def _make_instrument(self, symbol: str, exchange: str = "NSE") -> Instrument:
        return Instrument(
            instrument_id=InstrumentId.equity(exchange, symbol),
            symbol=symbol,
            exchange=ExchangeId.NSE,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            instrument_type=InstrumentType.EQUITY,
        )

    def test_register_and_lookup(self) -> None:
        registry = InstrumentRegistry()
        inst = self._make_instrument("RELIANCE")
        registry.register(inst)
        assert registry.lookup("RELIANCE") == inst

    def test_lookup_missing_returns_none(self) -> None:
        registry = InstrumentRegistry()
        assert registry.lookup("NONEXISTENT") is None

    def test_register_overwrites(self) -> None:
        registry = InstrumentRegistry()
        inst1 = self._make_instrument("RELIANCE")
        inst2 = Instrument(
            instrument_id=InstrumentId.equity("BSE", "RELIANCE"),
            symbol="RELIANCE",
            exchange=ExchangeId.NSE,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            instrument_type=InstrumentType.EQUITY,
        )
        registry.register(inst1)
        registry.register(inst2)
        assert registry.lookup("RELIANCE") == inst2

    def test_instruments_by_exchange(self) -> None:
        registry = InstrumentRegistry()
        inst_nse = self._make_instrument("RELIANCE")
        inst_bse = Instrument(
            instrument_id=InstrumentId.equity("BSE", "TCS"),
            symbol="TCS",
            exchange=ExchangeId.BSE,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            instrument_type=InstrumentType.EQUITY,
        )
        registry.register(inst_nse)
        registry.register(inst_bse)
        nse_instruments = registry.instruments_by_exchange(ExchangeId.NSE)
        assert len(nse_instruments) == 1
        assert nse_instruments[0].exchange == ExchangeId.NSE
