"""Lake vs live-broker candle endpoints must emit equivalent wire OHLCV (ADR-020)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from domain.candles.historical import (
    DateRange,
    HistoricalBar,
    HistoricalSeries,
    InstrumentRef,
)
from domain.provenance import DataProvenance
from interface.api import deps
from interface.api.config import APIConfig
from interface.api.main import create_app

_IST = ZoneInfo("Asia/Kolkata")
_SYMBOL = "RELIANCE"
_EXCHANGE = "NSE"
_TIMEFRAME = "1m"

# Same session window: 2026-01-15 09:15–09:17 IST → 03:45–03:47 UTC
_BAR_SPECS = (
    (100.0, 101.0, 99.0, 100.5, 1000),
    (100.5, 102.0, 100.0, 101.0, 1100),
    (101.0, 103.0, 100.5, 102.0, 1200),
)
_IST_TIMES = (
    datetime(2026, 1, 15, 9, 15, tzinfo=_IST),
    datetime(2026, 1, 15, 9, 16, tzinfo=_IST),
    datetime(2026, 1, 15, 9, 17, tzinfo=_IST),
)


def _utc_times() -> list[datetime]:
    return [t.astimezone(timezone.utc) for t in _IST_TIMES]


def _lake_dataframe() -> pd.DataFrame:
    """Datalake stores naive IST timestamps."""
    rows = []
    for ist, (o, h, l, c, v) in zip(_IST_TIMES, _BAR_SPECS):
        rows.append(
            {
                "timestamp": ist.replace(tzinfo=None),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": float(v),
            }
        )
    return pd.DataFrame(rows)


def _broker_series() -> HistoricalSeries:
    ref = InstrumentRef(symbol=_SYMBOL, exchange=_EXCHANGE)
    bars: list[HistoricalBar] = []
    for utc, (o, h, l, c, v) in zip(_utc_times(), _BAR_SPECS):
        bars.append(
            HistoricalBar(
                instrument=ref,
                timeframe=_TIMEFRAME,
                event_time=utc,
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(l)),
                close=Decimal(str(c)),
                volume=int(v),
                provenance=DataProvenance.now("test-broker", "parity"),
            )
        )
    return HistoricalSeries(
        bars=bars,
        coverage=DateRange(date(2026, 1, 15), date(2026, 1, 15)),
        instrument=ref,
        timeframe=_TIMEFRAME,
    )


class _ParityLakeGateway:
    def query_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        from_ts=None,
        to_ts=None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        df = _lake_dataframe()
        if from_ts is not None:
            df = df[df["timestamp"] >= from_ts.tz_localize(None)]
        if to_ts is not None:
            df = df[df["timestamp"] <= to_ts.tz_localize(None)]
        if limit is not None and limit > 0:
            df = df.head(limit)
        return df.reset_index(drop=True)


@dataclass
class _MockLedger:
    request_id: str = "parity-req"
    degraded: bool = False
    issues: list[str] = field(default_factory=list)
    sources: list[object] = field(default_factory=list)


class _ParityComposer:
    async def fetch_historical(self, query) -> tuple[HistoricalSeries, _MockLedger]:
        return _broker_series(), _MockLedger(
            sources=[type("Src", (), {"broker_id": "test-broker", "bar_count": 3, "is_primary": True})()]
        )


@pytest.fixture(autouse=True)
def _reset_container():
    deps._container = None
    yield
    deps._container = None


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        config=APIConfig(auth_mode="none"),
        datalake_gateway=_ParityLakeGateway(),
        market_data_composer=_ParityComposer(),
    )
    return TestClient(app)


def _wire_candle_dicts(payload: dict) -> list[dict]:
    return [
        {
            "t": c["t"],
            "o": c["o"],
            "h": c["h"],
            "l": c["l"],
            "c": c["c"],
            "v": c["v"],
        }
        for c in payload["candles"]
    ]


def test_lake_and_live_candles_emit_equivalent_wire_shape(client: TestClient) -> None:
    """``/market/candles`` (IST lake) and ``/market/live/candles`` (UTC broker) align."""
    lake_resp = client.get(
        "/api/v1/market/candles",
        params={
            "symbol": _SYMBOL,
            "exchange": _EXCHANGE,
            "timeframe": _TIMEFRAME,
            "limit": 3,
        },
    )
    assert lake_resp.status_code == 200, lake_resp.text

    live_resp = client.get(
        "/api/v1/market/live/candles",
        params={
            "symbol": _SYMBOL,
            "exchange": _EXCHANGE,
            "timeframe": _TIMEFRAME,
            "from_date": "2026-01-15",
            "to_date": "2026-01-15",
            "limit": 3,
        },
    )
    assert live_resp.status_code == 200, live_resp.text

    lake_candles = _wire_candle_dicts(lake_resp.json())
    live_candles = _wire_candle_dicts(live_resp.json())

    assert len(lake_candles) == len(live_candles) == 3
    assert lake_candles == live_candles

    expected_ts = [int(t.timestamp() * 1000) for t in _utc_times()]
    assert [c["t"] for c in lake_candles] == expected_ts
