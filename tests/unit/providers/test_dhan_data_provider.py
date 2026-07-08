"""Tests for DhanDataProvider — implements DataProvider port."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from domain.instruments.instrument_id import InstrumentId
from providers.dhan.data_provider import DhanDataProvider


class TestDhanDataProvider:
    """DhanDataProvider satisfies DataProvider interface."""

    def _make_provider(self, gateway=None):
        gw = gateway or MagicMock()
        return DhanDataProvider(gw)

    def test_name(self):
        provider = self._make_provider()
        assert provider.name == "dhan"

    def test_get_quote_returns_none_on_error(self):
        gw = MagicMock()
        gw.quote.side_effect = Exception("connection failed")
        provider = self._make_provider(gw)
        result = provider.get_quote(InstrumentId.equity("NSE", "RELIANCE"))
        assert result is None

    def test_get_quote_returns_snapshot(self):
        gw = MagicMock()
        gw.quote.return_value = {
            "last_price": 2450,
            "bid": 2449,
            "ask": 2451,
            "high": 2500,
            "low": 2400,
            "open": 2420,
            "close": 2480,
            "volume": 1000000,
        }
        provider = self._make_provider(gw)
        result = provider.get_quote(InstrumentId.equity("NSE", "RELIANCE"))
        assert result is not None
        assert result.ltp == Decimal("2450")

    def test_get_history_returns_empty_on_error(self):
        gw = MagicMock()
        gw.history.side_effect = Exception("timeout")
        provider = self._make_provider(gw)
        result = provider.get_history(InstrumentId.equity("NSE", "RELIANCE"))
        assert len(result) == 0

    def test_get_history_returns_dataframe(self):
        import pandas as pd

        gw = MagicMock()
        gw.history.return_value = pd.DataFrame(
            {"open": [100], "high": [110], "low": [90], "close": [105], "volume": [1000]}
        )
        provider = self._make_provider(gw)
        result = provider.get_history(
            InstrumentId.equity("NSE", "RELIANCE"), timeframe="1D", lookback_days=30
        )
        assert len(result) == 1

    def test_get_depth_returns_none_on_error(self):
        gw = MagicMock()
        gw.depth.side_effect = Exception("no depth")
        provider = self._make_provider(gw)
        result = provider.get_depth(InstrumentId.equity("NSE", "RELIANCE"))
        assert result is None

    def test_get_option_chain_returns_empty_on_error(self):
        gw = MagicMock()
        gw.option_chain.side_effect = Exception("no chain")
        provider = self._make_provider(gw)
        result = provider.get_option_chain(InstrumentId.index("NFO", "NIFTY"))
        assert result.underlying == ""

    def test_subscribe_returns_handle(self):
        gw = MagicMock()
        gw.stream.return_value = MagicMock()
        provider = self._make_provider(gw)
        handle = provider.subscribe(InstrumentId.equity("NSE", "RELIANCE"), lambda *a: None)
        assert handle.is_active

    def test_unsubscribe_deactivates_handle(self):
        gw = MagicMock()
        gw.stream.return_value = MagicMock()
        provider = self._make_provider(gw)
        handle = provider.subscribe(InstrumentId.equity("NSE", "RELIANCE"), lambda *a: None)
        provider.unsubscribe(handle)
        assert not handle.is_active
