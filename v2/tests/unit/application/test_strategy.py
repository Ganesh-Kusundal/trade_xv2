"""StrategyEngine and FeaturePipeline: register, route, emit, compute features."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4


from application.analytics.feature_pipeline import EnrichedBar, FeaturePipeline
from application.strategy.strategy_engine import StrategyEngine
from domain.commands import PlaceOrderCommand
from domain.entities import Bar, Quote
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.events import Message, OrderFilled
from domain.ports.types import StartEvent, StopEvent
from domain.value_objects import (
    CorrelationId,
    InstrumentId,
    OrderId,
    Price,
    Quantity,
    StrategyId,
    TimeFrame,
)
from infrastructure.message_bus.bus import MessageBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(close: str = "100") -> Bar:
    c = Price(value=Decimal(close))
    return Bar(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        open=c,
        high=c,
        low=c,
        close=c,
        volume=Quantity(value=Decimal("100")),
        timeframe=TimeFrame(value="1d"),
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
    )


def _make_quote(bid: str = "99", ask: str = "101") -> Quote:
    return Quote(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        bid=Price(value=Decimal(bid)),
        ask=Price(value=Decimal(ask)),
        bid_size=Quantity(value=Decimal("10")),
        ask_size=Quantity(value=Decimal("10")),
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
    )


def _make_fill(side: OrderSide = OrderSide.BUY) -> OrderFilled:
    return OrderFilled(
        order_id=OrderId(value="ORD-001"),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=side,
        filled_qty=Quantity(value=Decimal("10")),
        avg_price=Price(value=Decimal("100")),
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Fake strategies for testing
# ---------------------------------------------------------------------------

class RecordingStrategy:
    """Minimal strategy that records all calls."""

    def __init__(self, strategy_id: str = "test-strategy") -> None:
        self.strategy_id = StrategyId(value=strategy_id)
        self.calls: list[str] = []
        self.received_bars: list[Bar] = []
        self.received_quotes: list[Quote] = []
        self.received_fills: list[OrderFilled] = []
        self.received_events: list[Message] = []

    def on_start(self, event: StartEvent) -> None:
        self.calls.append("on_start")

    def on_stop(self, event: StopEvent) -> None:
        self.calls.append("on_stop")

    def on_quote(self, quote: Quote) -> None:
        self.calls.append("on_quote")
        self.received_quotes.append(quote)

    def on_bar(self, bar: Bar, features: dict[str, float] | None = None) -> None:
        self.calls.append("on_bar")
        self.received_bars.append(bar)

    def on_fill(self, fill: OrderFilled) -> None:
        self.calls.append("on_fill")
        self.received_fills.append(fill)

    def on_event(self, event: Message) -> None:
        self.calls.append("on_event")
        self.received_events.append(event)


class OrderingStrategy:
    """Strategy that emits an order on bar."""

    def __init__(self, strategy_id: str = "ordering-strategy") -> None:
        self.strategy_id = StrategyId(value=strategy_id)
        self._bus: MessageBus | None = None

    def set_bus(self, bus: MessageBus) -> None:
        self._bus = bus

    def on_start(self, event: StartEvent) -> None:
        pass

    def on_stop(self, event: StopEvent) -> None:
        pass

    def on_quote(self, quote: Quote) -> None:
        pass

    def on_bar(self, bar: Bar, features: dict[str, float] | None = None) -> None:
        if self._bus is not None:
            cmd = PlaceOrderCommand(
                instrument_id=bar.instrument_id,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Quantity(value=Decimal("10")),
                price=None,
                time_in_force=TimeInForce.DAY,
                correlation_id=CorrelationId(value=uuid4()),
            )
            self._bus.publish(cmd)

    def on_fill(self, fill: OrderFilled) -> None:
        pass

    def on_event(self, event: Message) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStrategyEngineRegister:
    """StrategyEngine register/unregister."""

    def test_register_strategy(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        strategy = RecordingStrategy()

        engine.register(strategy)

        assert StrategyId(value="test-strategy") in engine._strategies

    def test_unregister_strategy(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        strategy = RecordingStrategy()
        engine.register(strategy)

        engine.unregister(StrategyId(value="test-strategy"))

        assert StrategyId(value="test-strategy") not in engine._strategies

    def test_unregister_nonexistent_is_noop(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        # Should not raise
        engine.unregister(StrategyId(value="nonexistent"))

    def test_register_multiple_strategies(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        s1 = RecordingStrategy(strategy_id="s1")
        s2 = RecordingStrategy(strategy_id="s2")

        engine.register(s1)
        engine.register(s2)

        assert len(engine._strategies) == 2


class TestStrategyEngineRouting:
    """StrategyEngine routes messages to strategies."""

    def test_on_bar_routes_to_all_strategies(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        s1 = RecordingStrategy(strategy_id="s1")
        s2 = RecordingStrategy(strategy_id="s2")
        engine.register(s1)
        engine.register(s2)

        bar = _make_bar()
        engine.on_bar(bar)

        assert s1.received_bars == [bar]
        assert s2.received_bars == [bar]
        assert s1.calls.count("on_bar") == 1
        assert s2.calls.count("on_bar") == 1

    def test_on_quote_routes_to_all_strategies(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        s1 = RecordingStrategy(strategy_id="s1")
        engine.register(s1)

        quote = _make_quote()
        engine.on_quote(quote)

        assert s1.received_quotes == [quote]

    def test_on_fill_routes_to_all_strategies(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        s1 = RecordingStrategy(strategy_id="s1")
        engine.register(s1)

        fill = _make_fill()
        engine.on_fill(fill)

        assert s1.received_fills == [fill]

    def test_on_event_routes_to_all_strategies(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        s1 = RecordingStrategy(strategy_id="s1")
        engine.register(s1)

        # Use a Message subclass that we can publish
        class DummyEvent(Message):
            pass

        event = DummyEvent(timestamp=datetime(2024, 6, 1, tzinfo=UTC))
        engine.on_event(event)

        assert s1.received_events == [event]


class TestStrategyEngineLifecycle:
    """Strategy lifecycle: on_start, on_stop."""

    def test_start_calls_on_start(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        strategy = RecordingStrategy()
        engine.register(strategy)

        event = StartEvent(
            strategy_id=strategy.strategy_id,
            timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        )
        engine.start_strategy(strategy.strategy_id, event)

        assert "on_start" in strategy.calls

    def test_stop_calls_on_stop(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        strategy = RecordingStrategy()
        engine.register(strategy)

        event = StopEvent(
            strategy_id=strategy.strategy_id,
            timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        )
        engine.stop_strategy(strategy.strategy_id, event)

        assert "on_stop" in strategy.calls

    def test_start_nonexistent_strategy_is_noop(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        event = StartEvent(
            strategy_id=StrategyId(value="nonexistent"),
            timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        )
        # Should not raise
        engine.start_strategy(StrategyId(value="nonexistent"), event)


class TestStrategyEngineEmitOrder:
    """StrategyEngine emit_order publishes to MessageBus."""

    def test_emit_order_publishes_command(self) -> None:
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        commands: list[PlaceOrderCommand] = []
        bus.subscribe(PlaceOrderCommand, commands.append)

        cmd = PlaceOrderCommand(
            instrument_id=InstrumentId.parse("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Quantity(value=Decimal("10")),
            price=None,
            time_in_force=TimeInForce.DAY,
            correlation_id=CorrelationId(value=uuid4()),
        )
        engine.emit_order(cmd)

        assert len(commands) == 1
        assert commands[0] is cmd

    def test_strategy_emitting_order_via_bus(self) -> None:
        """Strategy publishes order via bus, engine routes bar to strategy."""
        bus = MessageBus()
        engine = StrategyEngine(bus=bus)
        commands: list[PlaceOrderCommand] = []
        bus.subscribe(PlaceOrderCommand, commands.append)

        strategy = OrderingStrategy()
        strategy.set_bus(bus)
        engine.register(strategy)

        engine.on_bar(_make_bar())

        assert len(commands) == 1
        assert commands[0].instrument_id.value == "NSE:RELIANCE"
        assert commands[0].side == OrderSide.BUY


# ---------------------------------------------------------------------------
# FeaturePipeline Tests
# ---------------------------------------------------------------------------

class TestFeaturePipeline:
    """FeaturePipeline computes returns and SMA on each bar."""

    def test_first_bar_returns_zero(self) -> None:
        pipeline = FeaturePipeline()
        bar = _make_bar(close="100")
        features = pipeline.on_bar(bar)

        assert features["returns"] == 0.0
        assert features["sma"] == 100.0

    def test_returns_computed_correctly(self) -> None:
        pipeline = FeaturePipeline()
        pipeline.on_bar(_make_bar(close="100"))
        features = pipeline.on_bar(_make_bar(close="110"))

        # (110 - 100) / 100 = 0.1
        assert abs(features["returns"] - 0.1) < 1e-10

    def test_sma_computed_correctly(self) -> None:
        pipeline = FeaturePipeline(sma_window=3)
        pipeline.on_bar(_make_bar(close="100"))
        pipeline.on_bar(_make_bar(close="110"))
        features = pipeline.on_bar(_make_bar(close="120"))

        # SMA of [100, 110, 120] = 110.0
        assert abs(features["sma"] - 110.0) < 1e-10

    def test_sma_window_sliding(self) -> None:
        pipeline = FeaturePipeline(sma_window=2)
        pipeline.on_bar(_make_bar(close="100"))
        pipeline.on_bar(_make_bar(close="110"))
        features = pipeline.on_bar(_make_bar(close="120"))

        # SMA of last 2: [110, 120] = 115.0
        assert abs(features["sma"] - 115.0) < 1e-10

    def test_publishes_enriched_bar_to_bus(self) -> None:
        bus = MessageBus()
        enriched: list[EnrichedBar] = []
        bus.subscribe(EnrichedBar, enriched.append)

        pipeline = FeaturePipeline(bus=bus)
        bar = _make_bar(close="100")
        pipeline.on_bar(bar)

        assert len(enriched) == 1
        assert enriched[0].bar is bar
        assert "returns" in enriched[0].features
        assert "sma" in enriched[0].features

    def test_pipeline_ordering_with_strategy_engine(self) -> None:
        """Market Data → FeaturePipeline → StrategyEngine."""
        bus = MessageBus()
        enriched_bars: list[EnrichedBar] = []
        bus.subscribe(EnrichedBar, enriched_bars.append)

        pipeline = FeaturePipeline(bus=bus)
        strategy = RecordingStrategy(strategy_id="pipeline-test")
        engine = StrategyEngine(bus=bus)
        engine.register(strategy)

        bar = _make_bar(close="100")
        # Pipeline first, then engine
        features = pipeline.on_bar(bar)
        engine.on_bar(bar)

        assert len(enriched_bars) == 1
        assert strategy.received_bars == [bar]
        assert "returns" in features
        assert "sma" in features
