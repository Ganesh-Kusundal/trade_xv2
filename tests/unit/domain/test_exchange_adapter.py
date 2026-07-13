from datetime import datetime, time
from zoneinfo import ZoneInfo

from domain.market.exchange_adapters import (
    BSEExchangeAdapter,
    MCXExchangeAdapter,
    NSEExchangeAdapter,
    get_exchange_adapter,
)
from domain.ports.exchange_adapter import ExchangeAdapterPort


def test_nse_adapter_satisfies_protocol():
    adapter = NSEExchangeAdapter()
    assert isinstance(adapter, ExchangeAdapterPort)


def test_nse_trading_hours():
    adapter = NSEExchangeAdapter()
    ist = ZoneInfo("Asia/Kolkata")
    # 10:00 IST on a Monday
    during = datetime(2026, 7, 13, 10, 0, tzinfo=ist)
    assert adapter.is_trading_hours(during)
    # 8:00 IST — before market open
    before = datetime(2026, 7, 13, 8, 0, tzinfo=ist)
    assert not adapter.is_trading_hours(before)


def test_nse_trading_day():
    adapter = NSEExchangeAdapter()
    ist = ZoneInfo("Asia/Kolkata")
    monday = datetime(2026, 7, 13, 10, 0, tzinfo=ist)
    assert adapter.is_trading_day(monday)
    saturday = datetime(2026, 7, 18, 10, 0, tzinfo=ist)
    assert not adapter.is_trading_day(saturday)


def test_get_exchange_adapter_known():
    adapter = get_exchange_adapter("NSE")
    assert adapter.exchange_code == "NSE"


def test_get_exchange_adapter_unknown():
    import pytest
    with pytest.raises(KeyError):
        get_exchange_adapter("UNKNOWN")


def test_all_adapters_have_timezone():
    for name in ("NSE", "BSE", "MCX"):
        adapter = get_exchange_adapter(name)
        assert adapter.timezone is not None
