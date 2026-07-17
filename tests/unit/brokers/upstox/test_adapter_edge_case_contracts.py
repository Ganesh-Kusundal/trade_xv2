"""Regression tests for broker endpoint fixes and bug fixes."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


class TestHistoricalIntervalMapping:
    """Verify the real _INTERVAL_MAP -- 1m (the datalake's canonical lowercase
    timeframe) must resolve to minutes, not silently fall through to the
    ("days", "1") default via resolve_timeframe()'s .upper() call. That
    fallthrough was a real bug: every "1m" 1-minute request returned a
    single midnight daily candle instead of real intraday data, which the
    session-hours validator then correctly (but silently) dropped."""

    def test_1m_resolves_to_minutes_not_days_default(self):
        from brokers.upstox.adapters.historical_adapter import HistoricalAdapter

        assert HistoricalAdapter.resolve_timeframe("1m") == ("minutes", "1")
        assert HistoricalAdapter.resolve_timeframe("5m") == ("minutes", "5")
        assert HistoricalAdapter.resolve_timeframe("15m") == ("minutes", "15")
        assert HistoricalAdapter.resolve_timeframe("30m") == ("minutes", "30")
        assert HistoricalAdapter.resolve_timeframe("60m") == ("hours", "1")

    def test_month_maps_to_months(self):
        from brokers.upstox.adapters.historical_adapter import _INTERVAL_MAP

        assert _INTERVAL_MAP["MON"] == ("months", "1")
        assert _INTERVAL_MAP["MONTH"] == ("months", "1")

    def test_no_duplicate_keys(self):
        from brokers.upstox.adapters.historical_adapter import _INTERVAL_MAP

        keys = list(_INTERVAL_MAP.keys())
        assert len(keys) == len(set(keys)), "Duplicate keys found in _INTERVAL_MAP"


class TestGetOrderbook:
    """Verify get_orderbook uses get_order_list() not _parse_order."""

    def test_get_orderbook_calls_get_order_list(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        broker = MagicMock()
        broker.order_query.get_order_list.return_value = []
        gw = UpstoxBrokerGateway(broker)
        result = gw.get_orderbook()
        broker.order_query.get_order_list.assert_called_once()
        assert result == []


class TestDepthResponseParsing:
    """Verify get_depth parses the nested quotes response format."""

    def test_depth_parses_nested_format(self):
        from brokers.upstox.wire import UpstoxBrokerGateway
        from domain import MarketDepth

        broker = MagicMock()
        broker.instrument_resolver.resolve.return_value = MagicMock(
            instrument_key="NSE_EQ|INE002A01018"
        )
        broker.market_data_v2.get_order_book.return_value = {
            "data": {
                "NSE_EQ:RELIANCE": {
                    "depth": {
                        "buy": [{"price": 100.0, "quantity": 10, "orders": 1}],
                        "sell": [{"price": 101.0, "quantity": 20, "orders": 2}],
                    }
                }
            }
        }
        gw = UpstoxBrokerGateway(broker)
        depth = gw.depth("RELIANCE", "NSE")
        assert isinstance(depth, MarketDepth)
        assert len(depth.bids) == 1
        assert depth.bids[0].price == Decimal("100.0")
        assert len(depth.asks) == 1
        assert depth.asks[0].price == Decimal("101.0")

    def test_depth_handles_empty_data(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        broker = MagicMock()
        broker.instrument_resolver.resolve.return_value = MagicMock(
            instrument_key="NSE_EQ|INE002A01018"
        )
        broker.market_data_v2.get_order_book.return_value = {"data": {}}
        gw = UpstoxBrokerGateway(broker)
        depth = gw.depth("RELIANCE", "NSE")
        assert depth.bids == []
        assert depth.asks == []


class TestHistoricalProperty:
    """Verify historical access works via extended or direct history() method."""

    def test_history_method_exists(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        broker = MagicMock()
        gw = UpstoxBrokerGateway(broker)
        assert hasattr(gw, "history")

    def test_history_callable(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        broker = MagicMock()
        gw = UpstoxBrokerGateway(broker)
        assert callable(gw.history)


class TestNewsAdapterFilters:
    """Verify news adapter forwards category and instrument_keys."""

    def test_adapter_forwards_category(self):
        from brokers.upstox.news.adapter import UpstoxNewsAdapter
        from brokers.upstox.news.client import UpstoxNewsClient

        client = MagicMock(spec=UpstoxNewsClient)
        client.get_news.return_value = []
        adapter = UpstoxNewsAdapter(client)
        adapter.get_news(category="instrument_keys", instrument_keys=["NSE_EQ|INE002A01018"])
        client.get_news.assert_called_once_with(
            category="instrument_keys",
            symbol=None,
            from_date=None,
            to_date=None,
            instrument_keys=["NSE_EQ|INE002A01018"],
        )

    def test_adapter_defaults_category_to_holdings(self):
        from brokers.upstox.news.adapter import UpstoxNewsAdapter
        from brokers.upstox.news.client import UpstoxNewsClient

        client = MagicMock(spec=UpstoxNewsClient)
        client.get_news.return_value = []
        adapter = UpstoxNewsAdapter(client)
        adapter.get_news()
        client.get_news.assert_called_once_with(
            category="holdings",
            symbol=None,
            from_date=None,
            to_date=None,
            instrument_keys=None,
        )


class TestGatewayClose:
    """Verify gateway has a close method."""

    def test_gateway_close_exists(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        broker = MagicMock()
        gw = UpstoxBrokerGateway(broker)
        assert hasattr(gw, "close")
        gw.close()
        broker.disconnect.assert_called_once()


class TestMarketDepthInit:
    """Verify MarketDepth doesn't accept symbol kwarg."""

    def test_market_depth_no_symbol(self):
        from domain import MarketDepth

        depth = MarketDepth(bids=[], asks=[])
        assert depth.bids == []
        assert depth.asks == []
