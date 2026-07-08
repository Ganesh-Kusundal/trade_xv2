"""Unit tests for the Universe / Session public facade (composition root)."""

from __future__ import annotations

from datetime import date

from domain.instruments.instrument import Equity, Future, Index, Option
from domain.tests._fakes import FakeEventBus, FakeProvider
from domain.universe import Session, Universe


def _new_session() -> tuple[Session, FakeProvider, FakeEventBus]:
    bus = FakeEventBus()
    fp = FakeProvider()
    fp.seed_quote("RELIANCE", "NSE", __import__("decimal").Decimal("2500"))
    session = Session(fp, event_bus=bus)
    return session, fp, bus


def test_session_exposes_universe():
    session, _, _ = _new_session()
    assert isinstance(session.universe, Universe)
    assert session.provider.name == "fake"


def test_universe_builds_equity():
    session, _, _ = _new_session()
    eq = session.universe.equity("RELIANCE")
    assert isinstance(eq, Equity)
    assert eq.symbol == "RELIANCE"
    assert eq.exchange == "NSE"


def test_universe_builds_index():
    session, _, _ = _new_session()
    idx = session.universe.index("NIFTY")
    assert isinstance(idx, Index)
    assert idx.symbol == "NIFTY"


def test_universe_builds_future():
    session, _, _ = _new_session()
    fut = session.universe.future("NIFTY", expiry=date(2026, 7, 31))
    assert isinstance(fut, Future)
    assert fut.expiry == date(2026, 7, 31)


def test_universe_builds_option():
    session, _, _ = _new_session()
    opt = session.universe.option("RELIANCE", __import__("decimal").Decimal("2500"), "CE",
                                  expiry=date(2026, 7, 31))
    assert isinstance(opt, Option)
    assert opt.strike == __import__("decimal").Decimal("2500")
    assert opt.is_call is True


def test_session_close_clears_default_provider():
    session, _, _ = _new_session()
    session.close()
    from domain.ports.provider_registry import get_default_provider

    assert get_default_provider() is None
