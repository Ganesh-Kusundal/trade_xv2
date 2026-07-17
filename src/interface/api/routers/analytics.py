"""Analytics endpoints (indicators, snapshots, market breadth)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from interface.api.auth import require_auth
from interface.api.deps import get_view_manager
from interface.api.schemas import (
    IndicatorsResponse,
    IndicatorValue,
    MarketBreadthResponse,
    RelativeStrengthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/indicators", response_model=IndicatorsResponse)
async def get_indicators(
    symbol: str = Query(..., description="Symbol"),
    type: str = Query(..., description="Indicator type (atr, vwap, rsi, momentum, volume)"),
    timeframe: str = Query("1m", description="Timeframe"),
    limit: int = Query(100, ge=1, le=1000, description="Max values"),
):
    """Get technical indicator values for a symbol.

    Queries DuckDB feature views:
    - atr: v_feature_atr
    - vwap: v_feature_vwap
    - rsi: v_feature_rsi
    - momentum: v_feature_momentum
    - volume: v_feature_volume
    """
    vm = get_view_manager()

    try:
        view_map = {
            "atr": ("v_feature_atr", "atr_14"),
            "vwap": ("v_feature_vwap", "vwap"),
            "rsi": ("v_feature_rsi", "rsi_14"),
            "momentum": ("v_feature_momentum", "roc_5"),
            "volume": ("v_feature_volume", "relative_volume"),
        }

        if type not in view_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid indicator type '{type}'. Valid: {', '.join(view_map.keys())}",
            )

        view_name, value_col = view_map[type]
        query = (
            f"SELECT timestamp, symbol, {value_col} FROM {view_name} "
            "WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?"
        )

        results = vm.query(query, [symbol.upper(), limit]).fetchall()

        values = []
        for row in results:
            value = row[2]

            ts = row[0]
            ts_ms = int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else int(ts)

            values.append(
                IndicatorValue(
                    timestamp=ts_ms,
                    symbol=symbol,
                    value=float(value) if value else 0.0,
                )
            )

        return IndicatorsResponse(
            symbol=symbol,
            indicator_type=type,
            values=list(reversed(values)),  # Chronological order
            count=len(values),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Indicator fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indicator fetch failed: {exc!s}",
        ) from exc


@router.get("/relative-strength", response_model=RelativeStrengthResponse)
async def get_relative_strength(
    limit: int = Query(20, ge=1, le=100, description="Max symbols"),
):
    """Get relative strength rankings.

    Uses real RankingEngine to compute composite scores
    and rank symbols by relative strength.
    """
    try:
        from analytics.ranking import RankingEngine

        # Get snapshot data from DuckDB
        vm = get_view_manager()
        query = """
            SELECT symbol, ltp, intraday_score, roc_5, relative_volume
            FROM v_intraday_snapshot
            ORDER BY intraday_score DESC
            LIMIT ?
        """
        results = vm.query(query, [limit]).fetchall()

        if not results:
            return RelativeStrengthResponse(rankings=[], count=0)

        # Build DataFrame for ranking engine
        import pandas as pd

        data = pd.DataFrame(
            [
                {
                    "symbol": row[0],
                    "ltp": float(row[1]) if row[1] else 0.0,
                    "composite_score": float(row[2]) if row[2] else 50.0,
                    "roc": float(row[3]) if row[3] else 0.0,
                    "relative_volume": float(row[4]) if row[4] else 1.0,
                }
                for row in results
            ]
        )

        # Run ranking engine
        engine = RankingEngine()
        rankings = engine.top_relative_strength(data, limit=limit)

        return RelativeStrengthResponse(
            rankings=rankings,
            count=len(rankings),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Relative strength fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Relative strength fetch failed: {exc!s}",
        ) from exc


@router.get("/market-breadth", response_model=MarketBreadthResponse)
async def get_market_breadth():
    """Get market breadth indicators (advances/declines, TRIN, McClellan).

    Uses real BreadthAnalytics to compute market breadth from
    intraday snapshot data.
    """
    try:
        from analytics.market_breadth import BreadthAnalytics

        # Get snapshot data from DuckDB
        vm = get_view_manager()
        query = """
            SELECT
                COUNT(*) FILTER (WHERE intraday_score > 60) as advances,
                COUNT(*) FILTER (WHERE intraday_score < 40) as declines,
                COUNT(*) FILTER (WHERE intraday_score BETWEEN 40 AND 60) as unchanged,
                COUNT(*) FILTER (WHERE intraday_score > 80) as new_highs,
                COUNT(*) FILTER (WHERE intraday_score < 20) as new_lows,
                SUM(CASE WHEN intraday_score > 50 THEN day_volume ELSE 0 END) as up_volume,
                SUM(CASE WHEN intraday_score < 50 THEN day_volume ELSE 0 END) as down_volume
            FROM v_intraday_snapshot
        """
        results = vm.query(query).fetchone()

        if not results:
            # Return neutral breadth when no data
            return MarketBreadthResponse(
                advances=0.0,
                declines=0.0,
                unchanged=0.0,
                advance_decline_ratio=0.0,
                new_highs=0.0,
                new_lows=0.0,
                trin=None,
                mcclellan_oscillator=None,
                breadth_score=50.0,
                regime="Neutral",
            )

        # Build snapshot for BreadthAnalytics
        snapshot = {
            "advances": float(results[0]) if results[0] else 0.0,
            "declines": float(results[1]) if results[1] else 0.0,
            "unchanged": float(results[2]) if results[2] else 0.0,
            "new_highs": float(results[3]) if results[3] else 0.0,
            "new_lows": float(results[4]) if results[4] else 0.0,
            "up_volume": float(results[5]) if results[5] else 0.0,
            "down_volume": float(results[6]) if results[6] else 0.0,
        }

        # Run BreadthAnalytics
        analytics = BreadthAnalytics()
        result = analytics.analyze(snapshot)

        # Extract metrics from AnalysisResult
        metrics = result.metrics or {}
        scores = result.scores or {}
        signals = result.signals or []

        # Determine regime from signals or default
        regime = "Neutral"
        for signal in signals:
            if "Positive" in signal or "bullish" in signal.lower():
                regime = "Positive"
                break
            elif "Negative" in signal or "bearish" in signal.lower():
                regime = "Negative"
                break

        return MarketBreadthResponse(
            advances=metrics.get("advances", 0.0),
            declines=metrics.get("declines", 0.0),
            unchanged=metrics.get("unchanged", 0.0),
            advance_decline_ratio=metrics.get("advance_decline_ratio", 0.0),
            new_highs=metrics.get("new_highs", 0.0),
            new_lows=metrics.get("new_lows", 0.0),
            trin=metrics.get("trin"),
            mcclellan_oscillator=metrics.get("mcclellan_oscillator"),
            breadth_score=scores.get("breadth", 50.0),
            regime=regime,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Market breadth fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Market breadth fetch failed: {exc!s}",
        ) from exc


@router.get("/strategies")
async def list_strategies():
    """List registered strategy names."""
    from runtime.factory import build_multi_strategy_runtime

    runtime = build_multi_strategy_runtime()
    return {"strategies": runtime.list_strategies(), "count": len(runtime.list_strategies())}


@router.post("/strategies/run")
async def run_strategies(body: dict):
    """Build a multi-strategy pipeline for the given strategy names."""
    from analytics.strategy.registry import StrategyRegistry
    from application.trading.multi_strategy_runtime import MultiStrategyRuntime

    names = body.get("names") or body.get("strategies") or []
    if not names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="names required")
    StrategyRegistry.discover("analytics.strategy.builtins")
    pipeline = MultiStrategyRuntime.create_pipeline(names)
    if not pipeline.strategies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No valid strategies in {names}",
        )
    return {
        "strategy_count": len(pipeline.strategies),
        "strategies": [s.name for s in pipeline.strategies],
    }
