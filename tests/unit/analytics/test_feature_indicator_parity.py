"""Parity: analytics pipeline features delegate to domain indicators."""

from __future__ import annotations

import pandas as pd

from analytics.pipeline.features import ATR, EMA, MACD, RSI, SMA, VWAP


def _fixed_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 101.5, 103.0, 104.0, 103.5, 105.0],
            "high": [101.0, 102.5, 103.0, 102.0, 104.0, 105.0, 104.5, 106.0],
            "low": [99.5, 100.5, 101.0, 100.8, 102.5, 103.5, 103.0, 104.5],
            "close": [100.5, 102.0, 101.8, 101.2, 103.5, 104.2, 104.0, 105.5],
            "volume": [1000, 1100, 900, 1200, 1300, 1150, 1250, 1400],
        }
    )


def test_pipeline_indicators_match_domain_on_fixed_bars() -> None:
    """Golden assert: feature wrappers == domain.indicators on fixed OHLCV."""
    df = _fixed_bars()
    from domain.indicators.atr import ATR as DomainATR
    from domain.indicators.macd import MACD as DomainMACD
    from domain.indicators.moving_averages import EMA as DomainEMA
    from domain.indicators.moving_averages import SMA as DomainSMA
    from domain.indicators.rsi import RSI as DomainRSI
    from domain.indicators.vwap import VWAP as DomainVWAP

    atr_out = ATR(period=3).compute(df.copy())
    pd.testing.assert_series_equal(
        atr_out["atr"],
        DomainATR(period=3).calculate_frame(df),
        check_names=False,
    )

    vwap_out = VWAP().compute(df.copy())
    pd.testing.assert_series_equal(
        vwap_out["vwap"],
        DomainVWAP().calculate_frame(df),
        check_names=False,
    )

    rsi_out = RSI(period=3).compute(df.copy())
    pd.testing.assert_series_equal(
        rsi_out["rsi"],
        DomainRSI(period=3).calculate_frame(df),
        check_names=False,
    )

    sma_out = SMA(period=3).compute(df.copy())
    pd.testing.assert_series_equal(
        sma_out["sma"],
        DomainSMA(period=3).calculate_frame(df, "close"),
        check_names=False,
    )

    ema_out = EMA(period=3).compute(df.copy())
    pd.testing.assert_series_equal(
        ema_out["ema"],
        DomainEMA(period=3).calculate_frame(df, "close"),
        check_names=False,
    )

    macd_out = MACD(fast=3, slow=5, signal=2).compute(df.copy())
    domain_macd = DomainMACD(fast=3, slow=5, signal=2).calculate_frame(df)
    pd.testing.assert_series_equal(macd_out["macd_line"], domain_macd["macd"], check_names=False)
    pd.testing.assert_series_equal(
        macd_out["macd_signal"], domain_macd["signal"], check_names=False
    )
    pd.testing.assert_series_equal(
        macd_out["macd_histogram"], domain_macd["histogram"], check_names=False
    )
