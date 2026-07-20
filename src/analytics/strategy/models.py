"""Strategy pipeline models — Signal, SignalType, StrategyResult.

The Signal dataclass is the core output of a Strategy. It carries rich
metadata beyond a simple BUY/SELL/HOLD: confidence, entry/exit levels,
position sizing, and strategy-specific reasoning.

Usage:
    signal = Signal(
        symbol="RELIANCE",
        signal_type=SignalType.BUY,
        confidence=0.82,
        strategy="MomentumBreakout",
        entry_price=2500.0,
        stop_loss=2420.0,
        target=2650.0,
        reasons=["RSI oversold bounce", "Volume surge 2.1x"],
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from domain.ports.time_service import get_current_clock


def _signal_timestamp() -> datetime:
    return get_current_clock().now()

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalType(str, Enum):
    """Signal direction and strength."""

    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


# ---------------------------------------------------------------------------
# Strategy State (P2-Phase 2)
# ---------------------------------------------------------------------------


class StrategyState(str, Enum):
    """Strategy lifecycle states.

    Transitions:
    - INACTIVE → ACTIVE (activate strategy)
    - ACTIVE → PAUSED (temporarily disable)
    - ACTIVE → DISABLED (permanently disable)
    - PAUSED → ACTIVE (resume strategy)
    - PAUSED → DISABLED (disable from paused state)
    - DISABLED → {} (terminal state)
    """

    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"

    @property
    def is_active(self) -> bool:
        """True if strategy is active and can generate signals."""
        return self == StrategyState.ACTIVE

    @property
    def is_terminal(self) -> bool:
        """True if strategy is disabled (cannot transition further)."""
        return self == StrategyState.DISABLED


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    """A rich trading signal produced by a Strategy.

    Attributes
    ----------
    symbol:
        NSE/BSE symbol (e.g. ``"RELIANCE"``).
    signal_type:
        Direction and strength (BUY / SELL / HOLD / STRONG_BUY / STRONG_SELL).
    confidence:
        Model confidence in [0.0, 1.0].  0.5 = neutral, >0.7 = high.
    strategy:
        Human-readable name of the originating strategy.
    entry_price:
        Suggested entry price.  ``None`` if strategy does not suggest one.
    stop_loss:
        Suggested stop-loss price.  ``None`` if not applicable.
    target:
        Suggested target price.  ``None`` if not applicable.
    position_size_pct:
        Suggested position size as % of capital (0-100).  0 = no sizing.
    reasons:
        Human-readable list of reasons behind the signal.
    timestamp:
        UTC timestamp when the signal was generated.
    metadata:
        Arbitrary strategy-specific data (e.g. indicator values).
    """

    symbol: str
    signal_type: SignalType
    confidence: float = 0.5
    strategy: str = ""
    entry_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    position_size_pct: float = 0.0
    reasons: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=_signal_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {self.confidence}")
        if not 0.0 <= self.position_size_pct <= 100.0:
            raise ValueError(f"position_size_pct must be in [0, 100], got {self.position_size_pct}")

    @property
    def is_actionable(self) -> bool:
        """True if the signal is anything other than HOLD."""
        return self.signal_type not in (SignalType.HOLD,)

    @property
    def is_buy(self) -> bool:
        return self.signal_type in (SignalType.BUY, SignalType.STRONG_BUY)

    @property
    def is_sell(self) -> bool:
        return self.signal_type in (SignalType.SELL, SignalType.STRONG_SELL)

    @property
    def risk_reward_ratio(self) -> float | None:
        """Compute R:R ratio if entry, stop, and target are all set."""
        if self.entry_price is None or self.stop_loss is None or self.target is None:
            return None
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.target - self.entry_price)
        if risk == 0:
            return None
        return round(reward / risk, 2)


# ---------------------------------------------------------------------------
# StrategyResult
# ---------------------------------------------------------------------------


@dataclass
class StrategyResult:
    """Aggregated output from running strategies on a set of candidates.

    Attributes
    ----------
    strategy:
        Name of the strategy that produced these signals.
    signals:
        List of Signal objects, one per candidate evaluated.
    evaluated:
        Total number of candidates evaluated.
    metadata:
        Strategy-level metadata (e.g. parameters used).
    """

    strategy: str
    signals: list[Signal] = field(default_factory=list)
    evaluated: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.signals)

    @property
    def actionable(self) -> list[Signal]:
        """Signals that are not HOLD."""
        return [s for s in self.signals if s.is_actionable]

    @property
    def buys(self) -> list[Signal]:
        return [s for s in self.signals if s.is_buy]

    @property
    def sells(self) -> list[Signal]:
        return [s for s in self.signals if s.is_sell]

    def top(self, n: int = 10) -> list[Signal]:
        """Return top-N signals by confidence (descending)."""
        return sorted(self.signals, key=lambda s: s.confidence, reverse=True)[:n]

    def by_symbol(self, symbol: str) -> Signal | None:
        """Return the first signal for a given symbol, or None."""
        for s in self.signals:
            if s.symbol == symbol:
                return s
        return None

from analytics.scanner.models import Candidate  # noqa: F401
