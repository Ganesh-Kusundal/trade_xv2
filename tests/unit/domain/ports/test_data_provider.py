"""Tests for DataProvider port — verifying interface contract."""

from __future__ import annotations

import pytest

from domain.ports.data_provider import DataProvider


class TestDataProviderInterface:
    """DataProvider must be abstract with required methods."""

    def test_cannot_instantiate_directly(self):
        """DataProvider is abstract — cannot be instantiated."""
        with pytest.raises(TypeError):
            DataProvider()

    def test_has_name_property(self):
        """DataProvider must have a name property."""
        assert hasattr(DataProvider, "name")

    def test_has_get_quote_method(self):
        """DataProvider must have get_quote method."""
        assert hasattr(DataProvider, "get_quote")

    def test_has_get_history_method(self):
        """DataProvider must have get_history method."""
        assert hasattr(DataProvider, "get_history")

    def test_has_get_depth_method(self):
        """DataProvider must have get_depth method."""
        assert hasattr(DataProvider, "get_depth")

    def test_has_get_option_chain_method(self):
        """DataProvider must have get_option_chain method."""
        assert hasattr(DataProvider, "get_option_chain")

    def test_has_get_future_chain_method(self):
        """DataProvider must have get_future_chain method."""
        assert hasattr(DataProvider, "get_future_chain")

    def test_has_subscribe_method(self):
        """DataProvider must have subscribe method."""
        assert hasattr(DataProvider, "subscribe")

    def test_has_unsubscribe_method(self):
        """DataProvider must have unsubscribe method."""
        assert hasattr(DataProvider, "unsubscribe")

    def test_concrete_implementation_works(self):
        """A minimal concrete implementation should satisfy the interface."""
        from unittest.mock import MagicMock

        from domain.instruments.instrument_id import InstrumentId

        class MockProvider(DataProvider):
            @property
            def name(self) -> str:
                return "mock"

            def get_quote(self, instrument_id):
                return None

            def get_history(self, instrument_id, **kwargs):
                import pandas as pd

                return pd.DataFrame()

            def get_depth(self, instrument_id):
                return None

            def get_option_chain(self, underlying, **kwargs):
                from domain.entities.options import OptionChain

                return OptionChain(underlying="", exchange="", expiry="")

            def get_future_chain(self, underlying):
                from domain.entities.options import FutureChain

                return FutureChain(underlying="", exchange="")

            def subscribe(self, instrument_id, callback, **kwargs):
                return MagicMock()

            def unsubscribe(self, handle):
                pass

        provider = MockProvider()
        assert provider.name == "mock"
        assert provider.get_quote(InstrumentId.equity("NSE", "RELIANCE")) is None
