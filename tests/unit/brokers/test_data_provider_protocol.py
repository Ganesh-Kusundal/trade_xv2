"""Cross-broker DataProvider protocol conformance."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.dhan.data.data_provider import DhanDataProvider
from brokers.paper.data_provider import PaperDataProvider
from brokers.paper.paper_gateway import PaperGateway
from brokers.upstox.data_provider import UpstoxDataProvider
from domain.candles.historical import HistoricalBar
from domain.instruments.instrument_id import InstrumentId


@pytest.mark.unit
@pytest.mark.parametrize(
    "provider_factory",
    [
        lambda: PaperDataProvider(PaperGateway(initial_capital=Decimal("100000"))),
        lambda: DhanDataProvider(MagicMock()),
        lambda: UpstoxDataProvider(MagicMock()),
    ],
    ids=["paper", "dhan", "upstox"],
)
def test_get_history_returns_list_of_historical_bars(provider_factory) -> None:
    provider = provider_factory()
    if isinstance(provider, DhanDataProvider):
        provider._gw.history.return_value = __import__("pandas").DataFrame(
            {
                "timestamp": ["2024-01-01"],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
        )
    elif isinstance(provider, UpstoxDataProvider):
        provider._gw.history.return_value = __import__("pandas").DataFrame(
            {
                "timestamp": ["2024-01-01"],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
        )

    iid = InstrumentId.equity("NSE", "RELIANCE")
    bars = provider.get_history(iid, timeframe="1D", lookback_days=5)
    assert isinstance(bars, list)
    if bars:
        assert isinstance(bars[0], HistoricalBar)


@pytest.mark.unit
def test_dhan_subscribe_failure_raises() -> None:
    gw = MagicMock()
    gw.stream.side_effect = RuntimeError("stream unavailable")
    provider = DhanDataProvider(gw)
    iid = InstrumentId.equity("NSE", "RELIANCE")
    with pytest.raises(RuntimeError, match="stream unavailable"):
        provider.subscribe(iid, lambda i, p: None)


@pytest.mark.unit
def test_upstox_subscribe_failure_raises() -> None:
    gw = MagicMock(spec=[])
    provider = UpstoxDataProvider(gw)
    iid = InstrumentId.equity("NSE", "RELIANCE")
    with pytest.raises(RuntimeError, match="subscribe unsupported"):
        provider.subscribe(iid, lambda i, p: None)
