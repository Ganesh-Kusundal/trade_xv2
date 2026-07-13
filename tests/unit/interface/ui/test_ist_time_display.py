"""CLI timestamp display must show IST, not raw UTC.

Broker quote/order/trade timestamps are stored internally as UTC-aware
datetimes (see domain.ports.time_service) -- that's deliberate, not a
bug: it avoids DST/comparison bugs and matches how Dhan/Upstox actually
send timestamps. The quote terminal and OMS order/trade tables used to
call ``.strftime()`` directly on them, so a tick captured at 15:59 IST
during live market hours displayed as "10:29".

Fixed with one canonical converter (``interface.ui.utils.time_formatter
.format_ist_time``) imported by every display site, rather than each
site defining its own copy.
"""

from __future__ import annotations

from datetime import datetime, timezone

from interface.ui.utils.time_formatter import format_ist_time


class TestFormatIstTime:
    def test_utc_aware_timestamp_converted_to_ist(self):
        utc_ts = datetime(2026, 7, 13, 10, 29, 15, tzinfo=timezone.utc)
        assert format_ist_time(utc_ts) == "15:59:15"

    def test_naive_timestamp_left_unconverted(self):
        naive_ts = datetime(2026, 7, 13, 15, 59, 15)
        assert format_ist_time(naive_ts) == "15:59:15"

    def test_none_timestamp_shows_na(self):
        assert format_ist_time(None) == "N/A"

    def test_midnight_utc_rolls_to_next_day_ist(self):
        """23:45 UTC is 05:15 IST the next day -- exercises the +5:30 rollover."""
        utc_ts = datetime(2026, 7, 13, 23, 45, 0, tzinfo=timezone.utc)
        assert format_ist_time(utc_ts) == "05:15:00"


class TestDisplaySitesUseTheSharedFormatter:
    """market.py and oms.py must import the one shared formatter, not
    each define their own -- guards against the duplication regressing."""

    def test_market_module_imports_shared_formatter(self):
        import interface.ui.commands.market as market_module

        assert market_module.format_ist_time is format_ist_time

    def test_oms_module_imports_shared_formatter(self):
        import interface.ui.commands.oms as oms_module

        assert oms_module.format_ist_time is format_ist_time
