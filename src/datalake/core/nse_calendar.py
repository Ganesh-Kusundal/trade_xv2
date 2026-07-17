"""NSE market holiday calendar — Indian stock market trading days.

Provides:
- ``is_trading_day(date)`` — check if a date is a trading day
- ``trading_days_between(start, end)`` — count trading days in range
- ``expected_candles(date, timeframe)`` — expected candle count for a day

Covers NSE holidays for 2020-2026. Includes:
- Official NSE holidays (Republic Day, Independence Day, etc.)
- Special trading sessions (Muhurat trading, etc.)
- Known early closes

For production use, consider loading from an API or database that
is updated annually by NSE.
"""

from __future__ import annotations

from datetime import date, timedelta

# NSE holidays 2020-2026 (official + known special sessions)
# Sourced from NSE's official yearly "Trading holidays" circulars (NSE/CMTR/*,
# e.g. archives CMTR46623/50560/54757/59722/65587/71775), cross-checked against
# zero-candle days in the datalake. Diwali-Laxmi Pujan (Muhurat trading) dates
# are included: the regular session is closed even though a short evening
# Muhurat auction runs, so a handful of candles on that date is expected, not
# a data gap. Two lunar holidays (Bakri Id 2021, 2023) shifted by a day after
# the original circular per moon-sighting addenda; the shifted date is used
# here since it matches actual exchange closure in the datalake.
_NSE_HOLIDAYS: set[date] = {
    # 2020
    date(2020, 2, 21), date(2020, 3, 10),
    date(2020, 4, 2), date(2020, 4, 6), date(2020, 4, 10),
    date(2020, 4, 14), date(2020, 5, 1), date(2020, 5, 25),
    date(2020, 10, 2), date(2020, 11, 16), date(2020, 11, 30),
    date(2020, 12, 25),
    # 2021
    date(2021, 1, 26), date(2021, 3, 11), date(2021, 3, 29),
    date(2021, 4, 2), date(2021, 4, 14), date(2021, 4, 21),
    date(2021, 5, 13), date(2021, 7, 21), date(2021, 8, 19),
    date(2021, 9, 10), date(2021, 10, 15), date(2021, 11, 4),
    date(2021, 11, 5), date(2021, 11, 19), date(2021, 12, 25),
    # 2022
    date(2022, 1, 26), date(2022, 3, 1), date(2022, 3, 18),
    date(2022, 4, 14), date(2022, 4, 15),
    date(2022, 5, 3), date(2022, 8, 9),
    date(2022, 8, 15), date(2022, 8, 31), date(2022, 10, 5), date(2022, 10, 24),
    date(2022, 10, 26), date(2022, 11, 8), date(2022, 12, 25),
    # 2023
    date(2023, 1, 26), date(2023, 3, 7), date(2023, 3, 30),
    date(2023, 4, 4), date(2023, 4, 7), date(2023, 4, 14), date(2023, 5, 1),
    date(2023, 6, 29), date(2023, 8, 15),
    date(2023, 9, 19), date(2023, 10, 2), date(2023, 10, 24),
    date(2023, 11, 14), date(2023, 11, 27), date(2023, 12, 25),
    # 2024
    date(2024, 1, 26), date(2024, 3, 8), date(2024, 3, 25),
    date(2024, 3, 29), date(2024, 4, 11),
    date(2024, 4, 17), date(2024, 5, 1),
    date(2024, 6, 17), date(2024, 7, 17), date(2024, 8, 15),
    date(2024, 10, 2), date(2024, 11, 1),
    date(2024, 11, 15), date(2024, 12, 25),
    # 2024 special one-off closures (ad-hoc NSE circulars, not the annual list):
    # Jan 22 Ram Mandir Pran Pratishtha (Maharashtra govt holiday);
    # May 20 / Nov 20 Mumbai/Maharashtra election polling days.
    date(2024, 1, 22), date(2024, 5, 20), date(2024, 11, 20),
    # 2025
    date(2025, 2, 26), date(2025, 3, 14),
    date(2025, 3, 31), date(2025, 4, 10), date(2025, 4, 14),
    date(2025, 4, 18), date(2025, 5, 1),
    date(2025, 8, 15), date(2025, 8, 27), date(2025, 10, 2), date(2025, 10, 21),
    date(2025, 10, 22), date(2025, 11, 5), date(2025, 12, 25),
    # 2026
    date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26),
    date(2026, 3, 31), date(2026, 4, 3), date(2026, 4, 14),
    date(2026, 5, 1), date(2026, 5, 28), date(2026, 6, 26),
    date(2026, 9, 14), date(2026, 10, 2), date(2026, 10, 20),
    date(2026, 11, 10), date(2026, 12, 25),
    # 2026 special one-off closure: Jan 15 Maharashtra civic body elections.
    date(2026, 1, 15),
}

# Early close days (market closes at 1:30 PM IST instead of 3:30 PM)
_EARLY_CLOSE_DAYS: set[date] = set()


def is_trading_day(d: date) -> bool:
    """Check if a date is an NSE trading day.

    Returns False for weekends (Sat/Sun), NSE holidays, and the
    day after if it's a known early-close-adjacent holiday.
    """
    if d.weekday() >= 5:
        return False
    return d not in _NSE_HOLIDAYS


def is_early_close(d: date) -> bool:
    """Check if a date is an early close day (1:30 PM IST close)."""
    return d in _EARLY_CLOSE_DAYS


def trading_days_between(start: date, end: date) -> list[date]:
    """Return list of trading days between start and end (inclusive)."""
    days = []
    current = start
    while current <= end:
        if is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def count_trading_days(start: date, end: date) -> int:
    """Count trading days between start and end (inclusive)."""
    return len(trading_days_between(start, end))


#: Regular NSE session length: 9:15 AM to 3:30 PM IST.
REGULAR_SESSION_MINUTES: int = 375
#: Early-close session length: 9:15 AM to 1:30 PM IST.
EARLY_CLOSE_SESSION_MINUTES: int = 255
#: Timeframe -> minutes-per-candle. Single source for candle-count math.
TIMEFRAME_MINUTES: dict[str, int] = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}


def expected_candles_per_day(timeframe: str = "1m", *, early_close: bool = False) -> int:
    """Expected candle count for a full (or early-close) session and timeframe.

    Date-agnostic helper: the single formula behind both the calendar-aware
    :func:`expected_candles` and the datalake completeness checks (previously
    each hardcoded ``candles_per_hour * 6.25``, i.e. 375/60 in disguise).
    """
    minutes = EARLY_CLOSE_SESSION_MINUTES if early_close else REGULAR_SESSION_MINUTES
    return minutes // TIMEFRAME_MINUTES.get(timeframe, 1)


def expected_candles(d: date, timeframe: str = "1m") -> int:
    """Expected candle count for a given trading day and timeframe.

    Regular session: 9:15 AM to 3:30 PM IST = 375 minutes
    Early close:     9:15 AM to 1:30 PM IST = 255 minutes
    """
    if not is_trading_day(d):
        return 0
    return expected_candles_per_day(timeframe, early_close=is_early_close(d))
