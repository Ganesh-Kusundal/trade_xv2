"""Backtest endpoints (run, results, comparison).

Wires the backtest engine into the API for on-demand backtest execution.
"""

from __future__ import annotations

import logging
import threading
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status

from interface.api.auth import require_auth
from interface.api.deps import get_datalake_gateway
from interface.api.schemas import (
    BacktestMetrics,
    BacktestResultResponse,
    BacktestRunRequest,
)
from datalake.research.backtest_cache_store import BacktestCacheStore

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


_backtest_cache: dict[str, BacktestResultResponse] = {}
_backtest_cache_lock = threading.Lock()
_cache_store = BacktestCacheStore()
_hydrated = False


def _ensure_hydrated() -> None:
    global _hydrated
    if _hydrated:
        return
    with _backtest_cache_lock:
        if _hydrated:
            return
        _backtest_cache.update(_cache_store.load_all())
        _hydrated = True


def _cache_result(resp: BacktestResultResponse) -> None:
    _ensure_hydrated()
    with _backtest_cache_lock:
        _backtest_cache[resp.run_id] = resp
    _cache_store.save(resp)


@router.post("/run", response_model=BacktestResultResponse)
async def run_backtest(
    req: BacktestRunRequest,
    gateway=Depends(get_datalake_gateway),
):
    """Run a backtest with the specified parameters.

    Executes the backtest engine against historical data from the
    Parquet data lake. Uses the same FeaturePipeline and StrategyPipeline
    as live trading for zero-parity backtesting.
    """
    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Data lake gateway not connected.",
        )

    try:
        lookback_days = req.years * 365
        df = gateway.history(
            symbol=req.symbol,
            exchange="NSE",
            timeframe=req.timeframe,
            lookback_days=lookback_days,
        )

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No historical data for symbol '{req.symbol}'",
            )

        from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline

        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))

        from analytics.strategy import BreakoutStrategy, MomentumStrategy, StrategyPipeline

        strategy_map = {
            "momentum": MomentumStrategy,
            "breakout": BreakoutStrategy,
        }
        strategy_cls = strategy_map.get(req.strategy, MomentumStrategy)
        strategy = StrategyPipeline(strategies=[strategy_cls()])

        from analytics.backtest import BacktestConfig, BacktestEngine

        config = BacktestConfig(
            initial_capital=req.initial_capital,
            warmup_bars=20,
        )
        engine = BacktestEngine(pipeline, strategy, config)
        result = engine.run(df, symbol=req.symbol)

        run_id = str(uuid.uuid4())[:12]
        m = result.metrics

        resp = BacktestResultResponse(
            run_id=run_id,
            symbol=req.symbol,
            timeframe=req.timeframe,
            metrics=BacktestMetrics(
                total_return_pct=round(m.total_return_pct, 2),
                annualized_return_pct=round(m.cagr, 2),
                sharpe_ratio=round(m.sharpe_ratio, 2),
                sortino_ratio=round(m.sortino_ratio, 2),
                max_drawdown_pct=round(m.max_drawdown, 2),
                profit_factor=round(m.trade_analysis.profit_factor, 2),
                win_rate=round(m.trade_analysis.win_rate, 2),
                total_trades=m.trade_analysis.total_trades,
                winning_trades=m.trade_analysis.winning_trades,
                losing_trades=m.trade_analysis.losing_trades,
            ),
        )

        _cache_result(resp)
        return resp

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Backtest failed for %s: %s", req.symbol, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {exc}",
        ) from exc


@router.get("/results/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_result(backtest_id: str):
    """Get backtest results for a completed run."""
    _ensure_hydrated()
    with _backtest_cache_lock:
        result = _backtest_cache.get(backtest_id)
    if not result:
        result = _cache_store.get(backtest_id)
        if result:
            with _backtest_cache_lock:
                _backtest_cache[backtest_id] = result
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest result '{backtest_id}' not found.",
        )
    return result


def _resolve_run_ids(run_id: str, run_ids: str | None) -> list[str]:
    if run_ids:
        ids = [rid.strip() for rid in run_ids.split(",") if rid.strip()]
        if len(ids) >= 2:
            return ids
    return [run_id]


@router.get("/comparison/{run_id}", response_model=dict)
async def compare_backtests(
    run_id: str,
    run_ids: str | None = Query(None, description="Comma-separated run IDs to compare"),
):
    """Compare multiple backtest runs side by side."""
    _ensure_hydrated()
    ids = _resolve_run_ids(run_id, run_ids)
    if len(ids) < 2 and run_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least two run_ids required for comparison.",
        )

    comparisons = []
    for rid in ids:
        with _backtest_cache_lock:
            result = _backtest_cache.get(rid)
        if not result:
            result = _cache_store.get(rid)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backtest result '{rid}' not found.",
            )
        comparisons.append(
            {
                "run_id": result.run_id,
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "metrics": result.metrics.model_dump(),
            }
        )

    if len(comparisons) == 1:
        return {"runs": comparisons, "count": 1}

    symbols = {row["symbol"] for row in comparisons}
    timeframes = {row["timeframe"] for row in comparisons}
    return {
        "runs": comparisons,
        "count": len(comparisons),
        "metadata": {
            "symbols": sorted(symbols),
            "timeframes": sorted(timeframes),
            "homogeneous": len(symbols) == 1 and len(timeframes) == 1,
        },
    }
