"""StrategyPipeline — orchestrates Strategy evaluation over candidates.

The pipeline:
1. Takes a list of Candidates (from Scanner/Ranker)
2. Runs each Strategy on each Candidate
3. Collects all Signals into a single StrategyResult per strategy

This is the same pipeline consumed by Scanner, Strategy, Replay,
Backtest, Paper, and Live — ensuring parity across all modes.

Usage:
    pipeline = StrategyPipeline(strategies=[MomentumStrategy(), BreakoutStrategy()])
    result = pipeline.evaluate(candidates, features_by_symbol)
    for signal in result.actionable:
        print(signal.symbol, signal.signal_type, signal.confidence)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType, StrategyResult
from analytics.strategy.protocols import Strategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Built-in strategies (examples / defaults)
# ---------------------------------------------------------------------------


@dataclass
class MomentumStrategy:
    """Momentum-based strategy using RSI and ROC.

    Strong signals (high confidence):
    - BUY when RSI < rsi_oversold and ROC > roc_threshold
    - SELL when RSI > rsi_overbought and ROC < -roc_threshold

    Weakened signals (50% confidence):
    - BUY when RSI < rsi_weak_buy and ROC > roc_weak_threshold
    - SELL when RSI > rsi_weak_sell and ROC < -roc_weak_threshold

    Parameters
    ----------
    rsi_oversold : float
        RSI threshold for strong buy signal (default 35).
    rsi_overbought : float
        RSI threshold for strong sell signal (default 70).
    roc_threshold : float
        Minimum ROC % for strong signal (default 0.0).
    rsi_weak_buy : float
        RSI threshold for weakened buy (default 45).
    rsi_weak_sell : float
        RSI threshold for weakened sell (default 60).
    roc_weak_threshold : float
        Minimum ROC % for weakened signal (default 2.0).
    """

    name: str = "Momentum"
    rsi_oversold: float = 35.0
    rsi_overbought: float = 70.0
    roc_threshold: float = 0.0
    rsi_weak_buy: float = 45.0
    rsi_weak_sell: float = 60.0
    roc_weak_threshold: float = 2.0

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        if features.empty:
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy=self.name,
                reasons=["No data"],
            )

        last = features.iloc[-1]
        rsi = float(last.get("rsi", 50.0))
        roc = float(last.get("roc", 0.0))
        close = float(last.get("close", 0.0))

        reasons: list[str] = []
        confidence = 0.0
        weakened = False

        # Strong signals
        if rsi < self.rsi_oversold and roc > self.roc_threshold:
            signal_type = SignalType.BUY
            reasons.append(f"RSI {rsi:.1f} < {self.rsi_oversold} (oversold)")
            reasons.append(f"ROC {roc:.2f}% > {self.roc_threshold}% (momentum up)")
            confidence = min(1.0, (self.rsi_oversold - rsi) / 30.0 + 0.3)
        elif rsi > self.rsi_overbought and roc < -self.roc_threshold:
            signal_type = SignalType.SELL
            reasons.append(f"RSI {rsi:.1f} > {self.rsi_overbought} (overbought)")
            reasons.append(f"ROC {roc:.2f}% < -{self.roc_threshold}% (momentum down)")
            confidence = min(1.0, (rsi - self.rsi_overbought) / 30.0 + 0.3)
        # Weakened signals (50% confidence)
        elif rsi < self.rsi_weak_buy and roc > self.roc_weak_threshold:
            signal_type = SignalType.BUY
            weakened = True
            reasons.append(f"RSI {rsi:.1f} < {self.rsi_weak_buy} (mild oversold)")
            reasons.append(f"ROC {roc:.2f}% > {self.roc_weak_threshold}% (momentum up)")
            confidence = min(0.5, (self.rsi_weak_buy - rsi) / 40.0 + 0.15)
        elif rsi > self.rsi_weak_sell and roc < -self.roc_weak_threshold:
            signal_type = SignalType.SELL
            weakened = True
            reasons.append(f"RSI {rsi:.1f} > {self.rsi_weak_sell} (mild overbought)")
            reasons.append(f"ROC {roc:.2f}% < -{self.roc_weak_threshold}% (momentum down)")
            confidence = min(0.5, (rsi - self.rsi_weak_sell) / 40.0 + 0.15)
        else:
            signal_type = SignalType.HOLD
            reasons.append(f"RSI {rsi:.1f}, ROC {roc:.2f}% — no signal")
            confidence = 0.0

        # Compute suggested entry/stop/target from ATR if available
        atr = float(last.get("atr", 0.0))
        entry_price = close if close > 0 else None
        stop_loss = (
            (close - 1.5 * atr)
            if atr > 0 and signal_type == SignalType.BUY
            else ((close + 1.5 * atr) if atr > 0 and signal_type == SignalType.SELL else None)
        )
        target = (
            (close + 3.0 * atr)
            if atr > 0 and signal_type == SignalType.BUY
            else ((close - 3.0 * atr) if atr > 0 and signal_type == SignalType.SELL else None)
        )

        metadata = {"rsi": rsi, "roc": roc, "atr": atr, "weakened": weakened}

        return Signal(
            symbol=candidate.symbol,
            signal_type=signal_type,
            confidence=round(confidence, 3),
            strategy=self.name,
            entry_price=entry_price,
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            target=round(target, 2) if target else None,
            reasons=reasons,
            metadata=metadata,
        )


@dataclass
class BreakoutStrategy:
    """Breakout strategy: BUY on price above recent high, SELL on breakdown.

    Uses swing high/low columns if available, else falls back to close > SMA20.
    """

    name: str = "Breakout"

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        if features.empty:
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy=self.name,
                reasons=["No data"],
            )

        last = features.iloc[-1]
        close = float(last.get("close", 0.0))
        swing_high = float(last.get("last_swing_high", last.get("swing_high", close)))
        swing_low = float(last.get("last_swing_low", last.get("swing_low", close)))
        sma20 = float(last.get("sma_20", close))
        volume = float(last.get("volume", 0.0))
        volume_sma = float(last.get("volume_sma", volume))

        reasons: list[str] = []
        confidence = 0.0

        if close > swing_high and volume > volume_sma * 1.5:
            signal_type = SignalType.BUY
            reasons.append(f"Close {close:.2f} > swing high {swing_high:.2f}")
            reasons.append(f"Volume {volume:.0f} > 1.5x avg ({volume_sma:.0f})")
            confidence = min(1.0, 0.5 + (volume / max(volume_sma, 1) - 1.5) * 0.3)
        elif close < swing_low and volume > volume_sma * 1.5:
            signal_type = SignalType.SELL
            reasons.append(f"Close {close:.2f} < swing low {swing_low:.2f}")
            reasons.append(f"Volume {volume:.0f} > 1.5x avg ({volume_sma:.0f})")
            confidence = min(1.0, 0.5 + (volume / max(volume_sma, 1) - 1.5) * 0.3)
        else:
            signal_type = SignalType.HOLD
            reasons.append("No breakout/breakdown confirmed")
            confidence = 0.0

        return Signal(
            symbol=candidate.symbol,
            signal_type=signal_type,
            confidence=round(confidence, 3),
            strategy=self.name,
            entry_price=close if close > 0 else None,
            reasons=reasons,
            metadata={"swing_high": swing_high, "swing_low": swing_low, "sma20": sma20},
        )


# ---------------------------------------------------------------------------
# StrategyPipeline
# ---------------------------------------------------------------------------


def _default_strategies() -> list[Strategy]:
    """Discover strategies via registry (TOS-P6-001); fall back to builtins."""
    from analytics.strategy.registry import StrategyRegistry

    # Ensure built-ins are registered at least once.
    if "momentum" not in StrategyRegistry.list():
        StrategyRegistry.register("momentum", MomentumStrategy)
    if "breakout" not in StrategyRegistry.list():
        StrategyRegistry.register("breakout", BreakoutStrategy)
    try:
        StrategyRegistry.discover("analytics.strategy.builtins")
    except Exception:  # pragma: no cover - discovery best-effort
        pass
    names = StrategyRegistry.list()
    if not names:
        return [MomentumStrategy(), BreakoutStrategy()]
    out: list[Strategy] = []
    for name in names:
        try:
            out.append(StrategyRegistry.create(name))
        except Exception:
            continue
    return out or [MomentumStrategy(), BreakoutStrategy()]


@dataclass
class StrategyPipeline:
    """Orchestrates Strategy evaluation across Candidates.

    Parameters
    ----------
    strategies:
        List of Strategy instances to evaluate each candidate.
        Defaults via StrategyRegistry.discover (TOS-P6-001).
    """

    strategies: list[Strategy] = field(default_factory=_default_strategies)

    def evaluate(
        self,
        candidates: list[Candidate],
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> list[StrategyResult]:
        """Run every strategy on every candidate.

        Parameters
        ----------
        candidates:
            List of Candidate objects from a Scanner.
        features_by_symbol:
            Mapping of symbol -> feature-enriched DataFrame (from FeaturePipeline).

        Returns
        -------
        list[StrategyResult]
            One StrategyResult per strategy, each containing Signals for
            all candidates that had features available.
        """
        results: list[StrategyResult] = []

        for strategy in self.strategies:
            signals: list[Signal] = []
            evaluated = 0

            for candidate in candidates:
                features = features_by_symbol.get(candidate.symbol)
                if features is None or features.empty:
                    logger.debug("No features for %s, skipping", candidate.symbol)
                    continue

                try:
                    signal = strategy.evaluate(candidate, features)
                    signals.append(signal)
                    evaluated += 1
                except Exception as exc:
                    logger.warning(
                        "Strategy %s failed on %s: %s", strategy.name, candidate.symbol, exc
                    )
                    signals.append(
                        Signal(
                            symbol=candidate.symbol,
                            signal_type=SignalType.HOLD,
                            confidence=0.0,
                            strategy=strategy.name,
                            reasons=[f"Error: {exc}"],
                        )
                    )
                    evaluated += 1

            results.append(
                StrategyResult(
                    strategy=strategy.name,
                    signals=signals,
                    evaluated=evaluated,
                )
            )
            logger.info(
                "Strategy %s: %d signals (%d actionable) from %d candidates",
                strategy.name,
                len(signals),
                len([s for s in signals if s.is_actionable]),
                evaluated,
            )

        return results

    def evaluate_single(
        self,
        candidate: Candidate,
        features: pd.DataFrame,
    ) -> list[Signal]:
        """Evaluate a single candidate across all strategies.

        Convenience method for backtesting / live where you evaluate
        one symbol at a time.
        """
        signals: list[Signal] = []
        for strategy in self.strategies:
            try:
                signal = strategy.evaluate(candidate, features)
                signals.append(signal)
            except Exception as exc:
                logger.warning("Strategy %s failed on %s: %s", strategy.name, candidate.symbol, exc)
                signals.append(
                    Signal(
                        symbol=candidate.symbol,
                        signal_type=SignalType.HOLD,
                        confidence=0.0,
                        strategy=strategy.name,
                        reasons=[f"Error: {exc}"],
                    )
                )
        return signals
