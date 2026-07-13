"""Tests for Black-Scholes Greeks computation."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.options._greeks import GreeksAnalytics, _d1_d2, _norm_cdf


def _chain_with_greeks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strike": 100,
                "option_type": "CE",
                "oi": 100,
                "iv": 0.20,
                "delta": 0.6,
                "gamma": 0.02,
                "vega": 0.1,
                "theta": -0.05,
            },
            {
                "strike": 110,
                "option_type": "CE",
                "oi": 50,
                "iv": 0.25,
                "delta": 0.4,
                "gamma": 0.015,
                "vega": 0.08,
                "theta": -0.04,
            },
            {
                "strike": 100,
                "option_type": "PE",
                "oi": 80,
                "iv": 0.22,
                "delta": -0.4,
                "gamma": 0.02,
                "vega": 0.1,
                "theta": -0.03,
            },
            {
                "strike": 90,
                "option_type": "PE",
                "oi": 60,
                "iv": 0.28,
                "delta": -0.6,
                "gamma": 0.018,
                "vega": 0.09,
                "theta": -0.04,
            },
        ]
    )


def _chain_without_greeks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"strike": 100, "option_type": "CE", "oi": 100, "iv": 0.20},
            {"strike": 110, "option_type": "CE", "oi": 50, "iv": 0.25},
            {"strike": 100, "option_type": "PE", "oi": 80, "iv": 0.22},
            {"strike": 90, "option_type": "PE", "oi": 60, "iv": 0.28},
        ]
    )


def test_greeks_with_provided_data() -> None:
    chain = _chain_with_greeks()
    result = GreeksAnalytics().analyze(chain, multiplier=1.0)
    assert "delta_exposure" in result.metrics
    assert "gamma_exposure" in result.metrics
    assert "vega_exposure" in result.metrics
    assert "theta_exposure" in result.metrics


def test_greeks_computed_from_spot() -> None:
    chain = _chain_without_greeks()
    result = GreeksAnalytics().analyze(chain, multiplier=1.0, spot_price=105, days_to_expiry=30)
    assert result.metrics["delta_exposure"] != 0.0
    assert result.metrics["gamma_exposure"] > 0
    assert result.metrics["vega_exposure"] > 0


def test_greeks_without_spot_defaults_to_zero() -> None:
    chain = _chain_without_greeks()
    result = GreeksAnalytics().analyze(chain, multiplier=1.0)
    assert result.metrics["delta_exposure"] == 0.0
    assert result.metrics["gamma_exposure"] == 0.0


def test_net_delta_signal() -> None:
    chain = pd.DataFrame(
        [
            {"strike": 100, "option_type": "CE", "oi": 100, "iv": 0.20},
            {"strike": 110, "option_type": "CE", "oi": 100, "iv": 0.25},
        ]
    )
    result = GreeksAnalytics().analyze(chain, multiplier=1.0, spot_price=105, days_to_expiry=30)
    signals = " ".join(result.signals)
    assert "long" in signals.lower() or "short" in signals.lower()


def test_norm_cdf() -> None:
    assert _norm_cdf(0) == pytest.approx(0.5, abs=1e-10)
    assert _norm_cdf(1.96) == pytest.approx(0.975, abs=0.01)
    assert _norm_cdf(-1.96) == pytest.approx(0.025, abs=0.01)


def test_d1_d2() -> None:
    d1, d2 = _d1_d2(100, 100, 1.0, 0.05, 0.2)
    assert d1 > d2
    assert d1 > 0
