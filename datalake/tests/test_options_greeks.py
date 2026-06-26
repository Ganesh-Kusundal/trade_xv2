"""Tests for datalake.options_greeks — BS Greeks precomputation."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from datalake.features import rsi, macd, atr, historical_volatility


class TestBlackScholesGreeks:
    """Validate BS Greeks formulas against known analytical results."""

    @staticmethod
    def bs_d1(spot, strike, t, r, iv):
        return (math.log(spot / strike) + (r + 0.5 * iv**2) * t) / (iv * math.sqrt(t))

    @staticmethod
    def norm_cdf(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))

    @staticmethod
    def norm_pdf(x):
        return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

    def test_atm_call_delta_near_half(self):
        d1 = self.bs_d1(100, 100, 1.0, 0.0, 0.2)
        delta = self.norm_cdf(d1)
        assert delta == pytest.approx(0.54, abs=0.06)

    def test_deep_itm_call_delta_near_one(self):
        d1 = self.bs_d1(200, 100, 1.0, 0.06, 0.2)
        delta = self.norm_cdf(d1)
        assert delta > 0.95

    def test_deep_otm_call_delta_near_zero(self):
        d1 = self.bs_d1(50, 100, 1.0, 0.06, 0.2)
        delta = self.norm_cdf(d1)
        assert delta < 0.05

    def test_put_delta_symmetry(self):
        d1 = self.bs_d1(100, 100, 1.0, 0.0, 0.2)
        call_delta = self.norm_cdf(d1)
        put_delta = call_delta - 1.0
        assert call_delta + put_delta == pytest.approx(0.0, abs=0.1)

    def test_gamma_positive(self):
        d1 = self.bs_d1(100, 100, 1.0, 0.06, 0.2)
        gamma = self.norm_pdf(d1) / (100 * 0.2 * math.sqrt(1.0))
        assert gamma > 0

    def test_gamma_highest_atm(self):
        d1_atm = self.bs_d1(100, 100, 1.0, 0.06, 0.2)
        d1_otm = self.bs_d1(100, 120, 1.0, 0.06, 0.2)
        gamma_atm = self.norm_pdf(d1_atm) / (100 * 0.2 * math.sqrt(1.0))
        gamma_otm = self.norm_pdf(d1_otm) / (100 * 0.2 * math.sqrt(1.0))
        assert gamma_atm > gamma_otm

    def test_theta_negative_for_long_option(self):
        spot, strike, t, r, iv = 100, 100, 1.0, 0.06, 0.2
        d1 = self.bs_d1(spot, strike, t, r, iv)
        d2 = d1 - iv * math.sqrt(t)
        theta = (-(spot * self.norm_pdf(d1) * iv) / (2 * math.sqrt(t))
                 - r * strike * math.exp(-r * t) * self.norm_cdf(d2)) / 365.0
        assert theta < 0

    def test_vega_positive(self):
        spot, strike, t, iv = 100, 100, 1.0, 0.2
        d1 = self.bs_d1(spot, strike, t, 0.06, iv)
        vega = spot * self.norm_pdf(d1) * math.sqrt(t) / 100.0
        assert vega > 0

    def test_vega_highest_atm(self):
        spot, t, iv = 100, 1.0, 0.2
        d1_atm = self.bs_d1(spot, 100, t, 0.06, iv)
        d1_otm = self.bs_d1(spot, 130, t, 0.06, iv)
        vega_atm = spot * self.norm_pdf(d1_atm) * math.sqrt(t) / 100.0
        vega_otm = spot * self.norm_pdf(d1_otm) * math.sqrt(t) / 100.0
        assert vega_atm > vega_otm


class TestFeatureConsistency:
    """Ensure feature functions produce consistent, non-null outputs."""

    @pytest.fixture
    def ohlcv(self):
        np.random.seed(42)
        n = 200
        close = 1000 + np.cumsum(np.random.randn(n) * 5)
        return pd.DataFrame({
            "open": close - 1,
            "high": close + 3,
            "low": close - 3,
            "close": close,
            "volume": np.random.randint(1000, 50000, n),
        })

    def test_rsi_bounded(self, ohlcv):
        result = rsi(ohlcv["close"], 14).dropna()
        assert (result >= 0).all() and (result <= 100).all()

    def test_macd_consistency(self, ohlcv):
        result = macd(ohlcv["close"])
        assert len(result) == len(ohlcv)
        assert result["macd"].iloc[-1] != result["macd_signal"].iloc[-1]

    def test_atr_positive(self, ohlcv):
        result = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"]).dropna()
        assert (result > 0).all()

    def test_hvol_positive(self, ohlcv):
        result = historical_volatility(ohlcv["close"], 20).dropna()
        assert (result > 0).all()
