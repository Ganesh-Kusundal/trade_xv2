"""Market-structure analytics."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class MarketStructureAnalyzer:
    def __init__(self, swing_left: int = 2, swing_right: int = 2) -> None:
        self._swing_left = swing_left
        self._swing_right = swing_right

    def analyze(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if df.empty:
            df["swing_high"] = False
            df["swing_low"] = False
            df["trend"] = "Neutral"
            df["market_structure"] = "Range"
            return df

        df["swing_high"] = self._detect_swing_highs(df["high"])
        df["swing_low"] = self._detect_swing_lows(df["low"])
        df["trend"] = self._vectorized_trend(df)
        df["market_structure"] = self._vectorized_structure(df)
        return df

    def _detect_swing_highs(self, high: pd.Series) -> pd.Series:
        """Detect swing highs without look-ahead bias.

        A bar is a swing high if its high is >= the max of the previous
        `swing_left` bars AND >= the max of the next `swing_right` bars.
        The swing is only confirmed after `swing_right` bars have passed,
        so we shift the result forward by `swing_right` to avoid using
        future data.
        """
        left_max = high.rolling(self._swing_left, min_periods=1).max().shift(1)
        right_max = high.rolling(self._swing_right, min_periods=1).max()
        confirmed = (high >= left_max) & (high >= right_max)
        # Shift back by swing_right so only confirmed swings are marked
        return confirmed.shift(self._swing_right).fillna(False).astype(bool)

    def _detect_swing_lows(self, low: pd.Series) -> pd.Series:
        """Detect swing lows without look-ahead bias.

        A bar is a swing low if its low is <= the min of the previous
        `swing_left` bars AND <= the min of the next `swing_right` bars.
        The swing is only confirmed after `swing_right` bars have passed.
        """
        left_min = low.rolling(self._swing_left, min_periods=1).min().shift(1)
        right_min = low.rolling(self._swing_right, min_periods=1).min()
        confirmed = (low <= left_min) & (low <= right_min)
        # Shift back by swing_right so only confirmed swings are marked
        return confirmed.shift(self._swing_right).fillna(False).astype(bool)

    def _vectorized_trend(self, df: pd.DataFrame) -> pd.Series:
        import pandas as pd

        result = pd.Series("Neutral", index=df.index)

        swing_highs = df.loc[df["swing_high"], "high"]
        swing_lows = df.loc[df["swing_low"], "low"]

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs.iloc[-1] > swing_highs.iloc[-2]
            hl = swing_lows.iloc[-1] > swing_lows.iloc[-2]
            lh = swing_highs.iloc[-1] < swing_highs.iloc[-2]
            ll = swing_lows.iloc[-1] < swing_lows.iloc[-2]

            if hh and hl:
                result.iloc[-1] = "Uptrend"
            elif lh and ll:
                result.iloc[-1] = "Downtrend"

        if result.iloc[-1] == "Neutral":
            ma20 = df["close"].rolling(20, min_periods=5).mean()
            last_close = df["close"].iloc[-1]
            last_ma = ma20.iloc[-1]
            if pd.notna(last_ma):
                if last_close > last_ma:
                    result.iloc[-1] = "Uptrend"
                elif last_close < last_ma:
                    result.iloc[-1] = "Downtrend"

        return result

    def _vectorized_structure(self, df: pd.DataFrame) -> pd.Series:
        import pandas as pd

        result = pd.Series("Neutral", index=df.index)

        rolling_high = df["high"].rolling(20, min_periods=5).max()
        rolling_low = df["low"].rolling(20, min_periods=5).min()
        rolling_mid = (rolling_high + rolling_low) / 2
        range_pct = (rolling_high - rolling_low) / df["close"].replace(0, 1e-10)

        close = df["close"]
        relative_volume = (
            df["relative_volume"]
            if "relative_volume" in df.columns
            else pd.Series(1.0, index=df.index)
        )
        atr_vals = df["atr"] if "atr" in df.columns else pd.Series(0.0, index=df.index)
        atr_ratio = atr_vals / df["close"].replace(0, 1e-10)

        trend = df["trend"] if "trend" in df.columns else pd.Series("Neutral", index=df.index)

        breakout_mask = (close >= rolling_high) & (relative_volume >= 1.5)
        pullback_mask = (trend == "Uptrend") & (close < rolling_mid) & (close > rolling_low)
        continuation_mask = trend.isin(["Uptrend", "Downtrend"]) & (close > rolling_mid)
        compression_mask = (range_pct <= 0.02) & (atr_ratio <= 0.015)
        range_mask = range_pct <= 0.035

        result[breakout_mask] = "Breakout"
        result[~breakout_mask & pullback_mask] = "Pullback"
        result[~breakout_mask & ~pullback_mask & continuation_mask] = "Trend Continuation"
        result[~breakout_mask & ~pullback_mask & ~continuation_mask & compression_mask] = (
            "Compression"
        )
        result[
            ~breakout_mask & ~pullback_mask & ~continuation_mask & ~compression_mask & range_mask
        ] = "Range"

        return result
