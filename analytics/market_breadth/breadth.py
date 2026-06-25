"""Market breadth analytics."""

from __future__ import annotations

import pandas as pd

from analytics.core.models import AnalysisResult


class BreadthAnalytics:
    def analyze(
        self,
        snapshot: pd.DataFrame | dict[str, float],
        *,
        history: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        data = (
            pd.Series(snapshot)
            if isinstance(snapshot, dict)
            else snapshot.iloc[-1]
            if not snapshot.empty
            else pd.Series(dtype="float64")
        )
        if data.empty:
            return AnalysisResult(name="breadth", summary="No breadth data")

        advances = float(data.get("advances", 0.0))
        declines = float(data.get("declines", 0.0))
        unchanged = float(data.get("unchanged", 0.0))
        new_highs = float(data.get("new_highs", 0.0))
        new_lows = float(data.get("new_lows", 0.0))
        total = advances + declines + unchanged
        adv_decline_ratio = (
            advances / declines if declines > 0 else float("inf") if advances > 0 else 0.0
        )
        breadth_score = 50.0
        if total > 0:
            breadth_score = advances / total * 100
        if new_highs > new_lows:
            breadth_score += min(20.0, (new_highs - new_lows) / max(total, 1.0) * 100)
        else:
            breadth_score -= min(20.0, (new_lows - new_highs) / max(total, 1.0) * 100)
        breadth_score = max(0.0, min(100.0, breadth_score))
        regime = (
            "Positive" if breadth_score >= 60 else "Negative" if breadth_score <= 40 else "Neutral"
        )

        metrics = {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "advance_decline_ratio": adv_decline_ratio,
            "new_highs": new_highs,
            "new_lows": new_lows,
            "total_issues": total,
        }
        signals = [regime]

        trin = self._compute_trin(
            advances, declines, data.get("up_volume", 0.0), data.get("down_volume", 0.0)
        )
        if trin is not None:
            metrics["trin"] = trin
            if trin < 0.5:
                signals.append("TRIN oversold (strong bullish)")
            elif trin > 2.0:
                signals.append("TRIN overbought (strong bearish)")

        mcclellan = None
        if history is not None and not history.empty:
            mcclellan = self._compute_mcclellan(history)
            if mcclellan is not None:
                metrics["mcclellan_oscillator"] = mcclellan
                if mcclellan > 0:
                    signals.append("McClellan positive (breadth improving)")
                elif mcclellan < -50:
                    signals.append("McClellan deeply negative (breadth deteriorating)")

        return AnalysisResult(
            name="breadth",
            summary=f"Market breadth is {regime}.",
            metrics=metrics,
            scores={"breadth": breadth_score},
            signals=signals,
        )

    @staticmethod
    def _compute_trin(
        advances: float, declines: float, up_volume: float, down_volume: float
    ) -> float | None:
        if declines == 0 or down_volume == 0:
            return None
        ad_ratio = advances / declines
        vol_ratio = up_volume / down_volume
        return ad_ratio / vol_ratio if vol_ratio > 0 else None

    @staticmethod
    def _compute_mcclellan(history: pd.DataFrame) -> float | None:
        if len(history) < 39:
            return None
        adv_col = "advances" if "advances" in history.columns else None
        dec_col = "declines" if "declines" in history.columns else None
        if adv_col is None or dec_col is None:
            return None
        df = history[[adv_col, dec_col]].copy()
        df["net"] = df[adv_col] - df[dec_col]
        ema19 = df["net"].ewm(span=19, adjust=False).mean()
        ema39 = df["net"].ewm(span=39, adjust=False).mean()
        return float(ema19.iloc[-1] - ema39.iloc[-1])


class SectorAnalytics:
    def analyze(self, sectors: pd.DataFrame) -> AnalysisResult:
        if sectors.empty:
            return AnalysisResult(name="sectors", summary="No sector data")
        df = sectors.copy()
        if "relative_strength" not in df:
            df["relative_strength"] = df.get("return_pct", 0.0)
        top = df.loc[df["relative_strength"].idxmax()]
        weak = df.loc[df["relative_strength"].idxmin()]
        rotation = "Risk-on" if float(top["relative_strength"]) > 0 else "Defensive"
        return AnalysisResult(
            name="sectors",
            summary=f"Top sector {top['sector']}, weak sector {weak['sector']}.",
            metrics={
                "top_sector": top["sector"],
                "weak_sector": weak["sector"],
                "sector_rotation": rotation,
                "relative_strength": df[["sector", "relative_strength"]].to_dict("records"),
            },
            scores={
                "sector_strength": max(
                    0.0, min(100.0, 50.0 + float(df["relative_strength"].mean()))
                )
            },
            signals=[rotation],
        )
