"""Order-flow analytics: delta, absorption, large trades, bid-ask imbalance."""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.models import AnalysisResult

logger = logging.getLogger(__name__)


class OrderFlowAnalytics:
    def analyze(
        self,
        trades: pd.DataFrame | None = None,
        *,
        chain: pd.DataFrame | None = None,
        large_trade_pct: float = 0.90,
    ) -> AnalysisResult:
        if trades is not None and not trades.empty:
            return self._analyze_trades(trades, large_trade_pct)
        if chain is not None and not chain.empty:
            return self._analyze_chain(chain)
        return AnalysisResult(name="order_flow", summary="No order-flow data provided.", metrics={})

    def _analyze_trades(self, trades: pd.DataFrame, large_trade_pct: float) -> AnalysisResult:
        df = trades.copy()
        required = {"price", "quantity", "side"}
        if not required.issubset(df.columns):
            logger.warning("OrderFlow: trades missing columns %s", required - set(df.columns))
            return AnalysisResult(
                name="order_flow",
                summary="Trades missing required columns (price, quantity, side).",
                metrics={},
            )

        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
        df["side"] = df["side"].astype(str).str.upper()

        buy_vol = float(df.loc[df["side"].isin(["BUY", "B"]), "quantity"].sum())
        sell_vol = float(df.loc[df["side"].isin(["SELL", "S"]), "quantity"].sum())
        total_vol = buy_vol + sell_vol
        delta = buy_vol - sell_vol

        threshold = float(df["quantity"].quantile(large_trade_pct)) if not df.empty else 0
        large_trades = df[df["quantity"] >= threshold]
        large_buy = float(
            large_trades.loc[large_trades["side"].isin(["BUY", "B"]), "quantity"].sum()
        )
        large_sell = float(
            large_trades.loc[large_trades["side"].isin(["SELL", "S"]), "quantity"].sum()
        )

        buy_value = float(
            df.loc[df["side"].isin(["BUY", "B"]), "price"]
            .mul(df.loc[df["side"].isin(["BUY", "B"]), "quantity"])
            .sum()
        )
        sell_value = float(
            df.loc[df["side"].isin(["SELL", "S"]), "price"]
            .mul(df.loc[df["side"].isin(["SELL", "S"]), "quantity"])
            .sum()
        )

        absorption = self._detect_absorption(df)
        if absorption:
            logger.debug("OrderFlow absorption detected: %s", absorption)

        imbalance = delta / max(total_vol, 1.0) * 100
        score = max(0.0, min(100.0, 50.0 + imbalance * 0.5))

        signals = []
        if delta > 0:
            signals.append("Net buying pressure")
        elif delta < 0:
            signals.append("Net selling pressure")
        if large_buy > large_sell * 1.5:
            signals.append("Large trade buying dominance")
        elif large_sell > large_buy * 1.5:
            signals.append("Large trade selling dominance")
        if absorption:
            signals.append(f"Absorption detected: {absorption}")

        return AnalysisResult(
            name="order_flow",
            summary=f"Delta: {delta:,.0f}, Imbalance: {imbalance:.1f}%",
            metrics={
                "buy_volume": buy_vol,
                "sell_volume": sell_vol,
                "delta": delta,
                "total_volume": total_vol,
                "imbalance_pct": imbalance,
                "large_buy_volume": large_buy,
                "large_sell_volume": large_sell,
                "buy_value": buy_value,
                "sell_value": sell_value,
            },
            scores={"order_flow": score},
            signals=signals,
        )

    def _analyze_chain(self, chain: pd.DataFrame) -> AnalysisResult:
        df = chain.copy()
        calls = df[df.get("option_type", pd.Series(dtype=str)).str.upper().isin(["CE", "CALL"])]
        puts = df[df.get("option_type", pd.Series(dtype=str)).str.upper().isin(["PE", "PUT"])]

        call_vol = float(calls["volume"].sum()) if not calls.empty and "volume" in calls else 0.0
        put_vol = float(puts["volume"].sum()) if not puts.empty and "volume" in puts else 0.0
        call_oi_change = (
            float(calls["change_in_oi"].sum())
            if not calls.empty and "change_in_oi" in calls
            else 0.0
        )
        put_oi_change = (
            float(puts["change_in_oi"].sum()) if not puts.empty and "change_in_oi" in puts else 0.0
        )

        delta = call_vol - put_vol
        total = call_vol + put_vol
        imbalance = delta / max(total, 1.0) * 100
        score = max(0.0, min(100.0, 50.0 + imbalance * 0.5))

        signals = []
        if call_vol > 0 and call_oi_change > 0:
            signals.append("Call buying")
        if call_vol > 0 and call_oi_change < 0:
            signals.append("Call writing")
        if put_vol > 0 and put_oi_change > 0:
            signals.append("Put buying")
        if put_vol > 0 and put_oi_change < 0:
            signals.append("Put writing")

        return AnalysisResult(
            name="order_flow",
            summary=f"Option flow delta: {delta:,.0f}",
            metrics={
                "call_volume": call_vol,
                "put_volume": put_vol,
                "delta": delta,
                "call_oi_change": call_oi_change,
                "put_oi_change": put_oi_change,
            },
            scores={"order_flow": score},
            signals=signals or ["Neutral flow"],
        )

    @staticmethod
    def _detect_absorption(trades: pd.DataFrame) -> str | None:
        if len(trades) < 10:
            return None
        if "timestamp" not in trades.columns:
            return None
        df = trades.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        if len(df) < 10:
            return None

        window = max(len(df) // 5, 5)
        rolling_vol = df["quantity"].rolling(window, min_periods=1).sum()
        rolling_delta = (
            df.apply(
                lambda r: r["quantity"]
                if str(r["side"]).upper() in ("BUY", "B")
                else -r["quantity"],
                axis=1,
            )
            .rolling(window, min_periods=1)
            .sum()
        )

        high_vol = rolling_vol > rolling_vol.quantile(0.8)
        small_delta = rolling_delta.abs() < rolling_vol * 0.1

        absorptions = high_vol & small_delta
        if absorptions.any():
            last_idx = absorptions[absorptions].index[-1]
            side = "buying" if rolling_delta.loc[last_idx] > 0 else "selling"
            return f"High volume with minimal price impact ({side})"
        return None
