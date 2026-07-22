"""Tests for the BrokerAdapter unified protocol (Phase 9.1)."""

from __future__ import annotations

from typing import Protocol

from domain.ports.broker_adapter import BrokerAdapter
from domain.ports.protocols import DataProvider, ExecutionProvider


from abc import ABC


def test_broker_adapter_is_abc():
    """BrokerAdapter must be an ABC."""
    assert issubclass(BrokerAdapter, ABC)


def test_trivial_adapter_satisfies_isinstance():
    """A class implementing DataProvider + ExecutionProvider + lifecycle passes."""

    class FakeInstrument:
        pass

    class TrivialAdapter(BrokerAdapter):
        __abstractmethods__ = set()
        broker_id = "fake"
        is_connected = True

        @property
        def name(self) -> str:
            return self.broker_id

        def get_quote(self, instrument_id):
            return None

        def get_history(
            self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
        ):
            import pandas as pd

            return pd.DataFrame()

        def get_history_series(
            self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
        ):
            from domain.candles.historical import HistoricalSeries, InstrumentRef

            return HistoricalSeries(
                bars=[],
                coverage=None,
                instrument=InstrumentRef(
                    symbol=instrument_id.underlying, exchange=instrument_id.exchange
                ),
                timeframe=timeframe,
            )

        def get_depth(self, instrument_id):
            return None

        def get_option_chain(self, underlying, *, expiry=None):
            return None

        def get_future_chain(self, underlying):
            return None

        def subscribe(self, instrument_id, callback, *, depth=False):
            return None

        def unsubscribe(self, subscription):
            return None

        def history_batch(self, instrument_ids, *, timeframe="1D", lookback_days=120):
            import pandas as pd

            return pd.DataFrame()

        def list_instruments(self, exchange=None):
            return []

        def get_quotes_batch(self, instrument_ids):
            return []

        def place_order(self, request):
            return None

        def cancel_order(self, order_id):
            return None

        def modify_order(self, request):
            return None

        def get_order_book(self):
            return []

        def get_positions(self):
            return []

        def get_holdings(self):
            return []

        def get_funds(self):
            return None

        def authenticate(self) -> bool:
            return True

        def close(self) -> None:
            return None

    TrivialAdapter.__abstractmethods__ = frozenset()
    obj = TrivialAdapter()
    assert isinstance(obj, BrokerAdapter)
    assert isinstance(obj, DataProvider)
    assert isinstance(obj, ExecutionProvider)
