"""Strategy endpoints (signals, candidates)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from interface.api.auth import require_auth
from interface.api.deps import get_view_manager
from interface.api.schemas import StrategySignal, StrategySignalsResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/signals", response_model=StrategySignalsResponse)
async def get_strategy_signals(
    strategy: str = Query(..., description="Strategy name (halftrend, momentum, breakout)"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=500, description="Max signals"),
):
    """Get strategy signals.

    Queries DuckDB strategy views:
    - halftrend: v_strategy_halftrend
    - momentum: v_strategy_momentum
    - breakout: v_strategy_breakout
    """
    vm = get_view_manager()

    try:
        view_map = {
            "halftrend": "v_strategy_halftrend",
            "momentum": "v_strategy_momentum",
            "breakout": "v_strategy_breakout",
        }

        if strategy not in view_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid strategy '{strategy}'. Valid: {', '.join(view_map.keys())}",
            )

        view_name = view_map[strategy]

        if strategy == "halftrend":
            query = (
                "SELECT symbol, ltp, intraday_score, signal, trend, "
                "rsi_14, roc_5, relative_volume, atr_14, "
                "stop_loss, target "
                f"FROM {view_name}"
            )
        elif strategy == "momentum":
            query = (
                "SELECT symbol, ltp, intraday_score, signal, trend, "
                "rsi_14, roc_5, relative_volume, atr_14, "
                "entry_level, target_level "
                f"FROM {view_name}"
            )
        elif strategy == "breakout":
            query = (
                "SELECT symbol, ltp, intraday_score, signal, trend, "
                "rsi_14, roc_5, relative_volume, atr_14, "
                "breakout_stop, breakout_target "
                f"FROM {view_name}"
            )

        params = []

        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol.upper())

        query += " ORDER BY intraday_score DESC LIMIT ?"
        params.append(limit)

        results = vm.query(query, params).fetchall()

        signals = []
        for row in results:
            signals.append(
                StrategySignal(
                    symbol=row[0] if row else "",
                    timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
                    signal_type=row[3] or "NEUTRAL",
                    score=float(row[2]) if row[2] else 0.0,
                    stop_loss=float(row[9]) if row[9] else None,
                    target=float(row[10]) if row[10] else None,
                    metadata={
                        "ltp": float(row[1]) if row[1] else 0.0,
                        "trend": row[4],
                        "rsi": float(row[5]) if row[5] else None,
                        "roc_5": float(row[6]) if row[6] else None,
                        "rel_volume": float(row[7]) if row[7] else None,
                        "atr": float(row[8]) if row[8] else None,
                    },
                )
            )

        return StrategySignalsResponse(
            signals=signals,
            count=len(signals),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Strategy signals fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Strategy signals fetch failed: {exc!s}",
        ) from exc


@router.get("/candidates", response_model=StrategySignalsResponse)
async def get_strategy_candidates(
    limit: int = Query(20, ge=1, le=100, description="Max candidates"),
):
    """Get strategy candidates.

    Returns v_strategy_candidates with combined scanner + features.
    """
    vm = get_view_manager()

    try:
        query = """
            SELECT symbol, ltp, intraday_score, signal, trend,
                   rsi_14, roc_5, relative_volume, atr_14,
                   suggested_quantity
            FROM v_strategy_candidates
            ORDER BY intraday_score DESC
            LIMIT ?
        """

        results = vm.query(query, [limit]).fetchall()

        signals = []
        for row in results:
            signals.append(
                StrategySignal(
                    symbol=row[0],
                    timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
                    signal_type=row[3] or "NEUTRAL",
                    score=float(row[2]) if row[2] else 0.0,
                    metadata={
                        "ltp": float(row[1]) if row[1] else 0.0,
                        "trend": row[4],
                        "rsi": float(row[5]) if row[5] else None,
                        "roc_5": float(row[6]) if row[6] else None,
                        "rel_volume": float(row[7]) if row[7] else None,
                        "atr": float(row[8]) if row[8] else None,
                        "suggested_qty": int(row[9]) if row[9] else None,
                    },
                )
            )

        return StrategySignalsResponse(
            signals=signals,
            count=len(signals),
        )

    except Exception as exc:
        logger.error("Strategy candidates fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Strategy candidates fetch failed: {exc!s}",
        ) from exc
