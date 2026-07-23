"""FeaturePipeline computes features before strategy sees the bar."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from application.analytics.feature_pipeline import FeaturePipeline
from application.strategy.strategy_engine import StrategyEngine
from domain.entities import Bar
from domain.value_objects import InstrumentId, Price, Quantity, StrategyId, TimeFrame
from infrastructure.message_bus.bus import MessageBus


def _bar(close: str, ts: datetime | None = None) -> Bar:
    c = Price(value=Decimal(close))
    return Bar(
        instrument_id=InstrumentId.parse("NSE:TEST"),
        open=c,
        high=c,
        low=c,
        close=c,
        volume=Quantity(value=Decimal("1")),
        timeframe=TimeFrame(value="1d"),
        timestamp=ts or datetime(2024, 1, 2, tzinfo=UTC),
    )


class _Probe:
    strategy_id = StrategyId(value="probe")

    def __init__(self, pipeline: FeaturePipeline) -> None:
        self._pipeline = pipeline
        self.features_at_bar: list[dict[str, float]] = []

    def on_start(self, event: object) -> None:
        return None

    def on_stop(self, event: object) -> None:
        return None

    def on_quote(self, quote: object) -> None:
        return None

    def on_fill(self, fill: object) -> None:
        return None

    def on_event(self, event: object) -> None:
        return None

    def on_bar(self, bar: Bar, features: dict[str, float] | None = None) -> None:
        # Features must already be computed when strategy runs.
        self.features_at_bar.append(dict(self._pipeline.last_features))


def test_features_computed_before_strategy_sees_bar() -> None:
    pipeline = FeaturePipeline()
    probe = _Probe(pipeline)
    engine = StrategyEngine(bus=MessageBus())
    engine.register(probe)

    for close in ("100", "110", "105"):
        bar = _bar(close)
        features = pipeline.on_bar(bar)
        assert "returns" in features
        assert "sma" in features
        engine.on_bar(bar)
        assert probe.features_at_bar[-1] == features

    assert len(probe.features_at_bar) == 3
    assert probe.features_at_bar[0]["returns"] == 0.0
    assert probe.features_at_bar[1]["returns"] == pytest_approx_return(100, 110)


def pytest_approx_return(prev: float, cur: float) -> float:
    return (cur - prev) / prev
