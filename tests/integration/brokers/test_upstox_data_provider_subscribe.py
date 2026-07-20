"""Upstox DataProvider.subscribe must normalize raw ticks to QuoteSnapshot."""

from __future__ import annotations

from decimal import Decimal

from brokers.upstox.data_provider import UpstoxDataProvider
from domain.entities.market import QuoteSnapshot
from domain.instruments.instrument_id import InstrumentId


class _FakeStreamHandle:
    def __init__(self) -> None:
        self.stop = lambda: None


class _FakeGateway:
    def __init__(self) -> None:
        self._on_tick = None

    def stream(self, symbol, exchange, mode=None, on_tick=None, **_kwargs):
        self._on_tick = on_tick
        return _FakeStreamHandle()

    def emit(self, raw: dict) -> None:
        assert self._on_tick is not None
        self._on_tick(raw)


def test_subscribe_normalizes_raw_dict_to_quote_snapshot() -> None:
    gw = _FakeGateway()
    provider = UpstoxDataProvider(gw)
    iid = InstrumentId.equity("NSE", "RELIANCE")
    received: list = []

    handle = provider.subscribe(iid, lambda _i, payload: received.append(payload))
    assert handle.is_active

    gw.emit(
        {
            "last_price": 2500.5,
            "bid": 2500.0,
            "ask": 2501.0,
            "volume": 1000,
            "ohlc": {"high": 2510, "low": 2490, "open": 2495, "close": 2500},
        }
    )

    assert len(received) == 1
    snap = received[0]
    assert isinstance(snap, QuoteSnapshot)
    assert snap.ltp == Decimal("2500.5")
    assert snap.instrument.symbol == "RELIANCE"
    assert snap.instrument.exchange == "NSE"
