"""TDD tests for broker.core.enums."""

from brokers.common.core.enums import (
    ExchangeSegment,
    FeedMode,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)


class TestExchangeSegment:
    def test_values(self):
        assert ExchangeSegment.NSE.value == "NSE_EQ"
        assert ExchangeSegment.BSE.value == "BSE_EQ"
        assert ExchangeSegment.NSE_FNO.value == "NSE_FNO"
        assert ExchangeSegment.BSE_FNO.value == "BSE_FNO"
        assert ExchangeSegment.MCX.value == "MCX_COMM"
        assert ExchangeSegment.NSE_CURRENCY.value == "NSE_CURRENCY"
        assert ExchangeSegment.IDX_I.value == "IDX_I"

    def test_all_unique(self):
        values = [e.value for e in ExchangeSegment]
        assert len(values) == len(set(values))

    def test_from_value_valid(self):
        assert ExchangeSegment.from_value("NSE_EQ") == ExchangeSegment.NSE

    def test_from_value_invalid(self):
        with pytest.raises(ValueError):
            ExchangeSegment.from_value("INVALID")

    def test_str(self):
        assert str(ExchangeSegment.NSE) == "NSE_EQ"


class TestOrderType:
    def test_values(self):
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.STOP_LOSS.value == "STOP_LOSS"
        assert OrderType.STOP_LOSS_MARKET.value == "STOP_LOSS_MARKET"


class TestProductType:
    def test_values(self):
        assert ProductType.CNC.value == "CNC"
        assert ProductType.INTRADAY.value == "INTRADAY"
        assert ProductType.MARGIN.value == "MARGIN"
        assert ProductType.MTF.value == "MTF"

    def test_valid_for_segment(self):
        assert ProductType.CNC in ProductType.valid_for("NSE_EQ")
        assert ProductType.INTRADAY in ProductType.valid_for("NSE_FNO")
        assert ProductType.MTF not in ProductType.valid_for("NSE_FNO")


class TestTransactionType:
    def test_values(self):
        assert TransactionType.BUY.value == "BUY"
        assert TransactionType.SELL.value == "SELL"

    def test_opposite(self):
        assert TransactionType.BUY.opposite() == TransactionType.SELL
        assert TransactionType.SELL.opposite() == TransactionType.BUY


class TestOrderStatus:
    def test_values(self):
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.OPEN.value == "OPEN"
        assert OrderStatus.EXECUTED.value == "EXECUTED"
        assert OrderStatus.REJECTED.value == "REJECTED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.PARTIALLY_EXECUTED.value == "PARTIALLY_EXECUTED"
        assert OrderStatus.TRIGGER_PENDING.value == "TRIGGER_PENDING"

    def test_is_terminal(self):
        assert OrderStatus.EXECUTED.is_terminal() is True
        assert OrderStatus.REJECTED.is_terminal() is True
        assert OrderStatus.CANCELLED.is_terminal() is True
        assert OrderStatus.PENDING.is_terminal() is False


class TestValidity:
    def test_values(self):
        assert Validity.DAY.value == "DAY"
        assert Validity.IOC.value == "IOC"


class TestInstrumentType:
    def test_values(self):
        assert InstrumentType.EQUITY.value == "EQUITY"
        assert InstrumentType.FUTURES.value == "FUTURES"
        assert InstrumentType.OPTIONS.value == "OPTIONS"


class TestFeedMode:
    def test_values(self):
        assert FeedMode.LTP.value == "LTP"
        assert FeedMode.FULL.value == "FULL"
        assert FeedMode.DEPTH.value == "DEPTH"


import pytest
