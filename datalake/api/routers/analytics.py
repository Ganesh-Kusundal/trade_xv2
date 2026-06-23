"""Analytics endpoints (indicators, snapshots, market breadth)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.api.deps import get_view_manager, get_data_catalog
from datalake.api.auth import require_auth
from datalake.api.schemas import (
    IndicatorsResponse,
    IndicatorValue,
    ScannerSnapshot,
    ScannerCandidatesResponse,
    RelativeStrengthResponse,
    MarketBreadthResponse,
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
        query = f"""
            SELECT timestamp, symbol, {value_col}
            FROM {view_name}
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        
        results = vm.query(query, [symbol.upper(), limit]).fetchall()
        
        values = []
        for row in results:
            value = row[2]
            
            ts = row[0]
            if hasattr(ts, "timestamp"):
                ts_ms = int(ts.timestamp() * 1000)
            else:
                ts_ms = int(ts)
            
            values.append(IndicatorValue(
                timestamp=ts_ms,
                symbol=symbol,
                value=float(value) if value else 0.0,
            ))
        
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
            detail=f"Indicator fetch failed: {str(exc)}",
        )


@router.get("/snapshot", response_model=ScannerCandidatesResponse)
async def get_snapshot(
    limit: int = Query(50, ge=1, le=500, description="Max symbols"),
):
    """Get intraday scanner snapshot for all symbols.
    
    Returns v_intraday_snapshot with latest scanner scores,
    signals, and metrics for all active symbols.
    """
    vm = get_view_manager()
    
    try:
        query = """
            SELECT symbol, ltp, intraday_score, signal, trend,
                   rsi_approx, roc_5, relative_volume, day_high, day_low, day_volume
            FROM v_intraday_snapshot
            ORDER BY intraday_score DESC
            LIMIT ?
        """
        
        results = vm.query(query, [limit]).fetchall()
        
        candidates = []
        for row in results:
            candidates.append(ScannerSnapshot(
                symbol=row[0],
                ltp=float(row[1]) if row[1] else 0.0,
                intraday_score=float(row[2]) if row[2] else 0.0,
                signal=row[3] or "NEUTRAL",
                trend=row[4] or "Neutral",
                rsi_14=float(row[5]) if row[5] else None,
                roc_5=float(row[6]) if row[6] else None,
                relative_volume=float(row[7]) if row[7] else None,
                day_high=float(row[8]) if row[8] else None,
                day_low=float(row[9]) if row[9] else None,
                day_volume=float(row[10]) if row[10] else None,
            ))
        
        return ScannerCandidatesResponse(
            candidates=candidates,
            count=len(candidates),
        )
        
    except Exception as exc:
        logger.error("Snapshot fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot fetch failed: {str(exc)}",
        )


@router.get("/top-candidates", response_model=ScannerCandidatesResponse)
async def get_top_candidates(
    limit: int = Query(10, ge=1, le=50, description="Max candidates"),
):
    """Get top scanner candidates by intraday score.
    
    Returns v_top3_candidates or v_top10_candidates based on limit.
    """
    vm = get_view_manager()
    
    try:
        view_name = "v_top3_candidates" if limit <= 3 else "v_top10_candidates"
        
        query = f"""
            SELECT symbol, ltp, intraday_score, signal, trend,
                   rsi_14, roc_5, relative_volume, day_high, day_low, day_volume
            FROM {view_name}
            LIMIT ?
        """
        
        results = vm.query(query, [limit]).fetchall()
        
        candidates = []
        for row in results:
            candidates.append(ScannerSnapshot(
                symbol=row[0],
                ltp=float(row[1]) if row[1] else 0.0,
                intraday_score=float(row[2]) if row[2] else 0.0,
                signal=row[3] or "NEUTRAL",
                trend=row[4] or "Neutral",
                rsi_14=float(row[5]) if row[5] else None,
                roc_5=float(row[6]) if row[6] else None,
                relative_volume=float(row[7]) if row[7] else None,
                day_high=float(row[8]) if row[8] else None,
                day_low=float(row[9]) if row[9] else None,
                day_volume=float(row[10]) if row[10] else None,
            ))
        
        return ScannerCandidatesResponse(
            candidates=candidates,
            count=len(candidates),
        )
        
    except Exception as exc:
        logger.error("Top candidates fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Top candidates fetch failed: {str(exc)}",
        )


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
        data = pd.DataFrame([
            {
                "symbol": row[0],
                "ltp": float(row[1]) if row[1] else 0.0,
                "composite_score": float(row[2]) if row[2] else 50.0,
                "roc": float(row[3]) if row[3] else 0.0,
                "relative_volume": float(row[4]) if row[4] else 1.0,
            }
            for row in results
        ])
        
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
            detail=f"Relative strength fetch failed: {str(exc)}",
        )


@router.get("/market-breadth", response_model=MarketBreadthResponse)
async def get_market_breadth():
    """Get market breadth indicators (advances/declines, TRIN, McClellan).
    
    Uses real BreadthAnalytics to compute market breadth from
    intraday snapshot data.
    """
    try:
        from analytics.market_breadth import BreadthAnalytics
        import pandas as pd
        
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
            detail=f"Market breadth fetch failed: {str(exc)}",
        )


@router.get("/strategies")
async def list_strategies():
    """List registered strategy names."""
    from brokers.common.strategy.multi_strategy_runtime import MultiStrategyRuntime

    runtime = MultiStrategyRuntime()
    return {"strategies": runtime.list_strategies(), "count": len(runtime.list_strategies())}


@router.post("/strategies/run")
async def run_strategies(body: dict):
    """Build a multi-strategy pipeline for the given strategy names."""
    from analytics.strategy.registry import StrategyRegistry
    from brokers.common.strategy.multi_strategy_runtime import MultiStrategyRuntime

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
