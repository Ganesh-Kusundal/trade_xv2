"""Regression/contract tests for UpstoxDataProvider.subscribe (Defect R8).

Covers the two P0 subscribe-path defects:

1. Argument mapping — ``subscribe`` must call the gateway's actual
   ``stream(symbol, exchange, mode, on_tick)`` signature with the correct
   positional mapping (underlying -> symbol, exchange -> exchange, depth flag
   -> mode, callback -> on_tick) and a *valid* mode string
   (``"ltpc"`` / ``"full"``, never the invalid ``"LTP"``).

2. No swallowed exceptions — a gateway error must propagate (not be hidden
   behind a silent empty handle), and when the gateway exposes no streaming
   method the failure must be raised rather than returning a dead handle.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain.instruments.instrument_id import InstrumentId
from brokers.upstox.data_provider import UpstoxDataProvider


def _instrument(exchange: str = "NSE", underlying: str = "RELIANCE") -> InstrumentId:
    return InstrumentId.equity(exchange, underlying)


class _Gateway:
    """Minimal gateway double recording stream calls."""

    def __init__(self, stream_side_effect: Exception | None = None) -> None:
        self.stream = MagicMock(side_effect=stream_side_effect)
        self.stream_depth = MagicMock()
        # A handle-like object returned by stream().
        self._handle = MagicMock()
        self._handle.stop = MagicMock()
        self.stream.return_value = self._handle


def test_subscribe_calls_stream_with_correct_args_ltp() -> None:
    gw = _Gateway()
    provider = UpstoxDataProvider(gw)
    iid = _instrument()
    received: list[object] = []

    provider.subscribe(iid, lambda i, raw: received.append(raw))

    # stream(symbol, exchange, mode, on_tick) — positional mapping.
    gw.stream.assert_called_once()
    args, kwargs = gw.stream.call_args
    assert args[0] == "RELIANCE"          # symbol <- underlying
    assert args[1] == "NSE"              # exchange
    assert args[2] == "ltpc"             # mode for depth=False
    assert callable(args[3])             # on_tick callback
    assert kwargs == {}                  # no stray kwargs
    # stream_depth must NOT be used for non-depth subscribe.
    gw.stream_depth.assert_not_called()


def test_subscribe_calls_stream_depth_with_full_mode_for_depth() -> None:
    gw = _Gateway()
    provider = UpstoxDataProvider(gw)
    iid = _instrument()

    provider.subscribe(iid, lambda i, raw: None, depth=True)

    # depth=True prefers stream_depth over the plain LTP stream.
    gw.stream_depth.assert_called_once()
    args, _ = gw.stream_depth.call_args
    assert args[0] == "RELIANCE"
    assert args[1] == "NSE"
    assert callable(args[2])             # on_depth callback
    gw.stream.assert_not_called()


def test_subscribe_returns_active_handle_with_stop() -> None:
    gw = _Gateway()
    provider = UpstoxDataProvider(gw)
    iid = _instrument()

    handle = provider.subscribe(iid, lambda i, raw: None)

    assert handle.is_active
    handle.unsubscribe()
    gw._handle.stop.assert_called_once()


def test_subscribe_propagates_gateway_error() -> None:
    boom = RuntimeError("websocket connect failed")
    gw = _Gateway(stream_side_effect=boom)
    provider = UpstoxDataProvider(gw)
    iid = _instrument()

    with pytest.raises(RuntimeError):
        provider.subscribe(iid, lambda i, raw: None)

    # The gateway was actually attempted (not silently skipped).
    gw.stream.assert_called_once()


def test_subscribe_raises_when_gateway_has_no_stream_method() -> None:
    """No silent empty handle when streaming is unsupported."""
    gw: object = object()  # exposes neither stream nor stream_depth
    provider = UpstoxDataProvider(gw)
    iid = _instrument()

    with pytest.raises(RuntimeError):
        provider.subscribe(iid, lambda i, raw: None)
