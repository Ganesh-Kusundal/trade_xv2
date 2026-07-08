import pandas as pd


class RSI:
    def __init__(self, period: int = 14):
        self.period = period

    def calculate(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        delta = close.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        avg_gain = gains.ewm(alpha=1 / self.period, min_periods=self.period).mean()
        avg_loss = losses.ewm(alpha=1 / self.period, min_periods=self.period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)
        return rsi
