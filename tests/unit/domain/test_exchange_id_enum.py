"""Tests for ExchangeId enum and DEFAULT_EXCHANGE constant (REF-3)."""

from domain.market_enums import ExchangeId


def test_exchange_id_values():
    assert ExchangeId.NSE == "NSE"
    assert ExchangeId.NFO == "NFO"
    assert ExchangeId.BSE == "BSE"
    assert ExchangeId.MCX == "MCX"
    assert ExchangeId.UNKNOWN == "UNKNOWN"


def test_exchange_id_is_str_enum():
    assert isinstance(ExchangeId.NSE, str)
    assert isinstance(ExchangeId.NSE, ExchangeId)


def test_default_exchange():
    from domain.constants.defaults import DEFAULT_EXCHANGE

    assert DEFAULT_EXCHANGE == ExchangeId.NSE
    assert DEFAULT_EXCHANGE == "NSE"


def test_exchange_id_string_comparison():
    assert ExchangeId.NSE == "NSE"
    assert "NSE" == ExchangeId.NSE
    assert ExchangeId.NSE != "BSE"
