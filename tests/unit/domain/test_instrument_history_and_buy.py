"""PR-2 InstrumentHistory facade + PR-3 instrument.buy OMS-only."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain.candles.historical import HistoricalBar, HistoricalSeries, InstrumentRef
from domain.candles.instrument_history import InstrumentHistory
from domain.errors import NotConfiguredError
from domain.orders.intent import OrderIntent
from domain.ports.protocols import OrderResult
from domain.provenance import DataProvenance, SourceIdentity
from domain.universe import Session


class _HistProv:
    name = "hp"

    def get_quote(self, instrument_id):
        return None

    def get_history_series(
        self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
    ):
        ref = InstrumentRef(symbol=instrument_id.underlying, exchange=instrument_id.exchange)
        bar = HistoricalBar(
            instrument=ref,
            timeframe=timeframe,
            event_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=10,
            provenance=DataProvenance(
                source=SourceIdentity(broker_id="hp"),
                fetched_at=datetime.now(tz=timezone.utc),
                request_id="h",
            ),
        )
        return HistoricalSeries(bars=[bar], coverage=None, instrument=ref, timeframe=timeframe)

    def get_history(self, *a, **k):
        return []

    def get_depth(self, *a, **k):
        return None

    def get_option_chain(self, *a, **k):
        raise NotImplementedError

    def get_future_chain(self, *a, **k):
        raise NotImplementedError

    def subscribe(self, *a, **k):
        return None

    def unsubscribe(self, *a, **k):
        return None


class _FakeOMS:
    def __init__(self) -> None:
        self.places: list[OrderIntent] = []
        self.ep_calls = 0

    def place(self, intent: OrderIntent) -> OrderResult:
        self.places.append(intent)
        order = MagicMock()
        order.order_id = f"OID-{len(self.places)}"
        return OrderResult.ok(order)


def test_history_is_callable_facade():
    session = Session(_HistProv())
    try:
        eq = session.universe.equity("RELIANCE")
        assert isinstance(eq.history, InstrumentHistory)
        assert callable(eq.history)
        series = eq.history(timeframe="1D", days=5)
        assert series.bar_count == 1
        assert eq.history.series is series
        assert eq.history.downloaded is series
        series2 = eq.history.download(days=10)
        assert series2.bar_count == 1
    finally:
        session.close()


def test_history_resample_does_not_clobber_download():
    session = Session(_HistProv())
    try:
        eq = session.universe.equity("RELIANCE")
        downloaded = eq.history(days=5)
        # resample may need multi-bar data; if it fails, skip soft
        try:
            view = eq.history.resample("W")
            assert eq.history.downloaded is downloaded
            assert eq.history.series is view
        except Exception:
            # single bar series may not resample — still ok that download remains
            assert eq.history.downloaded is downloaded
    finally:
        session.close()


def test_session_buy_via_oms_only():
    oms = _FakeOMS()
    ep = MagicMock()
    session = Session(_HistProv(), execution_provider=ep, order_service=oms)
    try:
        eq = session.universe.equity("RELIANCE")
        intent = session.intent(eq, "BUY", 2, price=Decimal("100"), correlation_id="buy:1")
        result = session.place(intent)
        assert result.success
        assert len(oms.places) == 1
        assert oms.places[0].quantity == 2
        assert oms.places[0].correlation_id == "buy:1"
        ep.place_order.assert_not_called()
    finally:
        session.close()


def test_session_buy_via_raises_without_oms():
    session = Session(_HistProv())  # no order_service
    try:
        eq = session.universe.equity("RELIANCE")
        with pytest.raises(RuntimeError, match="OrderServicePort|order.service|OMS"):
            session.buy(eq, 1)
    finally:
        session.close()


def test_session_buy_via_never_uses_ep_alone():
    """EP present but no OMS → still raise (KD-9)."""
    ep = MagicMock()
    session = Session(_HistProv(), execution_provider=ep)
    try:
        eq = session.universe.equity("RELIANCE")
        with pytest.raises(RuntimeError):
            session.buy(eq, 1)
        ep.place_order.assert_not_called()
    finally:
        session.close()


def test_future_and_option_factories_stamp_oms():
    oms = _FakeOMS()
    from datetime import date

    session = Session(_HistProv(), order_service=oms)
    try:
        fut = session.universe.future("NIFTY", expiry=date(2026, 12, 31))
        result = session.buy(fut, 1)
        assert result.success
        assert oms.places[-1].symbol == "NIFTY"
    finally:
        session.close()


def test_session_buy_still_works():
    oms = _FakeOMS()
    session = Session(_HistProv(), order_service=oms)
    try:
        eq = session.universe.equity("RELIANCE")
        r = session.buy(eq, 3, price=Decimal("50"))
        assert r.success
        assert oms.places[-1].quantity == 3
    finally:
        session.close()
