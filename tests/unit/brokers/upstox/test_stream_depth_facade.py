"""UpstoxWireAdapter.stream_depth(levels=...) — canonical depth-level dispatch.

Mirrors the Dhan facade test (tests/unit/brokers/dhan/test_stream_depth_facade.py)
so both gateways can be driven by the same call shape. Reuses the
``_make_gateway``/``_MockWebsocket`` fixtures from test_gateway_stream.py.
"""

from __future__ import annotations

import pytest

from brokers.common.streaming import DepthStreamHandle
from tests.unit.brokers.upstox.test_gateway_stream import _make_gateway


def test_stream_depth_levels_5_uses_full_mode():
    gateway, ws, _broker = _make_gateway(connected=True)

    handle = gateway.stream_depth("INFY", exchange="NSE", levels=5)

    assert isinstance(handle, DepthStreamHandle)
    assert handle.initial is None
    assert len(ws.subscribed) == 1
    _keys, mode = ws.subscribed[0]
    assert mode == "full"


def test_stream_depth_levels_30_uses_full_d30_mode():
    gateway, ws, _broker = _make_gateway(connected=True)

    handle = gateway.stream_depth("INFY", exchange="NSE", levels=30)

    assert isinstance(handle, DepthStreamHandle)
    assert len(ws.subscribed) == 1
    _keys, mode = ws.subscribed[0]
    assert mode == "full_d30"


def test_stream_depth_unsupported_level_raises():
    gateway, _ws, _broker = _make_gateway(connected=True)

    with pytest.raises(ValueError, match="Upstox supports depth levels"):
        gateway.stream_depth("INFY", exchange="NSE", levels=20)


def test_stream_depth_legacy_depth_type_still_works():
    """Back-compat: existing depth_type= callers (verify scripts, extensions) unaffected."""
    gateway, ws, _broker = _make_gateway(connected=True)

    gateway.stream_depth("INFY", exchange="NSE", depth_type="DEPTH_30")

    _keys, mode = ws.subscribed[0]
    assert mode == "full_d30"
