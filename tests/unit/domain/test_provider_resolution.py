"""PR-1: provider resolution — ambient, default registry, multi-session close."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.candles.historical import HistoricalSeries, InstrumentRef
from domain.entities.market import QuoteSnapshot
from domain.errors import NotConfiguredError
from domain.instruments.instrument import Equity
from domain.ports.provider_registry import get_default_provider, set_default_provider
from domain.ports.session_context import get_ambient_session
from domain.provenance import DataProvenance, SourceIdentity
from domain.universe import Session


class _FakeProvider:
    name = "fake-a"

    def __init__(self, tag: str = "A") -> None:
        self.tag = tag
        self.name = f"fake-{tag}"

    def get_quote(self, instrument_id):
        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying, exchange=instrument_id.exchange
            ),
            ltp=Decimal("100") if self.tag == "A" else Decimal("200"),
            event_time=datetime.now(tz=timezone.utc),
            provenance=DataProvenance(
                source=SourceIdentity(broker_id=self.name),
                fetched_at=datetime.now(tz=timezone.utc),
                request_id="t",
            ),
        )

    def get_history(
        self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
    ):
        return []

    def get_history_series(
        self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
    ):
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
        from domain.entities.options import OptionChain

        uid = getattr(underlying, "underlying", None) or getattr(underlying, "symbol", "X")
        ex = getattr(underlying, "exchange", "NSE")
        return OptionChain(underlying=uid, exchange=ex, expiry="", strikes=(), spot=None)

    def get_future_chain(self, underlying):
        from domain.entities.options import FutureChain

        return FutureChain(underlying=underlying.underlying, exchange=underlying.exchange)

    def subscribe(self, instrument_id, callback, *, depth=False):
        class _S:
            is_active = True

            def unsubscribe(self):
                self.is_active = False

        return _S()

    def unsubscribe(self, subscription):
        subscription.unsubscribe()


@pytest.fixture(autouse=True)
def _clear_registry():
    set_default_provider(None)
    yield
    set_default_provider(None)


def test_bare_equity_uses_default_provider():
    set_default_provider(_FakeProvider("A"))
    eq = Equity("RELIANCE")
    q = eq.refresh()
    assert q is not None
    assert q.ltp == Decimal("100")


def test_bare_equity_raises_without_provider():
    set_default_provider(None)
    eq = Equity("RELIANCE")
    with pytest.raises(NotConfiguredError):
        eq.refresh()


def test_multi_session_close_preserves_other_provider():
    pa, pb = _FakeProvider("A"), _FakeProvider("B")
    sa = Session(pa)
    sb = Session(pb)
    assert get_default_provider() is pb
    sa.close()
    # B still owns default
    assert get_default_provider() is pb
    eq = Equity("RELIANCE")
    assert eq.refresh().ltp == Decimal("200")
    sb.close()
    assert get_default_provider() is None


def test_nested_activate_restores_ambient_and_default():
    pa, pb = _FakeProvider("A"), _FakeProvider("B")
    sa = Session(pa)
    sb = Session(pb)
    assert get_ambient_session() is sb
    with sa.activate():
        assert get_ambient_session() is sa
        assert get_default_provider() is pa
        assert Equity("X").refresh().ltp == Decimal("100")
    # Restored to B
    assert get_ambient_session() is sb
    assert get_default_provider() is pb
    sa.close()
    sb.close()


def test_history_raises_without_provider():
    set_default_provider(None)
    with pytest.raises(NotConfiguredError):
        Equity("RELIANCE").history(days=5)
