"""SMA/EMA frame adapters for analytics pipeline parity."""


class SMA:
    def __init__(self, period: int = 20, min_periods: int = 1) -> None:
        self.period = period
        self.min_periods = min_periods

    def calculate_frame(self, df, source: str = "close"):
        return df[source].rolling(window=self.period, min_periods=self.min_periods).mean()


class EMA:
    def __init__(self, period: int = 20) -> None:
        self.period = period

    def calculate_frame(self, df, source: str = "close"):
        return df[source].ewm(span=self.period, adjust=False).mean()
