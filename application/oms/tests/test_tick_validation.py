"""Tests for tick size validation in RiskManager.check_order()."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.oms import PositionManager, RiskConfig, RiskManager
from domain import Order, OrderStatus, OrderType, ProductType, Side


def _make_order(
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    price: Decimal = Decimal("100.05"),
    quantity: int = 10,
) -> Order:
    return Order(
        order_id="O-1",
        symbol=symbol,
        exchange=exchange,
        side=Side.BUY,
        quantity=quantity,
        price=price,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )


@dataclass
class _FakeInstrument:
    tick_size: Decimal = Decimal("0.05")


@dataclass
class _FakeInstrumentProvider:
    instrument: _FakeInstrument | None = None

    def resolve(self, symbol: str, exchange: str):
        return self.instrument


@pytest.fixture
def position_manager() -> PositionManager:
    return PositionManager()


@pytest.fixture
def capital_provider() -> MagicMock:
    cp = MagicMock()
    cp.get_available_balance.return_value = Decimal("1000000")
    return cp


@pytest.fixture
def risk_config() -> RiskConfig:
    return RiskConfig()


class TestTickSizeValidation:
    def test_aligned_price_passes(
        self, position_manager, risk_config, capital_provider
    ):
        provider = _FakeInstrumentProvider(_FakeInstrument(Decimal("0.05")))
        rm = RiskManager(
            position_manager=position_manager,
            config=risk_config,
            capital_provider=capital_provider,
            instrument_provider=provider,
        )
        order = _make_order(price=Decimal("100.05"))
        result = rm.check_order(order)
        assert result.allowed is True

    def test_misaligned_price_rejected(
        self, position_manager, risk_config, capital_provider
    ):
        provider = _FakeInstrumentProvider(_FakeInstrument(Decimal("0.05")))
        rm = RiskManager(
            position_manager=position_manager,
            config=risk_config,
            capital_provider=capital_provider,
            instrument_provider=provider,
        )
        order = _make_order(price=Decimal("100.07"))
        result = rm.check_order(order)
        assert result.allowed is False
        assert "tick size" in (result.reason or "").lower()

    def test_market_order_skips_tick_check(
        self, position_manager, risk_config, capital_provider
    ):
        provider = _FakeInstrumentProvider(_FakeInstrument(Decimal("0.05")))
        rm = RiskManager(
            position_manager=position_manager,
            config=risk_config,
            capital_provider=capital_provider,
            instrument_provider=provider,
        )
        order = _make_order(price=Decimal("0"))
        order = Order(
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=order.quantity,
            price=Decimal("0"),
            order_type=OrderType.MARKET,
            product_type=order.product_type,
            status=order.status,
        )
        result = rm.check_order(order)
        assert result.allowed is True

    def test_no_instrument_provider_skips_check(
        self, position_manager, risk_config, capital_provider
    ):
        rm = RiskManager(
            position_manager=position_manager,
            config=risk_config,
            capital_provider=capital_provider,
        )
        order = _make_order(price=Decimal("100.07"))
        result = rm.check_order(order)
        assert result.allowed is True

    def test_instrument_not_found_skips_check(
        self, position_manager, risk_config, capital_provider
    ):
        provider = _FakeInstrumentProvider(instrument=None)
        rm = RiskManager(
            position_manager=position_manager,
            config=risk_config,
            capital_provider=capital_provider,
            instrument_provider=provider,
        )
        order = _make_order(price=Decimal("100.07"))
        result = rm.check_order(order)
        assert result.allowed is True

    def test_lookup_exception_skips_check(
        self, position_manager, risk_config, capital_provider
    ):
        class BrokenProvider:
            def resolve(self, symbol, exchange):
                raise RuntimeError("DB down")

        rm = RiskManager(
            position_manager=position_manager,
            config=risk_config,
            capital_provider=capital_provider,
            instrument_provider=BrokenProvider(),
        )
        order = _make_order(price=Decimal("100.07"))
        result = rm.check_order(order)
        assert result.allowed is True

    def test_float_tick_size_from_canonical_instrument(
        self, position_manager, risk_config, capital_provider
    ):
        @dataclass
        class FloatTickInstrument:
            tick_size: float = 0.05

        provider = _FakeInstrumentProvider(FloatTickInstrument())
        rm = RiskManager(
            position_manager=position_manager,
            config=risk_config,
            capital_provider=capital_provider,
            instrument_provider=provider,
        )
        order = _make_order(price=Decimal("100.05"))
        result = rm.check_order(order)
        assert result.allowed is True

    def test_large_tick_size_fno(
        self, position_manager, capital_provider
    ):
        config = RiskConfig(enable_margin_check=False)
        provider = _FakeInstrumentProvider(_FakeInstrument(Decimal("10")))
        rm = RiskManager(
            position_manager=position_manager,
            config=config,
            capital_provider=capital_provider,
            instrument_provider=provider,
        )
        aligned = _make_order(
            symbol="NIFTY25JUN20000CE",
            exchange="NFO",
            price=Decimal("72340"),
            quantity=1,
        )
        assert rm.check_order(aligned).allowed is True

        misaligned = _make_order(
            symbol="NIFTY25JUN20000CE",
            exchange="NFO",
            price=Decimal("72345"),
            quantity=1,
        )
        assert rm.check_order(misaligned).allowed is False
