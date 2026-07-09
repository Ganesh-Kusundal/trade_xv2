"""Backtest comparison and cache persistence tests."""

from __future__ import annotations

from api.routers import backtest as backtest_router
from api.schemas import BacktestMetrics, BacktestResultResponse
from datalake.research.backtest_cache_store import BacktestCacheStore


def _sample_result(run_id: str, symbol: str = "RELIANCE") -> BacktestResultResponse:
    return BacktestResultResponse(
        run_id=run_id,
        symbol=symbol,
        timeframe="1m",
        metrics=BacktestMetrics(
            total_return_pct=10.0,
            annualized_return_pct=8.0,
            sharpe_ratio=1.2,
            sortino_ratio=1.1,
            max_drawdown_pct=5.0,
            profit_factor=1.5,
            win_rate=55.0,
            total_trades=20,
            winning_trades=11,
            losing_trades=9,
        ),
    )


class TestBacktestCacheStore:
    def test_save_and_load(self, tmp_path):
        store = BacktestCacheStore(tmp_path / "cache.sqlite")
        result = _sample_result("run-a")
        store.save(result)
        loaded = store.get("run-a")
        assert loaded is not None
        assert loaded.symbol == "RELIANCE"
        assert loaded.metrics.sharpe_ratio == 1.2


class TestBacktestComparison:
    def test_compare_multiple_runs(self, tmp_path, monkeypatch):
        store = BacktestCacheStore(tmp_path / "cache.sqlite")
        store.save(_sample_result("run-a"))
        store.save(_sample_result("run-b", symbol="TCS"))

        monkeypatch.setattr(backtest_router, "_cache_store", store)
        with backtest_router._backtest_cache_lock:
            backtest_router._backtest_cache.clear()
            backtest_router._backtest_cache.update(store.load_all())

        from fastapi.testclient import TestClient

        from api.config import APIConfig
        from api.deps import reset_container
        from api.main import create_app

        reset_container()
        app = create_app(
            config=APIConfig(host="127.0.0.1", port=8000, cors_origins=[], auth_mode="none")
        )
        client = TestClient(app)

        response = client.get(
            "/api/v1/backtest/comparison/run-a",
            params={"run_ids": "run-a,run-b"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["metadata"]["homogeneous"] is False

        reset_container()
