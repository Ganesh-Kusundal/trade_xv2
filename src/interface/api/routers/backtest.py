"""Backtest endpoints (run, results, comparison).

Wires the backtest engine into the API for on-demand backtest execution.
"""

from __future__ import annotations

import logging
import threading
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.research.backtest_cache_store import BacktestCacheStore
from interface.api.auth import require_auth
from interface.api.deps import get_datalake_gateway
from interface.api.schemas import (
    BacktestMetrics,
    BacktestResultResponse,
    BacktestRunRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


class _BacktestCache:
    """Module-level backtest cache state."""

    _cache: dict[str, BacktestResultResponse] = {}
    _lock = threading.Lock()
    _store = BacktestCacheStore()
    _hydrated = False

    @classmethod
    def ensure_hydrated(cls) -> None:
        if cls._hydrated:
            return
        with cls._lock:
            if cls._hydrated:
                return
            cls._cache.update(cls._store.load_all())
            cls._hydrated = True

    @classmethod
    def cache_result(cls, resp: BacktestResultResponse) -> None:
        cls.ensure_hydrated()
        with cls._lock:
            cls._cache[resp.run_id] = resp
        cls._store.save(resp)

    @classmethod
    def get(cls, run_id: str) -> BacktestResultResponse | None:
        cls.ensure_hydrated()
        with cls._lock:
            return cls._cache.get(run_id)

    @classmethod
    def get_all(cls) -> dict[str, BacktestResultResponse]:
        cls.ensure_hydrated()
        with cls._lock:
            return dict(cls._cache)

    @classmethod
    def delete(cls, run_id: str) -> bool:
        cls.ensure_hydrated()
        with cls._lock:
            if run_id in cls._cache:
                del cls._cache[run_id]
                return True
            return False


def _ensure_hydrated() -> None:
    _BacktestCache.ensure_hydrated()


def _cache_result(resp: BacktestResultResponse) -> None:
    _BacktestCache.cache_result(resp)


@router.post("/run", response_model=BacktestResultResponse)
async def run_backtest(
    req: BacktestRunRequest,
    gateway=Depends(get_datalake_gateway),
):
    """Run a backtest with the specified parameters.

    Default path routes fills through the OMS (PARITY). Set ``research_only=true``
    for fast PURE_SIM research without live-execution parity guarantees.
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

        from analytics.backtest import BacktestConfig, ResearchMode
        from runtime.paper_session import build_backtest_engine

        config = BacktestConfig(
            initial_capital=req.initial_capital,
            warmup_bars=20,
        )
        engine = build_backtest_engine(
            pipeline,
            strategy,
            config,
            research_only=req.research_only,
        )
        result = engine.run(df, symbol=req.symbol)

        run_id = str(uuid.uuid4())[:12]
        m = result.metrics
        research_mode = (
            ResearchMode.PURE_SIM.value if req.research_only else ResearchMode.PARITY.value
        )

        resp = BacktestResultResponse(
            run_id=run_id,
            symbol=req.symbol,
            timeframe=req.timeframe,
            research_mode=research_mode,
            research_only=req.research_only,
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

        _BacktestCache.cache_result(resp)
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
    result = _BacktestCache.get(backtest_id)
    if not result:
        result = _BacktestCache._store.get(backtest_id)
        if result:
            _BacktestCache.cache_result(result)
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
    ids = _resolve_run_ids(run_id, run_ids)
    if len(ids) < 2 and run_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least two run_ids required for comparison.",
        )

    comparisons = []
    for rid in ids:
        result = _BacktestCache.get(rid)
        if not result:
            result = _BacktestCache._store.get(rid)
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
