"""Contract test: every DataProvider plugin must satisfy this shared contract.

Subclass ``_DataProviderContract`` (prefix ``_`` so pytest does not collect the
base) and implement ``build_provider`` returning a concrete provider seeded
with one quote. The inherited tests then prove the provider conforms to the
domain's data-access contract — the basis for broker/CSV/replay parity.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.instruments.instrument_id import InstrumentId
from domain.tests._fakes import FakeProvider, make_quote


class _DataProviderContract:
    """Shared DataProvider conformance contract (not collected directly)."""

    def build_provider(self) -> FakeProvider:
        raise NotImplementedError

    def test_get_quote_returns_snapshot(self) -> None:
        provider = self.build_provider()
        iid = InstrumentId.equity("NSE", "RELIANCE")
        quote = provider.get_quote(iid)
        assert quote is not None
        assert quote.ltp == Decimal("2500")

    def test_get_history_returns_ohlcv(self) -> None:
        provider = self.build_provider()
        iid = InstrumentId.equity("NSE", "RELIANCE")
        df = provider.get_history(iid, timeframe="5m")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns

    def test_get_depth_returns_ladder(self) -> None:
        provider = self.build_provider()
        iid = InstrumentId.equity("NSE", "RELIANCE")
        depth = provider.get_depth(iid)
        assert depth is not None
        assert depth.bids and depth.asks

    def test_subscribe_returns_active_handle(self) -> None:
        provider = self.build_provider()
        iid = InstrumentId.equity("NSE", "RELIANCE")
        sub = provider.subscribe(iid, lambda iid, q: None)
        assert sub is not None
        assert sub.is_active is True

    def test_unsubscribe_deactivates(self) -> None:
        provider = self.build_provider()
        iid = InstrumentId.equity("NSE", "RELIANCE")
        sub = provider.subscribe(iid, lambda iid, q: None)
        provider.unsubscribe(sub)
        assert sub.is_active is False


class TestFakeProviderContract(_DataProviderContract):
    def build_provider(self) -> FakeProvider:
        fp = FakeProvider()
        fp.seed_quote("RELIANCE", "NSE", Decimal("2500"))
        fp.seed_depth("RELIANCE", "NSE")
        return fp
