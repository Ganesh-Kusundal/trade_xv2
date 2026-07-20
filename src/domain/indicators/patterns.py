"""Candlestick / price-pattern detection (pure domain logic).

Lazy-pandas detectors implemented as frozen dataclasses whose :meth:`compute`
appends boolean and categorical columns to an OHLCV ``DataFrame``. No pandas
import at module scope (domain-purity rule), and no import of ``application`` /
``infrastructure`` / ``analytics``.

Detectors
---------
* ``cdl_doji``            — negligible real body vs range
* ``cdl_hammer``          — small body, long lower wick (bullish reversal shape)
* ``cdl_shooting_star``   — small body, long upper wick (bearish reversal shape)
* ``cdl_engulfing_bull``  — bullish candle fully engulfs prior bearish body
* ``cdl_engulfing_bear``  — bearish candle fully engulfs prior bullish body
* ``cdl_harami_bull``     — small bullish body inside prior large bearish body
* ``cdl_harami_bear``     — small bearish body inside prior large bullish body
* ``swing_continuation``  — trend continuation per MarketStructureAnalyzer
* ``swing_breakdown``     — close breaks below last confirmed swing low
* ``cdl_direction``       — enum summary: BULL / BEAR / NEUTRAL
"""

from __future__ import annotations

from dataclasses import dataclass, field

# No top-level pandas import (domain purity). MarketStructureAnalyzer lives in
# the same domain package, so importing it is allowed.
from domain.indicators.market_structure import MarketStructureAnalyzer


@dataclass(frozen=True)
class CandlestickPatterns:
    """Detect candlestick + swing patterns on an OHLCV frame.

    All thresholds are ratios of the bar range, so detectors are scale-free.
    ``compute`` mutates and returns ``df`` (adds boolean/enum columns). It is
    safe to call on an empty frame (returns columns of ``False`` / ``NEUTRAL``).
    """

    doji_body_ratio: float = 0.1
    hammer_lower_wick_mult: float = 2.0
    hammer_upper_wick_mult: float = 0.3
    hammer_max_body_ratio: float = 0.4
    swing_left: int = 2
    swing_right: int = 2

    def compute(self, data) -> object:
        import pandas as pd

        df = data
        required = ["open", "high", "low", "close"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        if df.empty:
            for col in self._column_names():
                df[col] = False if col != "cdl_direction" else "NEUTRAL"
            return df

        # --- bar geometry -------------------------------------------------
        body = df["close"] - df["open"]
        abs_body = body.abs()
        rng = (df["high"] - df["low"]).replace(0, 1e-10)
        upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
        lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
        body_ratio = abs_body / rng

        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        prev_body = prev_close - prev_open
        prev_abs_body = prev_body.abs()

        # --- doji ---------------------------------------------------------
        df["cdl_doji"] = body_ratio <= self.doji_body_ratio

        # --- hammer (bullish reversal shape) ------------------------------
        df["cdl_hammer"] = (
            (abs_body > 0)
            & (lower_wick >= self.hammer_lower_wick_mult * abs_body)
            & (upper_wick <= self.hammer_upper_wick_mult * abs_body)
            & (body_ratio <= self.hammer_max_body_ratio)
        )

        # --- shooting star (bearish reversal shape) -----------------------
        df["cdl_shooting_star"] = (
            (abs_body > 0)
            & (upper_wick >= self.hammer_lower_wick_mult * abs_body)
            & (lower_wick <= self.hammer_upper_wick_mult * abs_body)
            & (body_ratio <= self.hammer_max_body_ratio)
        )

        # --- engulfing ----------------------------------------------------
        bull_prev = prev_body < 0  # prior candle bearish
        bear_prev = prev_body > 0  # prior candle bullish
        df["cdl_engulfing_bull"] = (
            bull_prev & (body > 0) & (df["open"] <= prev_close) & (df["close"] >= prev_open)
        )
        df["cdl_engulfing_bear"] = (
            bear_prev & (body < 0) & (df["open"] >= prev_close) & (df["close"] <= prev_open)
        )

        # --- harami (inside bar) ------------------------------------------
        inside_body = (df["open"] >= prev_close) & (df["close"] <= prev_open)
        inside_body_bear = (df["open"] <= prev_close) & (df["close"] >= prev_open)
        df["cdl_harami_bull"] = bull_prev & (abs_body <= prev_abs_body) & inside_body
        df["cdl_harami_bear"] = bear_prev & (abs_body <= prev_abs_body) & inside_body_bear

        # --- swing continuation / breakdown (reuse MarketStructureAnalyzer)
        swings = MarketStructureAnalyzer(
            swing_left=self.swing_left, swing_right=self.swing_right
        ).analyze(df)
        last_swing_low = (
            df["low"].where(swings["swing_low"]).ffill().fillna(df["low"].expanding().min())
        )
        df["swing_continuation"] = swings["market_structure"] == "Trend Continuation"
        df["swing_breakdown"] = (df["close"] < last_swing_low) & (swings["trend"] != "Uptrend")

        # --- combined direction enum --------------------------------------
        bull = (
            df["cdl_engulfing_bull"]
            | df["cdl_hammer"]
            | df["cdl_harami_bull"]
            | df["swing_continuation"]
        )
        bear = (
            df["cdl_engulfing_bear"]
            | df["cdl_shooting_star"]
            | df["cdl_harami_bear"]
            | df["swing_breakdown"]
        )
        direction = pd.Series("NEUTRAL", index=df.index)
        direction[bear] = "BEAR"
        direction[bull] = "BULL"
        df["cdl_direction"] = direction

        return df

    def _column_names(self) -> list[str]:
        return [
            "cdl_doji",
            "cdl_hammer",
            "cdl_shooting_star",
            "cdl_engulfing_bull",
            "cdl_engulfing_bear",
            "cdl_harami_bull",
            "cdl_harami_bear",
            "swing_continuation",
            "swing_breakdown",
            "cdl_direction",
        ]


# Convenience frozen detector configs kept for callers that want a single
# boolean column without the full compute() output.
@dataclass(frozen=True)
class PatternColumns:
    """Static registry of pattern column names produced by compute()."""

    DOJI: str = "cdl_doji"
    HAMMER: str = "cdl_hammer"
    SHOOTING_STAR: str = "cdl_shooting_star"
    ENGULFING_BULL: str = "cdl_engulfing_bull"
    ENGULFING_BEAR: str = "cdl_engulfing_bear"
    HARAMI_BULL: str = "cdl_harami_bull"
    HARAMI_BEAR: str = "cdl_harami_bear"
    SWING_CONTINUATION: str = "swing_continuation"
    SWING_BREAKDOWN: str = "swing_breakdown"
    DIRECTION: str = "cdl_direction"

    ALL: tuple[str, ...] = field(
        default=(
            DOJI,
            HAMMER,
            SHOOTING_STAR,
            ENGULFING_BULL,
            ENGULFING_BEAR,
            HARAMI_BULL,
            HARAMI_BEAR,
            SWING_CONTINUATION,
            SWING_BREAKDOWN,
            DIRECTION,
        )
    )
