from __future__ import annotations

from decimal import Decimal

from brokers.upstox.mappers.price_parser import UpstoxPriceParser


def test_parse_rupee_default():
    p = UpstoxPriceParser.parse(123.45)
    assert p == Decimal("123.4500")


def test_parse_string_rupee():
    p = UpstoxPriceParser.parse("98.765")
    assert p == Decimal("98.7650")


def test_parse_paise_to_rupee():
    p = UpstoxPriceParser.parse(98765, is_paise=True)
    assert p == Decimal("987.6500")


def test_to_paise_from_rupee():
    assert UpstoxPriceParser.to_paise(Decimal("10.50")) == 1050
    assert UpstoxPriceParser.to_paise(10) == 1000
    assert UpstoxPriceParser.to_paise("0.99") == 99


def test_to_rupee_from_paise():
    assert UpstoxPriceParser.to_rupee(1050) == Decimal("10.50")
    assert UpstoxPriceParser.to_rupee(99) == Decimal("0.99")


def test_round_trip_paise():
    for rupee in (Decimal("0.01"), Decimal("1.50"), Decimal("12345.67"), Decimal("99999.99")):
        assert UpstoxPriceParser.to_rupee(UpstoxPriceParser.to_paise(rupee)) == rupee


def test_parse_none_or_empty_returns_zero():
    assert UpstoxPriceParser.parse(None) == Decimal("0.0000")
    assert UpstoxPriceParser.parse("") == Decimal("0.0000")
