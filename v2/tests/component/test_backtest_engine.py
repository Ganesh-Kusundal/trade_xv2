"""BacktestEngine iterates bars → BacktestResult with trade_count/metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from application.analytics.engines import BacktestEngine, BacktestResult
from application.execution import ExecutionEngine, InMemoryOrderStore, SimulatedFillSource
from application.execution.protocols import RiskCheckResult
from application.strategy.buy_and_hold import BuyAndHold
from domain.entities import Bar
from domain.value_objects import CorrelationId, InstrumentId, Price, Quantity, TimeFrame
from infrastructure.clock import FakeClock
from infrastructure.message_bus.bus import MessageBus


class _ApproveRisk:
    def check_order(self, command: object, context: object | None = None) -> RiskCheckResult:
        return RiskCheckResult(approved=True)


class _MemoryIdempotency:
    """Matches ExecutionEngine: None = new; non-None = prior result."""

    def __init__(self) -> None:
        self._results: dict[object, object] = {}

    def check_and_reserve(self, correlation_id: object) -> object | None:
        key = getattr(correlation_id, "value", correlation_id)
        return self._results.get(key)

    def record_result(self, correlation_id: object, result: object) -> None:
        key = getattr(correlation_id, "value", correlation_id)
        self._results[key] = result


def _bars(n: int = 3) -> list[Bar]:
    out: list[Bar] = []
    start = datetime(2024, 1, 2, tzinfo=UTC)
    for i in range(n):
        px = Price(value=Decimal(100 + i))
        out.append(
            Bar(
                instrument_id=InstrumentId(value="NSE:TEST"),
                open=px,
                high=px,
                low=px,
                close=px,
                volume=Quantity(value=Decimal("1")),
                timeframe=TimeFrame(value="1d"),
                timestamp=start + timedelta(days=i),
            )
        )
    return out


def test_backtest_few_bars_yields_result_with_trade_count_and_metrics() -> None:
    bus = MessageBus()
    clock = FakeClock(start=datetime(2024, 1, 1, tzinfo=UTC))
    ee = ExecutionEngine(
        fill_source=SimulatedFillSource(),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_store=InMemoryOrderStore(),
        message_bus=bus,
        clock=clock,
    )
    strategy = BuyAndHold(
        bus=bus,
        quantity=Quantity(value=Decimal("2")),
        correlation_id=CorrelationId(value=uuid4()),
    )
    engine = BacktestEngine(
        bus=bus,
        clock=clock,
        execution_engine=ee,
    )
    result = engine.run(bars=_bars(3), strategy=strategy)

    assert isinstance(result, BacktestResult)
    assert result.trade_count == 1
    assert isinstance(result.metrics, dict)
    assert result.metrics.get("bars_processed") == 3
