"""Research engines — Replay / Backtest / Paper / Live mode wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from application.analytics.feature_pipeline import FeaturePipeline
from application.strategy.strategy_engine import StrategyEngine
from domain.commands import PlaceOrderCommand
from domain.entities import Bar
from domain.enums import Environment
from domain.events import OrderFilled
from domain.ports import Strategy


@dataclass
class BacktestResult:
    trade_count: int
    metrics: dict[str, Any] = field(default_factory=dict)


class ReplayEngine:
    """Replay MessageLog through the same MessageBus handlers as live."""

    def __init__(
        self,
        *,
        bus: Any,
        message_log: Any,
        clock: Any | None = None,
    ) -> None:
        self._bus = bus
        self._log = message_log
        self._clock = clock

    def run(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        count = 0
        for message in self._log.read(start, end):
            if self._clock is not None:
                ts = getattr(message, "timestamp", None)
                if ts is not None:
                    setter = getattr(self._clock, "set", None)
                    if callable(setter):
                        setter(ts)
            self._bus.publish(message)
            count += 1
        return count


class BacktestEngine:
    """Iterate bars with FakeClock; optional SimulatedFillSource via ExecutionEngine."""

    def __init__(
        self,
        *,
        bus: Any,
        clock: Any,
        feature_pipeline: FeaturePipeline | None = None,
        strategy_engine: StrategyEngine | None = None,
        execution_engine: Any | None = None,
    ) -> None:
        self._bus = bus
        self._clock = clock
        self._pipeline = feature_pipeline or FeaturePipeline(bus=bus)
        self._strategies = strategy_engine or StrategyEngine(bus=bus)
        self._execution = execution_engine

    def run(
        self,
        bars: Iterable[Bar],
        strategy: Strategy | None = None,
    ) -> BacktestResult:
        if strategy is not None:
            self._strategies.register(strategy)

        fills: list[OrderFilled] = []
        cmd_sub = None
        fill_sub = None
        if self._execution is not None:
            cmd_sub = self._bus.subscribe(
                PlaceOrderCommand, self._execution.on_order_command
            )
            fill_sub = self._bus.subscribe(OrderFilled, fills.append)

        bars_processed = 0
        try:
            for bar in bars:
                self._advance_to(bar.timestamp)
                features = self._pipeline.on_bar(bar)
                self._strategies.on_bar(bar, features=features)
                bars_processed += 1
        finally:
            if cmd_sub is not None:
                self._bus.unsubscribe(cmd_sub)
            if fill_sub is not None:
                self._bus.unsubscribe(fill_sub)

        trade_count = len(fills)
        return BacktestResult(
            trade_count=trade_count,
            metrics={
                "bars_processed": bars_processed,
                "trades": trade_count,
            },
        )

    def _advance_to(self, when: datetime) -> None:
        setter = getattr(self._clock, "set", None)
        if callable(setter):
            setter(when)
            return
        now = self._clock.now()
        delta = when - now
        if delta.total_seconds() > 0:
            self._clock.advance(delta)


class PaperTradingEngine:
    """PAPER mode wrapper — live data + paper fills; requires a Runtime."""

    mode = Environment.PAPER

    def __init__(self, runtime: Any) -> None:
        if runtime is None:
            raise TypeError("PaperTradingEngine requires runtime")
        self.runtime = runtime


class LiveTradingEngine:
    """LIVE mode wrapper — live data + broker fills; requires a Runtime."""

    mode = Environment.LIVE

    def __init__(self, runtime: Any) -> None:
        if runtime is None:
            raise TypeError("LiveTradingEngine requires runtime")
        self.runtime = runtime
