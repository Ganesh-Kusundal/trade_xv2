"""Unit tests for domain models."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from brokers.dhan.domain import (
    Exchange,
    Instrument,
    InstrumentType,
    OptionType,
)
from domain import Balance, Quote, Side


def test_exchange_enum_values():
    expected = {"NSE", "BSE", "NFO", "BFO", "MCX", "CDS", "INDEX"}
    actual = {e.value for e in Exchange}
    assert actual == expected


def test_instrument_frozen():
    inst = Instrument(
        symbol="X",
        exchange=Exchange.NSE,
        security_id="1",
        instrument_type=InstrumentType.EQUITY,
    )
    with pytest.raises(FrozenInstanceError):
        inst.symbol = "Y"


def test_quote_defaults():
    q = Quote(symbol="X", ltp=Decimal("100"))
    assert q.symbol == "X"
    assert q.ltp == Decimal("100")
    assert q.open == Decimal("0")
    assert q.high == Decimal("0")
    assert q.low == Decimal("0")
    assert q.close == Decimal("0")
    assert q.volume == 0
    assert q.change == Decimal("0")


def test_order_side_enum():
    assert Side.BUY.value == "BUY"
    assert Side.SELL.value == "SELL"


def test_balance_fields():
    b = Balance()
    fields = {
        "available_balance",
        "sod_limit",
        "collateral_amount",
        "utilized_amount",
        "withdrawable_balance",
        "used_margin",
        "total_margin",
    }
    assert set(b.__dataclass_fields__.keys()) == fields
    # All default to zero
    assert all(getattr(b, f) == Decimal("0") for f in fields)


def test_instrument_is_option_property():
    inst = Instrument(
        symbol="NIFTY 25000 CE",
        exchange=Exchange.NFO,
        security_id="55000",
        instrument_type=InstrumentType.OPTION,
        option_type=OptionType.CALL,
        strike_price=Decimal("25000"),
    )
    assert inst.is_option is True
    assert inst.is_future is False


def test_instrument_is_future_property():
    inst = Instrument(
        symbol="NIFTY JUN FUT",
        exchange=Exchange.NFO,
        security_id="55100",
        instrument_type=InstrumentType.FUTURE,
    )
    assert inst.is_future is True
    assert inst.is_option is False
