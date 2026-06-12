"""Strategy module -- trading signal generation.

Provides an abstract strategy interface and a concrete moving-average
crossover implementation suitable for live trading and backtesting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from enum import Enum
from typing import Any, Deque, Dict

# -- Signal Enum -------------------------------------------------------------


class Signal(str, Enum):
    """Trading signal produced by a strategy."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


# -- Strategy ABC ------------------------------------------------------------


class Strategy(ABC):
    """Abstract strategy interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    @abstractmethod
    def on_bar(self, bar: dict[str, Any]) -> Signal:
        """Process a single OHLCV bar and return a signal.

        *bar* is expected to contain at least a ``"close"`` key.
        """
        ...


# -- Moving Average Crossover ------------------------------------------------


class MovingAverageCrossover(Strategy):
    """Dual moving-average crossover strategy.

    Generates a BUY signal when the fast SMA crosses above the slow SMA
    and a SELL signal when it crosses below.

    Parameters
    ----------
    fast_period:
        Window length for the fast moving average (default 5).
    slow_period:
        Window length for the slow moving average (default 20).
    """

    def __init__(self, fast_period: int = 5, slow_period: int = 20) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._prices: deque[float] = deque(maxlen=slow_period)
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    @property
    def name(self) -> str:
        return f"MACross({self._fast_period},{self._slow_period})"

    def on_bar(self, bar: dict[str, Any]) -> Signal:
        close = float(bar.get("close", 0))
        self._prices.append(close)

        if len(self._prices) < self._slow_period:
            return Signal.HOLD

        prices_list = list(self._prices)
        fast_sma = sum(prices_list[-self._fast_period :]) / self._fast_period
        slow_sma = sum(prices_list) / self._slow_period

        signal = Signal.HOLD

        if self._prev_fast is not None and self._prev_slow is not None:
            # Bullish cross: fast crosses above slow
            if self._prev_fast <= self._prev_slow and fast_sma > slow_sma:
                signal = Signal.BUY
            # Bearish cross: fast crosses below slow
            elif self._prev_fast >= self._prev_slow and fast_sma < slow_sma:
                signal = Signal.SELL

        self._prev_fast = fast_sma
        self._prev_slow = slow_sma

        return signal
