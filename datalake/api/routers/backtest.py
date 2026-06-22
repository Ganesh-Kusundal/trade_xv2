"""Backtest endpoints (run, results, comparison).

Wires the backtest engine into the API for on-demand backtest execution.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.api.deps import get_datalake_gateway
from datalake.api.auth import require_auth
from datalake.api.schemas import (
    BacktestRunRequest,
    BacktestResultResponse,
    BacktestMetrics,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


# Thread-safe in-memory cache for backtest results
_backtest_cache: dict[str, BacktestResultResponse] = {}
_backtest_cache_lock = threading.Lock()


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
        # Load historical data for the symbol
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

        # Build FeaturePipeline with standard indicators
        from analytics.pipeline import FeaturePipeline, RSI, ATR, SMA
        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))

        # Build StrategyPipeline (use momentum as default)
        from analytics.strategy import MomentumStrategy, BreakoutStrategy, StrategyPipeline

        strategy_map = {
            "momentum": MomentumStrategy,
            "breakout": BreakoutStrategy,
        }
        strategy_cls = strategy_map.get(req.strategy, MomentumStrategy)
        strategy = StrategyPipeline(strategies=[strategy_cls()])

        # Run backtest engine
        from analytics.backtest import BacktestEngine, BacktestConfig

        config = BacktestConfig(
            initial_capital=req.initial_capital,
            warmup_bars=20,
        )
        engine = BacktestEngine(pipeline, strategy, config)
        result = engine.run(df, symbol=req.symbol)

        # Build response
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

        # Cache result (thread-safe)
        with _backtest_cache_lock:
            _backtest_cache[run_id] = resp

        return resp

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Backtest failed for %s: %s", req.symbol, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {exc}",
        )


@router.get("/results/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_result(backtest_id: str):
    """Get backtest results for a completed run."""
    with _backtest_cache_lock:
        result = _backtest_cache.get(backtest_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest result '{backtest_id}' not found. Results are cached only in-memory.",
        )
    return result


@router.get("/comparison/{run_id}", response_model=dict)
async def compare_backtests(run_id: str):
    """Compare multiple backtest runs side by side."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Backtest comparison not available yet.",
        headers={"Retry-After": "30"},
    )
