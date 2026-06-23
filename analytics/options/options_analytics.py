"""Options, open-interest, PCR, max-pain, IV, Greeks, and option-flow analytics."""

from __future__ import annotations

import logging
import math

import pandas as pd

from analytics.core.models import AnalysisResult
from analytics.indicators.technical import iv_percentile, iv_rank

logger = logging.getLogger(__name__)


class OptionsAnalytics:
    def analyze(
        self,
        underlying: str,
        chain: pd.DataFrame | dict,
        *,
        spot_price: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
        multiplier: float = 1.0,
    ) -> AnalysisResult:
        option_chain = self._normalize_chain(chain)
        if option_chain.empty:
            logger.debug("OptionsAnalytics: empty chain for %s", underlying)
            return AnalysisResult(name="options", symbol=underlying, summary="No option-chain data")

        oi_result = OpenInterestAnalytics().analyze(option_chain)
        pcr_result = PCRAnalytics().analyze(option_chain)
        max_pain_result = MaxPainAnalytics().analyze(option_chain, spot_price)
        iv_result = IVAnalytics().analyze(option_chain, iv_history)
        greeks_result = GreeksAnalytics().analyze(option_chain, multiplier, spot_price=spot_price)
        flow_result = OptionFlowAnalytics().analyze(option_chain)
        strike_result = StrikeAnalytics().analyze(option_chain, spot_price)

        composite = (
            float(pcr_result.scores.get("pcr", 50.0)) * 0.25
            + float(iv_result.scores.get("iv", 50.0)) * 0.20
            + float(flow_result.scores.get("option_flow", 50.0)) * 0.20
            + float(strike_result.scores.get("strike_balance", 50.0)) * 0.35
        )
        regime = "Bullish" if composite >= 60 else "Bearish" if composite <= 40 else "Neutral"

        return AnalysisResult(
            name="options",
            symbol=underlying,
            summary=f"{underlying}: {regime} options regime.",
            metrics={
                **oi_result.metrics,
                **pcr_result.metrics,
                **max_pain_result.metrics,
                **iv_result.metrics,
                **greeks_result.metrics,
                **flow_result.metrics,
                **strike_result.metrics,
            },
            scores={
                "oi": float(oi_result.scores.get("oi", 50.0)),
                "pcr": float(pcr_result.scores.get("pcr", 50.0)),
                "iv": float(iv_result.scores.get("iv", 50.0)),
                "option_flow": float(flow_result.scores.get("option_flow", 50.0)),
                "strike_balance": float(strike_result.scores.get("strike_balance", 50.0)),
                "composite": composite,
            },
            signals=[regime, *pcr_result.signals, *flow_result.signals],
            recommendations=[
                "Use max pain and OI walls as reference zones, not standalone trade triggers.",
                "Confirm option-flow signals with price action and volume.",
            ],
            raw={
                "oi": oi_result.to_dict(),
                "pcr": pcr_result.to_dict(),
                "max_pain": max_pain_result.to_dict(),
                "iv": iv_result.to_dict(),
                "greeks": greeks_result.to_dict(),
                "flow": flow_result.to_dict(),
                "strikes": strike_result.to_dict(),
            },
        )

    def _normalize_chain(self, chain: pd.DataFrame | dict) -> pd.DataFrame:
        if isinstance(chain, pd.DataFrame):
            df = chain.copy()
        else:
            strikes = chain.get("strikes", []) if isinstance(chain, dict) else []
            df = pd.DataFrame(strikes)
        if df.empty:
            return pd.DataFrame()

        rename = {"type": "option_type", "opt_type": "option_type", "strike_price": "strike"}
        df = df.rename(columns=rename)
        required = {"strike", "option_type"}
        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"Option chain missing required columns: {sorted(missing)}")

        for column in ["strike", "oi", "change_in_oi", "volume", "iv", "ltp", "ltp_change", "price_change", "delta", "gamma", "vega", "theta"]:
            if column in df:
                df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
        df["option_type"] = df["option_type"].astype(str).str.upper().str.replace("CALL", "CE", regex=False).str.replace("PUT", "PE", regex=False)
        return df


class OpenInterestAnalytics:
    def analyze(self, chain: pd.DataFrame, concentration_top_n: int = 5) -> AnalysisResult:
        calls = chain[chain["option_type"] == "CE"]
        puts = chain[chain["option_type"] == "PE"]
        highest_call = self._highest(calls)
        highest_put = self._highest(puts)
        total_oi = float(chain["oi"].sum()) if not chain.empty else 0.0
        concentration = 0.0
        if total_oi > 0:
            concentration = float(chain.nlargest(concentration_top_n, "oi")["oi"].sum() / total_oi * 100)
        oi_shift = float(chain["change_in_oi"].sum()) if "change_in_oi" in chain else 0.0
        return AnalysisResult(
            name="open_interest",
            summary="Open-interest concentration calculated.",
            metrics={
                "highest_call_oi_strike": highest_call.get("strike"),
                "highest_call_oi": highest_call.get("oi", 0.0),
                "highest_put_oi_strike": highest_put.get("strike"),
                "highest_put_oi": highest_put.get("oi", 0.0),
                "oi_concentration_pct": concentration,
                "oi_shift": oi_shift,
            },
            scores={"oi": min(100.0, max(0.0, 50.0 + oi_shift / max(total_oi, 1.0) * 100))},
        )

    def _highest(self, data: pd.DataFrame) -> dict[str, float | None]:
        if data.empty:
            return {"strike": None, "oi": 0.0}
        row = data.loc[data["oi"].idxmax()]
        return {"strike": float(row["strike"]), "oi": float(row["oi"])}


class PCRAnalytics:
    def analyze(self, chain: pd.DataFrame, previous_pcr: float | None = None) -> AnalysisResult:
        calls = float(chain.loc[chain["option_type"] == "CE", "oi"].sum())
        puts = float(chain.loc[chain["option_type"] == "PE", "oi"].sum())
        pcr = puts / calls if calls > 0 else 0.0
        if previous_pcr is None:
            trend = "Flat"
        elif pcr > previous_pcr * 1.05:
            trend = "Rising"
        elif pcr < previous_pcr * 0.95:
            trend = "Falling"
        else:
            trend = "Stable"
        regime = "Bullish" if pcr >= 1.2 else "Bearish" if pcr <= 0.7 else "Neutral"
        score = min(100.0, max(0.0, 50.0 + (pcr - 1.0) * 50.0))
        return AnalysisResult(
            name="pcr",
            summary=f"PCR {pcr:.2f}, regime {regime}.",
            metrics={"pcr": pcr, "pcr_trend": trend, "pcr_regime": regime, "put_oi": puts, "call_oi": calls},
            scores={"pcr": score},
            signals=[regime],
        )


class MaxPainAnalytics:
    def analyze(self, chain: pd.DataFrame, spot_price: float | None = None) -> AnalysisResult:
        if chain.empty:
            return AnalysisResult(name="max_pain", summary="No strikes available", metrics={"max_pain": None})
        calls = chain[chain["option_type"] == "CE"].set_index("strike")["oi"]
        puts = chain[chain["option_type"] == "PE"].set_index("strike")["oi"]
        strikes = sorted(chain["strike"].unique())
        strike_series = pd.Series(strikes, index=strikes, dtype="float64")
        pain = {}
        for strike in strikes:
            call_pain = float((calls.reindex(strikes, fill_value=0) * (strike_series - strike).clip(lower=0)).sum())
            put_pain = float((puts.reindex(strikes, fill_value=0) * (strike - strike_series).clip(lower=0)).sum())
            pain[strike] = call_pain + put_pain
        max_pain = min(pain, key=pain.get)
        shift = None if spot_price is None else float(max_pain - spot_price)
        return AnalysisResult(
            name="max_pain",
            summary=f"Current max pain is {max_pain}.",
            metrics={"current_max_pain": max_pain, "max_pain_shift": shift, "pain_by_strike": pain},
        )


class IVAnalytics:
    def analyze(self, chain: pd.DataFrame, history: list[float] | pd.Series | None = None) -> AnalysisResult:
        iv = chain["iv"] if "iv" in chain else pd.Series(dtype="float64")
        current_iv = float(iv.mean()) if not iv.empty else 0.0
        iv_low = float(iv.min()) if not iv.empty else 0.0
        iv_high = float(iv.max()) if not iv.empty else current_iv
        ivr = iv_rank(current_iv, iv_low, iv_high)
        ivp = iv_percentile(current_iv, history) if history is not None else 50.0
        expansion = current_iv > iv_low * 1.25 if iv_low > 0 else False
        contraction = current_iv < iv_high * 0.75 if iv_high > 0 else False
        regime = "High" if ivr >= 70 else "Low" if ivr <= 30 else "Normal"
        return AnalysisResult(
            name="iv",
            summary=f"IV regime is {regime}.",
            metrics={"current_iv": current_iv, "iv_percentile": ivp, "iv_rank": ivr, "iv_expansion": expansion, "iv_contraction": contraction},
            scores={"iv": ivr},
            signals=[regime],
        )


class GreeksAnalytics:
    def analyze(
        self,
        chain: pd.DataFrame,
        multiplier: float = 1.0,
        spot_price: float | None = None,
        risk_free_rate: float = 0.06,
        days_to_expiry: float | None = None,
    ) -> AnalysisResult:
        df = chain.copy()
        has_greeks = all(col in df.columns for col in ["delta", "gamma", "vega", "theta"])
        if not has_greeks and spot_price is not None:
            df = self._compute_greeks(df, spot_price, risk_free_rate, days_to_expiry)
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

    def _compute_greeks(
        self,
        chain: pd.DataFrame,
        spot: float,
        risk_free_rate: float,
        days_to_expiry: float | None,
    ) -> pd.DataFrame:
        df = chain.copy()
        if days_to_expiry is None:
            days_to_expiry = 30.0
        t = max(days_to_expiry / 365.0, 1 / 365.0)
        
        # Pre-allocate columns
        df["delta"] = 0.0
        df["theta"] = 0.0
        df["gamma"] = 0.0
        df["vega"] = 0.0
        
        # Vectorized computation where possible, fallback to row iteration for complex logic
        strikes = df["strike"].values
        ivs = df["iv"].fillna(0.2).clip(lower=0.01).values
        option_types = df["option_type"].fillna("CE").str.upper().values
        
        for i, (strike, iv, opt_type) in enumerate(zip(strikes, ivs, option_types)):
            d1, d2 = self._d1_d2(spot, float(strike), t, risk_free_rate, float(iv))
            if opt_type in ("CE", "CALL"):
                df.iat[i, df.columns.get_loc("delta")] = self._call_delta(d1)
                df.iat[i, df.columns.get_loc("theta")] = self._call_theta(spot, float(strike), t, risk_free_rate, float(iv), d1, d2) / 365.0
            else:
                df.iat[i, df.columns.get_loc("delta")] = self._put_delta(d1)
                df.iat[i, df.columns.get_loc("theta")] = self._put_theta(spot, float(strike), t, risk_free_rate, float(iv), d1, d2) / 365.0
            df.iat[i, df.columns.get_loc("gamma")] = self._gamma(spot, t, float(iv), d1)
            df.iat[i, df.columns.get_loc("vega")] = self._vega(spot, t, float(iv), d1) / 100.0

        return df

    @staticmethod
    def _d1_d2(spot: float, strike: float, t: float, r: float, iv: float) -> tuple[float, float]:
        d1 = (math.log(spot / strike) + (r + 0.5 * iv**2) * t) / (iv * math.sqrt(t))
        d2 = d1 - iv * math.sqrt(t)
        return d1, d2

    @staticmethod
    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))

    @staticmethod
    def _norm_pdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

    def _call_delta(self, d1: float) -> float:
        return self._norm_cdf(d1)

    def _put_delta(self, d1: float) -> float:
        return self._norm_cdf(d1) - 1.0

    def _gamma(self, spot: float, t: float, iv: float, d1: float) -> float:
        return self._norm_pdf(d1) / (spot * iv * math.sqrt(t))

    def _vega(self, spot: float, t: float, iv: float, d1: float) -> float:
        return spot * self._norm_pdf(d1) * math.sqrt(t) / 100.0

    def _call_theta(
        self, spot: float, strike: float, t: float, r: float, iv: float, d1: float, d2: float,
    ) -> float:
        term1 = -(spot * self._norm_pdf(d1) * iv) / (2 * math.sqrt(t))
        term2 = r * strike * math.exp(-r * t) * self._norm_cdf(d2)
        return term1 - term2

    def _put_theta(
        self, spot: float, strike: float, t: float, r: float, iv: float, d1: float, d2: float,
    ) -> float:
        term1 = -(spot * self._norm_pdf(d1) * iv) / (2 * math.sqrt(t))
        term2 = -r * strike * math.exp(-r * t) * self._norm_cdf(-d2)
        return term1 + term2


class OptionFlowAnalytics:
    def analyze(self, chain: pd.DataFrame) -> AnalysisResult:
        calls = chain[chain["option_type"] == "CE"]
        puts = chain[chain["option_type"] == "PE"]
        call_volume = float(calls["volume"].sum()) if not calls.empty else 0.0
        put_volume = float(puts["volume"].sum()) if not puts.empty else 0.0
        call_oi_change = float(calls["change_in_oi"].sum()) if "change_in_oi" in calls else 0.0
        put_oi_change = float(puts["change_in_oi"].sum()) if "change_in_oi" in puts else 0.0
        if "ltp_change" in chain:
            price_change_col = "ltp_change"
        elif "price_change" in chain:
            price_change_col = "price_change"
        else:
            price_change_col = ""
        call_price_change = float(calls[price_change_col].sum()) if price_change_col and price_change_col in calls else 0.0
        put_price_change = float(puts[price_change_col].sum()) if price_change_col and price_change_col in puts else 0.0

        signals = []
        if call_volume > 0 and call_oi_change > 0 and call_price_change > 0:
            signals.append("Call Buying")
        if call_volume > 0 and call_oi_change < 0:
            signals.append("Call Writing")
        if put_volume > 0 and put_oi_change > 0 and put_price_change < 0:
            signals.append("Put Buying")
        if put_volume > 0 and put_oi_change < 0:
            signals.append("Put Writing")
        if not signals:
            signals.append("Neutral Flow")

        score = 50.0 + (call_oi_change - put_oi_change) / max(call_oi_change + abs(put_oi_change), 1.0) * 25.0
        return AnalysisResult(
            name="option_flow",
            summary=", ".join(signals),
            metrics={
                "call_volume": call_volume,
                "put_volume": put_volume,
                "call_oi_change": call_oi_change,
                "put_oi_change": put_oi_change,
            },
            scores={"option_flow": max(0.0, min(100.0, score))},
            signals=signals,
        )


class StrikeAnalytics:
    def analyze(self, chain: pd.DataFrame, spot_price: float | None = None) -> AnalysisResult:
        if chain.empty:
            return AnalysisResult(name="strikes", summary="No strikes available", metrics={})
        chain = chain.copy()
        chain["total_oi"] = chain["oi"]
        chain["liquidity"] = chain["total_oi"] + chain.get("volume", 0) * 0.25
        highest_put = chain.loc[chain["option_type"] == "PE", "oi"].idxmax()
        highest_call = chain.loc[chain["option_type"] == "CE", "oi"].idxmax()
        threshold = float(chain["liquidity"].quantile(0.90)) if not chain.empty else 0.0
        walls = chain.loc[chain["liquidity"] >= threshold, ["strike", "option_type", "liquidity"]].to_dict("records")
        support = float(chain.loc[highest_put, "strike"]) if pd.notna(highest_put) else None
        resistance = float(chain.loc[highest_call, "strike"]) if pd.notna(highest_call) else None
        balance = 50.0
        if spot_price is not None and support is not None and resistance is not None:
            if support < spot_price < resistance:
                balance = 65.0
            elif spot_price > resistance or spot_price < support:
                balance = 35.0
        return AnalysisResult(
            name="strikes",
            summary="Support, resistance, OI walls, and liquidity zones calculated.",
            metrics={
                "support": support,
                "resistance": resistance,
                "oi_walls": walls,
                "liquidity_zones": chain.nlargest(5, "liquidity")[["strike", "option_type", "liquidity"]].to_dict("records"),
            },
            scores={"strike_balance": balance},
        )
