"""C0.7b — UpstoxDataProvider.subscribe uses gateway.stream kwargs correctly."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain.instruments.instrument_id import InstrumentId


@pytest.mark.unit
def test_subscribe_calls_stream_with_mode_and_on_tick() -> None:
    from brokers.upstox.data_provider import UpstoxDataProvider

    gw = MagicMock()
    handle = MagicMock()
    handle.stop = MagicMock()
    gw.stream = MagicMock(return_value=handle)

    provider = UpstoxDataProvider(gw)
    iid = InstrumentId(exchange="NSE", underlying="RELIANCE", kind="EQUITY")
    cb = MagicMock()

    sub = provider.subscribe(iid, cb, depth=False)

    gw.stream.assert_called_once()
    args, kwargs = gw.stream.call_args
    assert args[0] == "RELIANCE"
    assert args[1] == "NSE"
    assert args[2] == "ltpc"
    assert callable(args[3])
    # callback adapter receives raw tick
    args[3]({"ltp": 1})
    cb.assert_called()
    assert sub is not None


@pytest.mark.unit
def test_subscribe_does_not_pass_callback_as_mode() -> None:
    from brokers.upstox.data_provider import UpstoxDataProvider

    gw = MagicMock()
    gw.stream = MagicMock(return_value=MagicMock())
    provider = UpstoxDataProvider(gw)
    iid = InstrumentId(exchange="NSE", underlying="TCS", kind="EQUITY")
    provider.subscribe(iid, lambda *_a, **_k: None)
    args, kwargs = gw.stream.call_args
    # Mode is the third positional; user callback is fourth — never conflated.
    assert len(args) == 4
    assert args[2] == "ltpc"
    assert callable(args[3])
    assert "on_tick" not in kwargs


@pytest.mark.unit
def test_subscribe_raises_on_stream_failure() -> None:
    from brokers.upstox.data_provider import UpstoxDataProvider

    gw = MagicMock()
    gw.stream = MagicMock(side_effect=RuntimeError("ws down"))
    provider = UpstoxDataProvider(gw)
    iid = InstrumentId(exchange="NSE", underlying="INFY", kind="EQUITY")
    with pytest.raises(RuntimeError, match="ws down"):
        provider.subscribe(iid, lambda *_a, **_k: None)
