"""MA-024 — DhanDataProvider.subscribe uses correct stream kwargs + QuoteSnapshot."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.dhan.data.data_provider import DhanDataProvider
from domain.entities.market import QuoteSnapshot
from domain.instruments.instrument_id import InstrumentId


def test_subscribe_calls_stream_with_mode_and_on_tick() -> None:
    gw = MagicMock()
    feed = MagicMock()
    feed.stop = MagicMock()
    gw.stream.return_value = feed
    gw.unstream = MagicMock()

    provider = DhanDataProvider(gw)
    iid = InstrumentId.equity("NSE", "RELIANCE")
    received: list = []

    handle = provider.subscribe(iid, lambda i, p: received.append(p))
    assert handle.is_active
    gw.stream.assert_called_once()
    kwargs = gw.stream.call_args.kwargs
    assert kwargs.get("mode") == "QUOTE"
    assert callable(kwargs.get("on_tick"))
    # positional symbol/exchange
    args = gw.stream.call_args.args
    assert args[0] == "RELIANCE"
    assert args[1] == "NSE"

    # Simulate gateway tick as Quote-like object
    tick = MagicMock()
    tick.ltp = Decimal("2500.5")
    tick.bid = Decimal("2500")
    tick.ask = Decimal("2501")
    tick.high = Decimal("2510")
    tick.low = Decimal("2490")
    tick.open = Decimal("2495")
    tick.close = Decimal("2500")
    tick.volume = 1000
    kwargs["on_tick"](tick)

    assert len(received) == 1
    assert isinstance(received[0], QuoteSnapshot)
    assert received[0].ltp == Decimal("2500.5")

    handle.unsubscribe()
    assert not handle.is_active
    gw.unstream.assert_called_once_with("RELIANCE", "NSE", on_tick=kwargs["on_tick"])


def test_subscribe_depth_mode() -> None:
    # "DEPTH" is not a real Dhan feed mode (only LTP/QUOTE/FULL — see
    # brokers.dhan.websocket._helpers._mode_map) and silently produced plain
    # quotes with bid=None/ask=None. "FULL" is the mode that actually carries
    # bid/ask, verified live.
    gw = MagicMock()
    gw.stream.return_value = MagicMock()
    provider = DhanDataProvider(gw)
    provider.subscribe(
        InstrumentId.equity("NSE", "INFY"),
        lambda *a: None,
        depth=True,
    )
    assert gw.stream.call_args.kwargs.get("mode") == "FULL"


def test_subscribe_normalizer_failure_logs(caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    gw = MagicMock()
    feed = MagicMock()
    gw.stream.return_value = feed

    provider = DhanDataProvider(gw)
    iid = InstrumentId.equity("NSE", "RELIANCE")
    received: list = []

    provider.subscribe(iid, lambda i, p: received.append(p))
    on_tick = gw.stream.call_args.kwargs["on_tick"]

    class _BrokenNormalizer:
        def _normalize_quote(self, *_a, **_k):
            raise ValueError("bad tick")

    provider._normalize_quote = _BrokenNormalizer()._normalize_quote  # type: ignore[method-assign]
    on_tick({"ltp": 1})

    assert received == []
    assert any("tick_normalize_failed" in r.message for r in caplog.records)


def test_subscribe_failure_raises() -> None:
    gw = MagicMock()
    gw.stream.side_effect = RuntimeError("no stream")
    provider = DhanDataProvider(gw)
    with pytest.raises(RuntimeError, match="no stream"):
        provider.subscribe(
            InstrumentId.equity("NSE", "SBIN"),
            lambda *a: None,
        )


def test_subscribe_normalizes_dict_tick() -> None:
    gw = MagicMock()
    gw.stream.return_value = MagicMock()
    provider = DhanDataProvider(gw)
    received: list = []
    provider.subscribe(
        InstrumentId.equity("NSE", "TCS"),
        lambda i, p: received.append(p),
    )
    on_tick = gw.stream.call_args.kwargs["on_tick"]
    on_tick({"last_price": 3500, "bid_price": 3499, "ask_price": 3501, "volume": 50})
    assert isinstance(received[0], QuoteSnapshot)
    assert received[0].ltp == Decimal("3500")
