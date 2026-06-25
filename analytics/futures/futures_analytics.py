"""Futures analytics engine."""

from __future__ import annotations

import logging

from analytics.core.models import AnalysisResult

logger = logging.getLogger(__name__)


class FuturesAnalytics:
    def analyze(
        self,
        symbol: str,
        *,
        spot_price: float | None = None,
        future_price: float | None = None,
        current_oi: float | None = None,
        next_oi: float | None = None,
        price_change: float = 0.0,
        oi_change: float = 0.0,
    ) -> AnalysisResult:
        basis_result = self.basis(spot_price, future_price)
        oi_result = self.oi_state(price_change, oi_change)
        rollover_result = self.rollover(current_oi, next_oi)
        strength = self.future_strength(basis_result, oi_result)
        score = 50.0
        if basis_result.metrics.get("basis_type") == "Premium":
            score += 10.0
        elif basis_result.metrics.get("basis_type") == "Discount":
            score -= 10.0
        if oi_result.signals and oi_result.signals[0] in {"Long Build-Up", "Short Covering"}:
            score += 20.0
        elif oi_result.signals and oi_result.signals[0] in {"Short Build-Up", "Long Unwinding"}:
            score -= 20.0

        return AnalysisResult(
            name="future",
            symbol=symbol,
            summary=f"{symbol}: {strength} future strength.",
            metrics={
                **basis_result.metrics,
                **oi_result.metrics,
                **rollover_result.metrics,
            },
            scores={"oi": float(oi_result.scores.get("oi", 50.0)), "future_strength": score},
            signals=[strength, *oi_result.signals],
            recommendations=["Confirm future strength with spot direction and OI build-up."],
            raw={
                "basis": basis_result.to_dict(),
                "oi": oi_result.to_dict(),
                "rollover": rollover_result.to_dict(),
            },
        )

    def basis(self, spot_price: float | None, future_price: float | None) -> AnalysisResult:
        if spot_price is None or future_price is None or spot_price <= 0:
            return AnalysisResult(
                name="basis",
                summary="Basis unavailable; spot and future prices are required.",
                metrics={"basis": None, "basis_pct": None, "basis_type": "Unavailable"},
            )
        basis = future_price - spot_price
        basis_pct = basis / spot_price * 100
        basis_type = "Premium" if basis > 0 else "Discount" if basis < 0 else "Flat"
        return AnalysisResult(
            name="basis",
            summary=f"Future is at {basis_type.lower()} to spot.",
            metrics={
                "spot": spot_price,
                "future": future_price,
                "basis": basis,
                "basis_pct": basis_pct,
                "basis_type": basis_type,
            },
        )

    def oi_state(self, price_change: float, oi_change: float) -> AnalysisResult:
        if price_change >= 0 and oi_change >= 0:
            state = "Long Build-Up"
            score = 80.0
        elif price_change < 0 and oi_change >= 0:
            state = "Short Build-Up"
            score = 20.0
        elif price_change < 0 and oi_change < 0:
            state = "Long Unwinding"
            score = 30.0
        else:
            state = "Short Covering"
            score = 70.0
        return AnalysisResult(
            name="oi_state",
            summary=state,
            metrics={"price_change": price_change, "oi_change": oi_change},
            scores={"oi": score},
            signals=[state],
        )

    def rollover(self, current_oi: float | None, next_oi: float | None) -> AnalysisResult:
        if current_oi is None or next_oi is None or next_oi <= 0:
            return AnalysisResult(
                name="rollover",
                summary="Roll-over unavailable; current and next OI are required.",
                metrics={"current_oi": current_oi, "next_oi": next_oi, "roll_pct": None},
            )
        roll_pct = current_oi / next_oi * 100
        return AnalysisResult(
            name="rollover",
            summary=f"Roll-over {roll_pct:.2f}%.",
            metrics={"current_oi": current_oi, "next_oi": next_oi, "roll_pct": roll_pct},
        )

    def future_strength(self, basis: AnalysisResult, oi: AnalysisResult) -> str:
        basis_type = basis.metrics.get("basis_type")
        oi_signal = oi.signals[0] if oi.signals else "Neutral"
        bullish = basis_type == "Premium" and oi_signal in {"Long Build-Up", "Short Covering"}
        bearish = basis_type == "Discount" and oi_signal in {"Short Build-Up", "Long Unwinding"}
        if bullish:
            return "Bullish"
        if bearish:
            return "Bearish"
        return "Neutral"
