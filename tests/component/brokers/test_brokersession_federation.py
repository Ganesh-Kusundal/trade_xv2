"""Zero-parity check: BrokerSession.history() uses the federated coordinator.

This is the missing regression guard for F-1 (silent truncation). Before
convergence, ``BrokerSession.history()`` went through ``HistoryPipeline`` which
counted failed chunks but emitted no ``Gap`` and derived coverage only from
returned bars — so a partial fetch looked complete over a shortened range.

These tests assert the new contract:
  * coverage spans the FULL requested range (chunking honoured), and
  * a mid-range chunk failure yields ``series.is_degraded == True`` and
    ``len(series.gaps) > 0`` (explicit, not silent).

Uses real components (a non-mock gateway wrapped by MarketDataGatewayAdapter),
not behaviour mocks.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from brokers.providers.dhan.config.capabilities import dhan_capabilities
from brokers.session.broker_session import BrokerSession
from domain.ports.broker_gateway import HistoricalBarRequest


@pytest.fixture
def dhan_caps():
    return dhan_capabilities()


class _RealGateway:
    """Real (non-mock) gateway honouring the wire adapter contract."""

    def __init__(self, caps) -> None:
        self._caps = caps

    def capabilities(self):
        return self._caps

    def history(
        self, symbol, exchange="NSE", timeframe="1D", lookback_days=90, from_date=None, to_date=None
    ):
        from datetime import date, timedelta

        import pandas as pd

        start = date.fromisoformat(from_date) if from_date else date.today()
        end = date.fromisoformat(to_date) if to_date else date.today()
        n = (end - start).days + 1
        dates = [start + timedelta(days=i) for i in range(n)]
        return pd.DataFrame(
            {
                "timestamp": dates,
                "open": [100.0] * n,
                "high": [101.0] * n,
                "low": [99.0] * n,
                "close": [100.5] * n,
                "volume": [1000] * n,
                "symbol": symbol,
                "exchange": exchange,
                "timeframe": timeframe,
            }
        )


def _make_session(broker_id, caps, gw):
    sess = BrokerSession.__new__(BrokerSession)
    sess._broker_id = broker_id
    sess._runtime = None
    provider = type("P", (), {"_gw": gw})()
    domain_session = type("DS", (), {"provider": provider})()
    sess._session = domain_session
    return sess


class TestBrokerSessionFederation:
    def test_coverage_spans_full_requested_range(self, dhan_caps):
        gw = _RealGateway(dhan_caps)
        session = _make_session("dhan", dhan_caps, gw)
        instrument = type("I", (), {"symbol": "RELIANCE", "exchange": "NSE"})()

        series = session.history(instrument, timeframe="1m", days=200)
        assert series.bar_count > 0
        # 200-day 1m request must NOT silently collapse to a shortened window.
        assert (series.coverage.end - series.coverage.start).days >= 199

    def test_middle_chunk_failure_is_explicit_not_silent(self, dhan_caps):
        # 1m max_chunk_days=90 -> 200d splits into 3 chunks (90+90+20).
        # Fail the MIDDLE chunk (the 2nd planned chunk's from_date).
        today = _dt.date(2026, 7, 17)
        gw = _RealGateway(dhan_caps)

        session = _make_session("dhan", dhan_caps, gw)
        base_build = session._build_historical_coordinator

        def _failing_build():
            coord = base_build()
            # Derive the ACTUAL middle chunk date from the planner so we fail
            # the right window (not a guessed one).
            from application.data.historical_coordinator import HistoricalQuery

            q = HistoricalQuery(
                instrument=__import__(
                    "domain.candles.historical", fromlist=["InstrumentRef"]
                ).InstrumentRef(symbol="RELIANCE", exchange="NSE"),
                timeframe="1m",
                from_date=today - _dt.timedelta(days=200),
                to_date=today,
                request_id="fed-mid",
            )
            chunks = coord._planner.plan(q, q.request_id)
            assert len(chunks) >= 3
            middle_from = chunks[1].from_date.isoformat()

            real_adapter = coord._registry.get_gateway("dhan")

            async def _failing_bars(request: HistoricalBarRequest, *, quota):
                if request.from_date == middle_from:
                    raise RuntimeError("simulated mid-range broker outage")
                return await real_adapter.get_historical_bars(request, quota=quota)

            coord._registry._gateways["dhan"] = _FailingAdapter(real_adapter, _failing_bars)
            return coord

        session._build_historical_coordinator = _failing_build

        instrument = type("I", (), {"symbol": "RELIANCE", "exchange": "NSE"})()
        series = session.history(instrument, timeframe="1m", days=200)

        # F-1 regression: degradation must be explicit, not hidden.
        assert series.is_degraded is True
        assert len(series.gaps) > 0
        # The failed middle window must appear as an explicit gap inside the
        # requested range (not silently collapsed into a shortened coverage).
        gap_starts = [g.start for g in series.gaps]
        assert any(today - _dt.timedelta(days=200) <= s <= today for s in gap_starts)


class _FailingAdapter:
    """Adapter wrapper that can raise for a targeted window."""

    def __init__(self, wrapped, fn) -> None:
        self._wrapped = wrapped
        self._fn = fn
        self._broker_id = wrapped.broker_id

    @property
    def broker_id(self) -> str:
        return self._broker_id

    def list_capabilities(self):
        return self._wrapped.list_capabilities()

    def supports(self, feature: str) -> bool:
        return self._wrapped.supports(feature)

    async def get_historical_bars(self, request, *, quota):
        return await self._fn(request, quota=quota)
