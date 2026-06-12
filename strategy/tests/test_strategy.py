from enum import Enum


class StrategyState(Enum):
    IDLE = "IDLE"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    IN_POSITION = "IN_POSITION"


class MovingAverageCrossoverStrategy:
    """A simple moving average strategy for demonstration and isolation testing."""

    def __init__(self, period: int):
        self.period = period
        self.state = StrategyState.IDLE

    def calculate_sma(self, prices: list[float]) -> float:
        if len(prices) < self.period:
            return 0.0
        return sum(prices[-self.period :]) / self.period

    def evaluate(self, prices: list[float], current_price: float) -> str:
        if len(prices) < self.period:
            return "HOLD"

        sma = self.calculate_sma(prices)

        # State: IDLE -> check entry signal
        if self.state == StrategyState.IDLE:
            if current_price > sma:
                self.state = StrategyState.SIGNAL_GENERATED
                return "BUY"

        # State: SIGNAL_GENERATED -> transition to IN_POSITION
        elif self.state == StrategyState.SIGNAL_GENERATED:
            self.state = StrategyState.IN_POSITION
            return "HOLD"

        # State: IN_POSITION -> check exit signal
        elif self.state == StrategyState.IN_POSITION and current_price < sma:
            self.state = StrategyState.IDLE
            return "SELL"

        return "HOLD"


# ── Tests ──────────────────────────────────────────────────────────────────


def test_sma_calculation():
    strategy = MovingAverageCrossoverStrategy(period=3)
    prices = [10.0, 20.0, 30.0]
    assert strategy.calculate_sma(prices) == 20.0

    prices_short = [10.0, 20.0]
    assert strategy.calculate_sma(prices_short) == 0.0


def test_signal_generation_and_state_transitions():
    strategy = MovingAverageCrossoverStrategy(period=3)
    prices = [10.0, 20.0, 30.0]  # SMA is 20.0

    # 1. State: IDLE. Price is below SMA -> HOLD
    assert strategy.evaluate(prices, current_price=18.0) == "HOLD"
    assert strategy.state == StrategyState.IDLE

    # 2. State: IDLE. Price crosses above SMA -> BUY signal, state -> SIGNAL_GENERATED
    assert strategy.evaluate(prices, current_price=22.0) == "BUY"
    assert strategy.state == StrategyState.SIGNAL_GENERATED

    # 3. State: SIGNAL_GENERATED -> transition to IN_POSITION on next evaluate
    assert strategy.evaluate(prices, current_price=23.0) == "HOLD"
    assert strategy.state == StrategyState.IN_POSITION

    # 4. State: IN_POSITION. Price crosses below SMA -> SELL signal, state -> IDLE
    assert strategy.evaluate(prices, current_price=15.0) == "SELL"
    assert strategy.state == StrategyState.IDLE
