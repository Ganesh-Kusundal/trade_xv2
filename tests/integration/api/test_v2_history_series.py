"""PR-0: /v2/history serializes HistoricalSeries (not DataFrame)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from interface.api.v2 import domain_endpoints as de
from domain.candles.historical import HistoricalBar, HistoricalSeries, InstrumentRef
from domain.provenance import DataProvenance, SourceIdentity
from domain.universe import Session


class _HistProvider:
    name = "hist-fake"

    def get_quote(self, instrument_id):
        return None

    def get_history_series(
        self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
    ):
        ref = InstrumentRef(symbol=instrument_id.underlying, exchange=instrument_id.exchange)
        bar = HistoricalBar(
            instrument=ref,
            timeframe=timeframe,
            event_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10.5"),
            volume=100,
            provenance=DataProvenance(
                source=SourceIdentity(broker_id="fake"),
                fetched_at=datetime.now(tz=timezone.utc),
                request_id="h",
            ),
        )
        return HistoricalSeries(
            bars=[bar],
            coverage=None,
            instrument=ref,
            timeframe=timeframe,
        )

    def get_history(self, *a, **k):
        return []

    def get_depth(self, instrument_id):
        return None

    def get_option_chain(self, *a, **k):
        raise NotImplementedError

    def get_future_chain(self, *a, **k):
        raise NotImplementedError

    def subscribe(self, *a, **k):
        return None

    def unsubscribe(self, *a, **k):
        return None


@pytest.mark.asyncio
async def test_history_endpoint_returns_records_from_series():
    session = Session(_HistProvider())
    de.set_session(session)
    try:
        rows = await de.history(
            symbol="RELIANCE",
            timeframe="1D",
            days=5,
            exchange="NSE",
            session=session,
        )
        assert len(rows) == 1
        assert rows[0]["close"] == 10.5
        assert rows[0]["volume"] == 100
        assert "timestamp" in rows[0]
    finally:
        de.set_session(None)  # type: ignore[arg-type]
        session.close()


@pytest.mark.asyncio
async def test_history_endpoint_empty_series():
    provider = MagicMock()
    provider.get_history_series.return_value = HistoricalSeries(
        bars=[],
        coverage=None,
        instrument=InstrumentRef(symbol="X", exchange="NSE"),
        timeframe="1D",
    )
    session = Session(provider)
    de.set_session(session)
    try:
        rows = await de.history(
            symbol="X", timeframe="1D", days=1, exchange="NSE", session=session
        )
        assert rows == []
    finally:
        de.set_session(None)  # type: ignore[arg-type]
        session.close()
