"""Volume profile analytics."""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.models import AnalysisResult, normalize_ohlcv

logger = logging.getLogger(__name__)


class VolumeProfileBuilder:
    def __init__(self, bins: int = 100, value_area_pct: float = 70.0) -> None:
        if bins < 10:
            raise ValueError("bins must be >= 10")
        self._bins = bins
        self._value_area_pct = value_area_pct

    def build(self, data: pd.DataFrame, *, symbol: str | None = None) -> AnalysisResult:
        df = normalize_ohlcv(data, symbol=symbol)
        if df.empty:
            return AnalysisResult(name="volume_profile", symbol=symbol, summary="No price data")

        profile = self._build_profile(df)
        poc = profile.loc[profile["volume"].idxmax()]
        total_volume = float(profile["volume"].sum())
        value_area_volume = total_volume * self._value_area_pct / 100
        sorted_profile = profile.sort_values("volume", ascending=False)
        cumulative = sorted_profile["volume"].cumsum()
        value_area = sorted_profile.loc[cumulative <= value_area_volume]
        vah = float(value_area["price_high"].max()) if not value_area.empty else float(poc["price_high"])
        val = float(value_area["price_low"].min()) if not value_area.empty else float(poc["price_low"])
        hvn = profile.loc[profile["volume"] >= profile["volume"].quantile(0.75), ["price_low", "price_high", "volume"]].to_dict("records")
        lvn = profile.loc[profile["volume"] <= profile["volume"].quantile(0.25), ["price_low", "price_high", "volume"]].to_dict("records")

        return AnalysisResult(
            name="volume_profile",
            symbol=symbol or str(df["symbol"].iloc[-1]),
            summary=f"POC {poc['price_mid']:.2f}, VAH {vah:.2f}, VAL {val:.2f}.",
            metrics={
                "poc": float(poc["price_mid"]),
                "vah": vah,
                "val": val,
                "value_area_pct": self._value_area_pct,
                "hvn": hvn[:10],
                "lvn": lvn[:10],
                "profile": profile.to_dict("records"),
            },
            charts=[{"type": "volume_profile", "data": profile.to_dict("records")}],
        )

    def _build_profile(self, df: pd.DataFrame) -> pd.DataFrame:
        price_low = float(df["low"].min())
        price_high = float(df["high"].max())
        step = (price_high - price_low) / self._bins
        edges = [price_low + index * step for index in range(self._bins + 1)]
        bins = pd.cut(df["close"], bins=edges, include_lowest=True)
        profile = (
            df.assign(price_bin=bins)
            .groupby("price_bin", observed=False)
            .agg(
                volume=("volume", "sum"),
                price_low=("low", "min"),
                price_high=("high", "max"),
                price_mid=("close", "mean"),
            )
            .reset_index(drop=True)
        )
        profile["price_mid"] = profile.apply(lambda row: (row["price_low"] + row["price_high"]) / 2, axis=1)
        return profile[profile["volume"] > 0].reset_index(drop=True)
