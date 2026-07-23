"""Upstox depth extension delegation tests (mirrors Dhan)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.entities import DepthLevel, MarketDepth
from domain.value_objects import InstrumentId, Price, Quantity
from plugins.brokers.upstox.extensions import UpstoxDepth20Extension


class _FakeStreaming:
    def __init__(self) -> None:
        self.calls: list[tuple[InstrumentId, Any]] = []

    def stream_depth(
        self, instrument_id: InstrumentId, on_depth: Any = None
    ) -> MarketDepth | None:
        self.calls.append((instrument_id, on_depth))
        return MarketDepth(
            instrument_id=instrument_id,
            bids=(DepthLevel(price=Price(value=Decimal("1272.0")), quantity=Quantity(value=Decimal("100"))),),
            asks=(),
            timestamp=datetime.now(),
        )


def test_upstox_depth_extension_delegates_to_streaming() -> None:
    fake = _FakeStreaming()
    ext = UpstoxDepth20Extension(_streaming=fake)
    iid = InstrumentId.parse("NSE:RELIANCE")

    captured: list[MarketDepth] = []
    result = ext.full_depth(iid, on_depth=captured.append)
    assert result is not None
    assert len(result.bids) == 1
    # stream_depth was invoked with the same instrument and a working callback.
    assert fake.calls[0][0] == iid
    cb = fake.calls[0][1]
    assert callable(cb)
    cb(result)  # exercise the callback path
    assert len(captured) == 1
    assert captured[0] is result


def test_upstox_depth_extension_no_streaming_returns_none() -> None:
    ext = UpstoxDepth20Extension(_streaming=None)
    assert ext.full_depth(InstrumentId.parse("NSE:RELIANCE")) is None
