"""Value object contract: Decimal money/price/qty, frozen, UUID correlation."""

from decimal import Decimal
from uuid import uuid4

import pytest

from domain.value_objects import (
    AccountId,
    ComponentId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
    StrategyId,
    TimeFrame,
    Timestamp,
)


# ── Immutability ──────────────────────────────────────────────────────

def test_ids_are_frozen() -> None:
    iid = InstrumentId.parse("NSE:RELIANCE")
    with pytest.raises(Exception):
        iid.value = "NSE:TCS"  # type: ignore[misc]


def test_money_is_frozen() -> None:
    m = Money(amount=Decimal("100"), currency="INR")
    with pytest.raises(Exception):
        m.amount = Decimal("200")  # type: ignore[misc]
    with pytest.raises(Exception):
        m.currency = "USD"  # type: ignore[misc]


def test_price_quantity_frozen() -> None:
    p = Price(value=Decimal("1"))
    q = Quantity(value=Decimal("1"))
    with pytest.raises(Exception):
        p.value = Decimal("2")  # type: ignore[misc]
    with pytest.raises(Exception):
        q.value = Decimal("2")  # type: ignore[misc]


def test_correlation_id_is_frozen() -> None:
    cid = CorrelationId(value=uuid4())
    with pytest.raises(Exception):
        cid.value = uuid4()  # type: ignore[misc]


def test_timestamp_is_frozen() -> None:
    ts = Timestamp(value=1_700_000_000_000_000_000)
    with pytest.raises(Exception):
        ts.value = 0  # type: ignore[misc]


# ── Decimal enforcement ──────────────────────────────────────────────

def test_money_rejects_float() -> None:
    with pytest.raises((TypeError, ValueError)):
        Money(amount=100.5, currency="INR")  # type: ignore[arg-type]


def test_price_rejects_float() -> None:
    with pytest.raises((TypeError, ValueError)):
        Price(value=2500.55)  # type: ignore[arg-type]


def test_quantity_rejects_float() -> None:
    with pytest.raises((TypeError, ValueError)):
        Quantity(value=10.0)  # type: ignore[arg-type]


def test_price_and_quantity_use_decimal() -> None:
    p = Price(value=Decimal("2500.55"))
    q = Quantity(value=Decimal("10"))
    assert isinstance(p.value, Decimal)
    assert isinstance(q.value, Decimal)
    assert (p * q) == Decimal("25005.50")


# ── Arithmetic ───────────────────────────────────────────────────────

def test_money_arithmetic() -> None:
    a = Money(amount=Decimal("100.50"), currency="INR")
    b = Money(amount=Decimal("25.25"), currency="INR")
    assert (a + b).amount == Decimal("125.75")
    assert (a - b).amount == Decimal("75.25")
    assert (a * Decimal("2")).amount == Decimal("201.00")


def test_money_rejects_currency_mismatch() -> None:
    a = Money(amount=Decimal("10"), currency="INR")
    b = Money(amount=Decimal("10"), currency="USD")
    with pytest.raises(ValueError):
        _ = a + b


# ── Equality & hashing ──────────────────────────────────────────────

def test_id_equality() -> None:
    assert InstrumentId.parse("NSE:RELIANCE") == InstrumentId.parse("NSE:RELIANCE")
    assert InstrumentId.parse("NSE:RELIANCE") != InstrumentId.parse("NSE:TCS")


def test_money_equality() -> None:
    a = Money(amount=Decimal("100"), currency="INR")
    b = Money(amount=Decimal("100"), currency="INR")
    c = Money(amount=Decimal("200"), currency="INR")
    assert a == b
    assert a != c


def test_price_equality() -> None:
    assert Price(Decimal("2500")) == Price(Decimal("2500"))
    assert Price(Decimal("2500")) != Price(Decimal("3000"))


def test_quantity_equality() -> None:
    assert Quantity(Decimal("10")) == Quantity(Decimal("10"))
    assert Quantity(Decimal("10")) != Quantity(Decimal("20"))


def test_correlation_id_equality() -> None:
    uid = uuid4()
    assert CorrelationId(uid) == CorrelationId(uid)
    assert CorrelationId(uid) != CorrelationId(uuid4())


def test_timestamp_equality() -> None:
    assert Timestamp(1_700_000_000_000_000_000) == Timestamp(1_700_000_000_000_000_000)
    assert Timestamp(1) != Timestamp(2)


def test_value_objects_are_hashable() -> None:
    s = {
        InstrumentId.parse("NSE:A"),
        OrderId("1"),
        AccountId("A"),
        StrategyId("S"),
        ComponentId("C"),
        CorrelationId(uuid4()),
        TimeFrame("1m"),
        Timestamp(0),
        Price(Decimal("1")),
        Quantity(Decimal("1")),
        Money(amount=Decimal("1"), currency="INR"),
    }
    assert len(s) == 11


def test_value_objects_in_dict_keys() -> None:
    d = {InstrumentId.parse("NSE:A"): 1, Price(Decimal("1")): 2}
    assert d[InstrumentId.parse("NSE:A")] == 1
    assert d[Price(Decimal("1"))] == 2


# ── String representation ───────────────────────────────────────────

def test_instrument_id_str() -> None:
    assert str(InstrumentId.parse("NSE:RELIANCE")) == "NSE:RELIANCE"


def test_money_str() -> None:
    m = Money(amount=Decimal("100.50"), currency="INR")
    assert "100.50" in str(m)
    assert "INR" in str(m)


def test_price_str() -> None:
    p = Price(value=Decimal("2500.55"))
    assert "2500.55" in str(p)


def test_quantity_str() -> None:
    q = Quantity(value=Decimal("10"))
    assert "10" in str(q)


def test_correlation_id_str() -> None:
    uid = uuid4()
    assert str(uid) in str(CorrelationId(uid))


def test_timestamp_str() -> None:
    ts = Timestamp(value=1_700_000_000_000_000_000)
    assert "1700000000000000000" in str(ts)


# ── Remaining id types and timeframe ─────────────────────────────────

def test_remaining_id_types_and_timeframe() -> None:
    assert OrderId(value="ord-1").value == "ord-1"
    assert AccountId(value="acct-1").value == "acct-1"
    assert StrategyId(value="strat-1").value == "strat-1"
    assert ComponentId(value="comp-1").value == "comp-1"
    assert TimeFrame(value="1m").value == "1m"


def test_timestamp_is_int() -> None:
    ts = Timestamp(value=1_700_000_000_000_000_000)
    assert isinstance(ts.value, int)
