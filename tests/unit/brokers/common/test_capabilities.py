"""Golden tests for BrokerCapabilities snapshots and query API."""

from brokers.common.rate_limit_config import DHAN_RATE_LIMITS, profiles_from_table
from brokers.providers.dhan.config.capabilities import dhan_capabilities
from brokers.providers.upstox.capabilities import upstox_capabilities


class TestDhanCapabilities:
    def test_super_order_and_depth_ws(self):
        caps = dhan_capabilities()
        assert caps.supports("super_order")
        assert caps.supports("depth_20_ws")
        assert caps.supports("expired_options_history")
        assert not caps.supports("news")
        assert not caps.supports("fundamentals")
        assert not caps.supports("portfolio_stream")
        assert caps.supports("native_slice_order")

    def test_intraday_lookback_ten_years(self):
        caps = dhan_capabilities()
        window = caps.historical_window_for("1m")
        assert window is not None
        assert window.max_lookback_days == 3650

    def test_orders_rate_limit_profile(self):
        caps = dhan_capabilities()
        profile = caps.limit_for("orders")
        assert profile is not None
        assert profile.sustained_rps == 10.0
        assert profile.extra_windows == ((250, 60.0), (7000, 86400.0))

    def test_extra_windows_round_trip_through_profiles_from_table(self):
        profiles = profiles_from_table(DHAN_RATE_LIMITS)
        orders = next(p for p in profiles if p.endpoint_class == "orders")
        assert orders.extra_windows == ((250, 60.0), (7000, 86400.0))


class TestUpstoxCapabilities:
    def test_news_and_no_super_order(self):
        caps = upstox_capabilities()
        assert caps.supports("news")
        assert caps.supports("fundamentals")
        assert not caps.supports("super_order")
        assert not caps.supports("depth_20_ws")
        assert caps.supports("expired_options_history")
        assert caps.supports("native_slice_order")
        assert caps.supports("forever_order")
        assert caps.max_batch_size == 500
        q = caps.limit_for("quotes")
        assert q is not None
        assert q.sustained_rps == 25.0

    def test_intraday_lookback_thirty_days(self):
        caps = upstox_capabilities()
        window = caps.historical_window_for("1m")
        assert window is not None
        assert window.max_lookback_days == 30

    def test_orders_extra_windows(self):
        caps = upstox_capabilities()
        profile = caps.limit_for("orders")
        assert profile is not None
        assert profile.extra_windows == ((500, 60.0), (2000, 1800.0))

    def test_can_serve_historical_respects_window(self):
        caps = upstox_capabilities()
        assert caps.can_serve_historical("1m", 30)
        assert not caps.can_serve_historical("1m", 31)
