"""Tests for QuoteStream and quotes re-exports."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain.entities.market import QuoteSnapshot
from domain.quotes import Quote, QuoteSnapshot, QuoteStream


def _make_quote(ltp: Decimal) -> QuoteSnapshot:
    return QuoteSnapshot(
        instrument=None,  # type: ignore[arg-type]
        ltp=ltp,
        event_time=datetime.now(timezone.utc),
        provenance=None,  # type: ignore[arg-type]
    )


def test_quote_reexport():
    assert Quote is not None


def test_quote_stream_append_and_latest():
    qs = QuoteStream(symbol="RELIANCE", exchange="NSE")
    qs.append(_make_quote(Decimal("2500")))
    qs.append(_make_quote(Decimal("2501")))
    assert qs.latest is not None
    assert qs.latest.ltp == Decimal("2501")
    assert qs.size == 2


def test_quote_stream_max_size():
    qs = QuoteStream(symbol="X", exchange="BSE", max_size=3)
    for i in range(5):
        qs.append(_make_quote(Decimal(str(100 + i))))
    assert qs.size == 3
    assert qs.latest.ltp == Decimal("104")


def test_quote_stream_last_n():
    qs = QuoteStream(symbol="X", exchange="BSE")
    for i in range(5):
        qs.append(_make_quote(Decimal(str(i))))
    assert len(qs.last_n(2)) == 2
    assert qs.last_n(2)[-1].ltp == Decimal("4")


def test_quote_stream_clear():
    qs = QuoteStream(symbol="X", exchange="BSE")
    qs.append(_make_quote(Decimal("1")))
    qs.clear()
    assert qs.size == 0
    assert qs.latest is None


def test_quote_stream_iter():
    qs = QuoteStream(symbol="X", exchange="BSE")
    qs.append(_make_quote(Decimal("1")))
    qs.append(_make_quote(Decimal("2")))
    prices = [q.ltp for q in qs]
    assert prices == [Decimal("1"), Decimal("2")]
