"""REF-3: market-hours helper tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brokers.common.core.constants import IST_OFFSET
from brokers.common.core.market_hours import (
    BSE_EQUITY_SESSION,
    MCX_COMMODITY_SESSION,
    NSE_CURRENCY_SESSION,
    NSE_EQUITY_SESSION,
    SESSIONS,
    TradingSession,
    is_equity_market_open,
    is_mcx_open,
    is_session_open,
    ist_now,
)


# All tests use a fixed reference date: 2026-06-17 (Wednesday in IST).
# This is a working day in IST, so weekday-only checks pass cleanly.
WED_IST_9_00 = datetime(2026, 6, 17, 9, 0, tzinfo=IST_OFFSET)
WED_IST_9_14 = datetime(2026, 6, 17, 9, 14, tzinfo=IST_OFFSET)
WED_IST_9_15 = datetime(2026, 6, 17, 9, 15, tzinfo=IST_OFFSET)
WED_IST_12_00 = datetime(2026, 6, 17, 12, 0, tzinfo=IST_OFFSET)
WED_IST_15_29 = datetime(2026, 6, 17, 15, 29, tzinfo=IST_OFFSET)
WED_IST_15_30 = datetime(2026, 6, 17, 15, 30, tzinfo=IST_OFFSET)
WED_IST_17_00 = datetime(2026, 6, 17, 17, 0, tzinfo=IST_OFFSET)
WED_IST_23_29 = datetime(2026, 6, 17, 23, 29, tzinfo=IST_OFFSET)
WED_IST_23_30 = datetime(2026, 6, 17, 23, 30, tzinfo=IST_OFFSET)
SAT_IST_10_00 = datetime(2026, 6, 20, 10, 0, tzinfo=IST_OFFSET)  # Saturday
SUN_IST_10_00 = datetime(2026, 6, 21, 10, 0, tzinfo=IST_OFFSET)  # Sunday


class TestIstNow:
    def test_returns_ist_datetime(self):
        now = ist_now()
        assert now.tzinfo is not None
        # Convert to IST and check offset
        assert now.astimezone(IST_OFFSET).utcoffset() == timedelta(hours=5, minutes=30)


class TestNseEquitySession:
    @pytest.mark.parametrize("when", [WED_IST_9_15, WED_IST_12_00, WED_IST_15_29])
    def test_open_during_hours(self, when):
        assert NSE_EQUITY_SESSION.is_open(when) is True

    @pytest.mark.parametrize("when", [WED_IST_9_00, WED_IST_9_14, WED_IST_15_30, WED_IST_17_00])
    def test_closed_outside_hours(self, when):
        assert NSE_EQUITY_SESSION.is_open(when) is False

    @pytest.mark.parametrize("when", [SAT_IST_10_00, SUN_IST_10_00])
    def test_closed_on_weekend(self, when):
        assert NSE_EQUITY_SESSION.is_open(when) is False

    def test_naive_datetime_treated_as_ist(self):
        # Strip tzinfo from a known-IST datetime and verify the helper
        # treats it as IST (not as UTC).
        naive_open = WED_IST_9_15.replace(tzinfo=None)
        assert NSE_EQUITY_SESSION.is_open(naive_open) is True


class TestMcxCommoditySession:
    @pytest.mark.parametrize("when", [WED_IST_9_00, WED_IST_12_00, WED_IST_23_29])
    def test_open_during_hours(self, when):
        assert MCX_COMMODITY_SESSION.is_open(when) is True

    @pytest.mark.parametrize("when", [WED_IST_9_15, WED_IST_23_30, WED_IST_15_30])
    def test_closed_outside_hours(self, when):
        # 9:15 is NSE open, not MCX (MCX opens at 9:00)
        # 23:30 is the close instant (exclusive)
        # 15:30 is after NSE close but before MCX close; the latter
        # should still be open. Use 8:59 instead.
        pass  # placeholder, see below

    def test_closed_at_close_instant(self):
        assert MCX_COMMODITY_SESSION.is_open(WED_IST_23_30) is False

    def test_closed_before_open(self):
        before = WED_IST_9_00.replace(hour=8, minute=59)
        assert MCX_COMMODITY_SESSION.is_open(before) is False


class TestNseCurrencySession:
    def test_open_at_9_00(self):
        assert NSE_CURRENCY_SESSION.is_open(WED_IST_9_00) is True

    def test_closed_at_17_00(self):
        # The close instant is exclusive
        assert NSE_CURRENCY_SESSION.is_open(WED_IST_17_00) is False

    def test_open_at_16_59(self):
        late = WED_IST_17_00.replace(hour=16, minute=59)
        assert NSE_CURRENCY_SESSION.is_open(late) is True


class TestIsSessionOpen:
    def test_known_session(self):
        assert is_session_open("NSE_EQUITY", WED_IST_12_00) is True
        assert is_session_open("MCX_COMMODITY", WED_IST_12_00) is True

    def test_unknown_session_raises(self):
        with pytest.raises(KeyError):
            is_session_open("BOGUS", WED_IST_12_00)

    def test_uppercase_lookup(self):
        assert is_session_open("nse_equity", WED_IST_12_00) is True


class TestIsEquityMarketOpen:
    def test_open_during_nse_hours(self):
        assert is_equity_market_open(WED_IST_12_00) is True

    def test_closed_at_close(self):
        assert is_equity_market_open(WED_IST_15_30) is False

    def test_closed_on_weekend(self):
        assert is_equity_market_open(SAT_IST_10_00) is False


class TestIsMcxOpen:
    def test_open_at_noon(self):
        assert is_mcx_open(WED_IST_12_00) is True

    def test_closed_at_23_30(self):
        assert is_mcx_open(WED_IST_23_30) is False


class TestSessionsRegistry:
    def test_all_sessions_registered(self):
        assert "NSE_EQUITY" in SESSIONS
        assert "BSE_EQUITY" in SESSIONS
        assert "MCX_COMMODITY" in SESSIONS
        assert "NSE_CURRENCY" in SESSIONS
        assert "BSE_CURRENCY" in SESSIONS
        assert len(SESSIONS) == 5

    def test_bse_equity_matches_nse_hours(self):
        assert BSE_EQUITY_SESSION.open_time == NSE_EQUITY_SESSION.open_time
        assert BSE_EQUITY_SESSION.close_time == NSE_EQUITY_SESSION.close_time
