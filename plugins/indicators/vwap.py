import pandas as pd


class VWAP:
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        return (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
