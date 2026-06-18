"""Analytics endpoints (indicators, snapshots, market breadth)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from datalake.api.deps import get_view_manager
from datalake.api.schemas import (
    IndicatorsResponse,
    IndicatorValue,
    ScannerSnapshot,
    ScannerCandidatesResponse,
    RelativeStrengthResponse,
    MarketBreadthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
            "atr": "v_feature_atr",
            "vwap": "v_feature_vwap",
            "rsi": "v_feature_rsi",
            "momentum": "v_feature_momentum",
            "volume": "v_feature_volume",
        }
        
        if type not in view_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid indicator type '{type}'. Valid: {', '.join(view_map.keys())}",
            )
        
        view_name = view_map[type]
        query = f"""
            SELECT timestamp, symbol, *
            FROM {view_name}
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        
        results = vm.query(query, [symbol.upper(), limit]).fetchall()
        
        values = []
        for row in results:
            # Extract value based on indicator type
            if type == "atr":
                value = row[2]  # atr_14
            elif type == "vwap":
                value = row[2]  # vwap
            elif type == "rsi":
                value = row[2]  # rsi_14
            elif type == "momentum":
                value = row[2]  # roc_5
            elif type == "volume":
                value = row[2]  # relative_volume
            else:
                value = 0.0
            
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
                   rsi_14, roc_5, relative_volume, day_high, day_low, day_volume
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
    """Get relative strength rankings."""
    # TODO: Implement with ranking engine
    return RelativeStrengthResponse(rankings=[], count=0)


@router.get("/market-breadth", response_model=MarketBreadthResponse)
async def get_market_breadth():
    """Get market breadth indicators (advances/declines, TRIN, McClellan)."""
    # TODO: Implement with BreadthAnalytics
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Market breadth not implemented yet",
    )
