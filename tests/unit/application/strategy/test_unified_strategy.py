"""Unit tests for UnifiedStrategy base class and EngineContext zero-parity execution."""

from decimal import Decimal
import pytest
from domain.candles.historical import HistoricalBar
from domain.entities import Quote
from domain.enums import OrderType, Side
from application.strategy.unified_strategy import EngineContext, UnifiedStrategy, StrategyConfig


class SimpleMomentumStrategy(UnifiedStrategy):
    """Test strategy implementation."""

    def __init__(self, config: StrategyConfig, context: EngineContext) -> None:
        super().__init__(config, context)
        self.bars_received = 0
        self.quotes_received = 0

    async def on_bar(self, bar: HistoricalBar) -> None:
        self.bars_received += 1
        if bar.close > Decimal("2500.00"):
            await self.submit_order(
                symbol=bar.instrument.symbol,
                exchange=bar.instrument.exchange,
                side=Side.BUY,
                quantity=10,
                order_type=OrderType.MARKET,
            )

    async def on_quote(self, quote: Quote) -> None:
        self.quotes_received += 1


@pytest.mark.asyncio
async def test_unified_strategy_lifecycle_and_order_submission():
    submitted_orders = []

    class MockEngineContext(EngineContext):
        async def submit_order(self, **kwargs) -> str:
            submitted_orders.append(kwargs)
            return "ORDER-101"

    context = MockEngineContext()
    config = StrategyConfig(name="MomentumTest", symbol="RELIANCE", exchange="NSE")
    strategy = SimpleMomentumStrategy(config, context)

    # Dispatch bar above threshold
    from datetime import datetime, timezone
    from domain.candles.historical import InstrumentRef
    from domain.provenance import DataProvenance

    bar = HistoricalBar(
        instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
        timeframe="1m",
        event_time=datetime.now(timezone.utc),
        open=Decimal("2490.00"),
        high=Decimal("2510.00"),
        low=Decimal("2485.00"),
        close=Decimal("2505.00"),
        volume=1000,
        provenance=DataProvenance.now(broker_id="paper", request_id="req-1"),
    )

    await strategy.on_bar(bar)

    assert strategy.bars_received == 1
    assert len(submitted_orders) == 1
    assert submitted_orders[0]["symbol"] == "RELIANCE"
    assert submitted_orders[0]["side"] == Side.BUY
    assert submitted_orders[0]["quantity"] == 10
