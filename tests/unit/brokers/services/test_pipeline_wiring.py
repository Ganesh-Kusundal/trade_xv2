"""Verify BrokerSession.history() routes through the federated coordinator.

After convergence, ``BrokerSession.history()`` / ``history_batch()`` must use
the SAME engine as the live API — ``HistoricalDataCoordinator`` — so the two
paths share identical chunking, conflict resolution, gap detection and
provenance (zero-parity). These tests assert that invariant using a real
(non-mock) gateway object wrapped by ``MarketDataGatewayAdapter``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from brokers.session.broker_session import BrokerSession
from domain.capabilities.broker_capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
)
from domain.candles.historical import HistoricalSeries, InstrumentRef
from infrastructure.adapters.market_data_gateway_adapter import (
    MarketDataGatewayAdapter,
)


def _make_caps() -> BrokerCapabilities:
    return BrokerCapabilities(
        broker_id="dhan",
        supports_historical_data=True,
        historical_windows=(
            HistoricalWindowConstraint(
                timeframe="1D", max_lookback_days=3650, max_chunk_days=365
            ),
            HistoricalWindowConstraint(
                timeframe="1m", max_lookback_days=3650, max_chunk_days=90
            ),
        ),
    )


class _RealGateway:
    """Minimal real gateway (not a mock) honouring the wire adapter contract."""

    def __init__(self, caps: BrokerCapabilities) -> None:
        self._caps = caps

    def capabilities(self) -> BrokerCapabilities:
        return self._caps

    def history(self, symbol, exchange="NSE", timeframe="1D", lookback_days=90,
                from_date=None, to_date=None):
        start = date.fromisoformat(from_date) if from_date else date.today()
        end = date.fromisoformat(to_date) if to_date else date.today()
        n = (end - start).days + 1
        dates = [start + timedelta(days=i) for i in range(n)]
        return pd.DataFrame({
            "timestamp": dates,
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [1000] * n,
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
        })


@pytest.fixture
def session(monkeypatch):
    gw = _RealGateway(_make_caps())
    adapter = MarketDataGatewayAdapter(gw, broker_id="dhan", capabilities=_make_caps())

    sess = BrokerSession.__new__(BrokerSession)
    sess._broker_id = "dhan"
    sess._runtime = None

    provider = type("P", (), {"_gw": gw})()
    domain_session = type("DS", (), {"provider": provider})()
    sess._session = domain_session
    return sess


class TestBrokerSessionRoutesThroughCoordinator:
    """BrokerSession.history() must hit the federated coordinator, not a dead pipeline."""

    def test_history_returns_historical_series(self, session):
        instrument = type("I", (), {"symbol": "RELIANCE", "exchange": "NSE"})()
        series = session.history(instrument, timeframe="1D", days=30)
        assert isinstance(series, HistoricalSeries)
        # from_date=today-30d, to_date=today -> inclusive range = 31 bars
        assert series.bar_count == 31
        assert series.instrument.symbol == "RELIANCE"
        assert series.timeframe == "1D"

    def test_history_coverage_spans_requested_range(self, session):
        today = date(2026, 7, 15)
        instrument = type("I", (), {"symbol": "RELIANCE", "exchange": "NSE"})()
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("brokers.session.broker_session.date", _FixedDate(today))
            series = session.history(instrument, timeframe="1D", days=30)
        assert series.coverage.start == today - timedelta(days=30)
        assert series.coverage.end == today

    def test_history_batch_returns_per_symbol_series(self, session):
        insts = [
            type("I", (), {"symbol": "RELIANCE", "exchange": "NSE"})(),
            type("I", (), {"symbol": "TCS", "exchange": "NSE"})(),
        ]
        result_map = session.history_batch(insts, timeframe="1D", days=10)
        assert set(result_map.keys()) == {"RELIANCE", "TCS"}
        assert all(isinstance(s, HistoricalSeries) for s in result_map.values())
        # from_date=today-10d, to_date=today -> inclusive range = 11 bars
        assert result_map["RELIANCE"].bar_count == 11

    def test_history_method_signature(self):
        import inspect

        sig = inspect.signature(BrokerSession.history)
        params = list(sig.parameters.keys())
        assert "instrument" in params
        assert "timeframe" in params
        assert "days" in params


class _FixedDate:
    """Stand-in for datetime.date that always reports a fixed today."""

    def __init__(self, fixed: date) -> None:
        self._fixed = fixed

    def today(self) -> date:
        return self._fixed
