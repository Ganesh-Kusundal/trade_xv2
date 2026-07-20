from datetime import date, datetime
from zoneinfo import ZoneInfo

from domain.ports.exchange_adapter import ExchangeAdapter
from plugins.exchanges.nse import ADAPTER, CALENDAR


def test_nse_adapter_implements_exchange_adapter_protocol():
    assert isinstance(ADAPTER, ExchangeAdapter)
    assert ADAPTER.exchange == "NSE"
    assert ADAPTER.timezone == "Asia/Kolkata"
    assert ADAPTER.base_currency == "INR"
    assert ADAPTER.price_scale == 100
    assert ADAPTER.tick_size == 0.05
    assert ADAPTER.lot_size == 1


def test_nse_trading_hours():
    ist = ZoneInfo("Asia/Kolkata")
    during = datetime(2026, 7, 13, 10, 0, tzinfo=ist)
    open_time, close_time = CALENDAR.session_bounds(during.date())
    assert open_time <= during.time() <= close_time
    before = datetime(2026, 7, 13, 8, 0, tzinfo=ist)
    assert before.time() < open_time


def test_nse_trading_day():
    monday = date(2026, 7, 13)
    assert CALENDAR.is_trading_day(monday)
    saturday = date(2026, 7, 18)
    assert not CALENDAR.is_trading_day(saturday)


def test_nse_adapter_normalizes_symbol():
    assert ADAPTER.normalize_symbol(" reliance ", "NSE") == "RELIANCE"


def test_nse_calendar_timezone():
    assert CALENDAR.timezone == "Asia/Kolkata"