"""Greeks computation — delta, gamma, vega, theta, and related helpers."""

from __future__ import annotations

import math

import pandas as pd

from analytics.core.models import AnalysisResult
from domain.constants.market import DEFAULT_RISK_FREE_RATE


def _d1_d2(spot: float, strike: float, t: float, r: float, iv: float) -> tuple[float, float]:
    d1 = (math.log(spot / strike) + (r + 0.5 * iv**2) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    return d1, d2


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _call_delta(d1: float) -> float:
    return _norm_cdf(d1)


def _put_delta(d1: float) -> float:
    return _norm_cdf(d1) - 1.0


def _gamma(spot: float, t: float, iv: float, d1: float) -> float:
    return _norm_pdf(d1) / (spot * iv * math.sqrt(t))


def _vega(spot: float, t: float, iv: float, d1: float) -> float:
    return spot * _norm_pdf(d1) * math.sqrt(t) / 100.0


def _call_theta(spot: float, strike: float, t: float, r: float, iv: float, d1: float, d2: float) -> float:
    term1 = -(spot * _norm_pdf(d1) * iv) / (2 * math.sqrt(t))
    term2 = r * strike * math.exp(-r * t) * _norm_cdf(d2)
    return term1 - term2


def _put_theta(spot: float, strike: float, t: float, r: float, iv: float, d1: float, d2: float) -> float:
    term1 = -(spot * _norm_pdf(d1) * iv) / (2 * math.sqrt(t))
    term2 = -r * strike * math.exp(-r * t) * _norm_cdf(-d2)
    return term1 + term2


def compute_greeks(
    chain: pd.DataFrame,
    spot: float,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    days_to_expiry: float | None = None,
) -> pd.DataFrame:
    """Compute greeks for an option chain DataFrame."""
    df = chain.copy()
    if days_to_expiry is None:
        days_to_expiry = 30.0
    t = max(days_to_expiry / 365.0, 1 / 365.0)

    df["delta"] = 0.0
    df["theta"] = 0.0
    df["gamma"] = 0.0
    df["vega"] = 0.0

    strikes = df["strike"].values
    ivs = df["iv"].fillna(0.2).clip(lower=0.01).values
    option_types = df["option_type"].fillna("CE").str.upper().values

    for i, (strike, iv, opt_type) in enumerate(zip(strikes, ivs, option_types, strict=False)):
        d1, d2_val = _d1_d2(spot, float(strike), t, risk_free_rate, float(iv))
        if opt_type in ("CE", "CALL"):
            df.iat[i, df.columns.get_loc("delta")] = _call_delta(d1)
            df.iat[i, df.columns.get_loc("theta")] = (
                _call_theta(spot, float(strike), t, risk_free_rate, float(iv), d1, d2_val) / 365.0
            )
        else:
            df.iat[i, df.columns.get_loc("delta")] = _put_delta(d1)
            df.iat[i, df.columns.get_loc("theta")] = (
                _put_theta(spot, float(strike), t, risk_free_rate, float(iv), d1, d2_val) / 365.0
            )
        df.iat[i, df.columns.get_loc("gamma")] = _gamma(spot, t, float(iv), d1)
        df.iat[i, df.columns.get_loc("vega")] = _vega(spot, t, float(iv), d1) / 100.0

    return df


class GreeksAnalytics:
    def analyze(
        self,
        chain: pd.DataFrame,
        multiplier: float = 1.0,
        spot_price: float | None = None,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
        days_to_expiry: float | None = None,
    ) -> AnalysisResult:
        df = chain.copy()
        has_greeks = all(col in df.columns for col in ["delta", "gamma", "vega", "theta"])
        if not has_greeks and spot_price is not None:
            df = compute_greeks(df, spot_price, risk_free_rate, days_to_expiry)
        elif not has_greeks:
            for col in ["delta", "gamma", "vega", "theta"]:
                if col not in df:
                    df[col] = 0.0

        exposure = df["oi"] * multiplier
        delta_exp = float((df["delta"] * exposure).sum())
        gamma_exp = float((df["gamma"] * exposure).sum())
        vega_exp = float((df["vega"] * exposure).sum())
        theta_exp = float((df["theta"] * exposure).sum())

        net_delta = float(df["delta"].sum())
        net_gamma = float(df["gamma"].sum())
        signals = []
        if abs(net_delta) > 0.5:
            signals.append(f"Net delta {'long' if net_delta > 0 else 'short'} bias")
        if net_gamma > 0:
            signals.append("Positive gamma exposure")
        if theta_exp < 0:
            signals.append("Negative theta (time decay working against positions)")

        return AnalysisResult(
            name="greeks",
            summary="Greeks exposure calculated.",
            metrics={
                "delta_exposure": delta_exp,
                "gamma_exposure": gamma_exp,
                "vega_exposure": vega_exp,
                "theta_exposure": theta_exp,
                "net_delta": net_delta,
                "net_gamma": net_gamma,
            },
            signals=signals,
        )
