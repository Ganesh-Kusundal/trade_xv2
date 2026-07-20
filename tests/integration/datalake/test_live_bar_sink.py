"""MD-001 increment 2: EventBus TICK → 1m bar → datalake parquet.

Uses real EventBus, CandleAggregator, LiveBarSink, and HistoricalDataLoader
merge-write — no mocks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from application.streaming.live_tick_pipeline import (
    LiveTickBarPipeline,
    market_tick_from_event,
)
from datalake.ingestion.live_bar_sink import LiveBarSink
from domain import Quote
from domain.events import DomainEvent
from infrastructure.event_bus.event_bus import EventBus
from plugins.exchanges.nse import ADAPTER


@pytest.fixture(autouse=True)
def _nse_exchange_adapter():
    from datalake.exchange_registry import set_active_adapter

    set_active_adapter(ADAPTER)
    yield
    from datalake import exchange_registry

    exchange_registry._ACTIVE = None


def _publish_tick(
    bus: EventBus,
    *,
    symbol: str,
    ltp: Decimal,
    ts: datetime,
    volume: int = 10,
) -> None:
    quote = Quote(symbol=symbol, ltp=ltp, volume=volume, timestamp=ts)
    bus.publish(
        DomainEvent(
            event_type="TICK",
            timestamp=ts,
            payload={"quote": quote},
            symbol=symbol,
            source="test",
        )
    )


def test_eventbus_tick_produces_merged_parquet_bar(tmp_path: Path) -> None:
    """TICK on EventBus → 1m close → parquet row at canonical path."""
    bus = EventBus()
    sink = LiveBarSink(root=str(tmp_path))
    pipeline = LiveTickBarPipeline(on_bar=sink.write_bar, timeframes=("1m",))
    bus.subscribe("TICK", lambda event: pipeline.on_tick(market_tick_from_event(event)))

    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    _publish_tick(bus, symbol="RELIANCE", ltp=Decimal("100"), ts=base)
    _publish_tick(
        bus,
        symbol="RELIANCE",
        ltp=Decimal("102"),
        ts=base.replace(second=30),
    )
    # Cross 1m boundary → emit 10:00 bucket (100, 102 high, vol 20).
    _publish_tick(
        bus,
        symbol="RELIANCE",
        ltp=Decimal("103"),
        ts=base.replace(minute=1),
    )

    sink.flush()
    pipeline.flush()

    parquet_path = (
        tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=RELIANCE" / "data.parquet"
    )
    assert parquet_path.exists(), f"expected bar at {parquet_path}"

    df = pd.read_parquet(parquet_path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "RELIANCE"
    assert row["open"] == pytest.approx(100.0)
    assert row["high"] == pytest.approx(102.0)
    assert row["close"] == pytest.approx(102.0)
    assert row["volume"] == 20


def test_market_tick_from_event_flat_payload() -> None:
    ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    event = DomainEvent(
        event_type="TICK",
        timestamp=ts,
        payload={"ltp": "250.5", "volume": 5, "exchange": "NSE"},
        symbol="INFY",
        source="synthetic",
    )
    tick = market_tick_from_event(event)
    assert tick is not None
    assert tick.instrument.symbol == "INFY"
    assert float(tick.ltp) == pytest.approx(250.5)
    assert tick.volume == 5
