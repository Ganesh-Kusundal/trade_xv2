"""Integration tests for backtest endpoints wired to real BacktestEngine."""

from __future__ import annotations
from contextlib import contextmanager

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.config import APIConfig
from api.deps import reset_container


def _build_sample_ohlcv(n_bars: int = 200) -> pd.DataFrame:
    """Build deterministic OHLCV data for backtesting."""
    dates = pd.date_range("2023-01-02", periods=n_bars, freq="B")
    t = np.linspace(0, 8 * np.pi, n_bars)
    base_price = 1500.0
    trend = np.linspace(0, 200, n_bars)
    prices = base_price + trend + 50 * np.sin(t)
    return pd.DataFrame({
        "timestamp": dates,
        "open": prices - 2,
        "high": prices + 5,
        "low": prices - 5,
        "close": prices,
        "volume": 1000000 + 200000 * np.sin(t),
    })


@pytest.fixture
def isolate_backtest_state():
    """Reset backtest cache and container before each test."""
    import api.routers.backtest as bt_mod
    with bt_mod._backtest_cache_lock:
        bt_mod._backtest_cache.clear()
    reset_container()
    yield
    with bt_mod._backtest_cache_lock:
        bt_mod._backtest_cache.clear()
    reset_container()


@contextmanager
def _make_client_with_gateway(sample_df=None, gateway=None):
    """Create test client with mocked gateway."""
    if gateway is None:
        if sample_df is None:
            sample_df = _build_sample_ohlcv(200)
        gateway = MagicMock()
        gateway.history.return_value = sample_df
    app = create_app(config=APIConfig(auth_mode="none"), datalake_gateway=gateway)
    with TestClient(app) as client:
        yield client


class TestBacktestRunRealEngine:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.backtest as bt_mod
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()
        yield
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()

    def test_run_backtest_produces_real_metrics(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "run_id" in data
            assert data["symbol"] == "RELIANCE"
            assert data["timeframe"] == "1d"
            metrics = data["metrics"]
            assert "total_return_pct" in metrics
            assert "sharpe_ratio" in metrics
            assert isinstance(metrics["total_trades"], int)

    def test_run_backtest_with_breakout_strategy(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "TCS", "years": 1, "timeframe": "1d", "initial_capital": 500_000, "strategy": "breakout"},
            )
            assert response.status_code == 200
            assert response.json()["symbol"] == "TCS"

    def test_run_backtest_caches_result(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 200
            run_id = response.json()["run_id"]
            get_resp = client.get(f"/api/v1/backtest/results/{run_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["run_id"] == run_id

    def test_run_backtest_invalid_strategy(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "unknown_strategy"},
            )
            assert response.status_code == 200

    def test_run_backtest_deterministic(self):
        with _make_client_with_gateway() as tc:
            sample_df = _build_sample_ohlcv(200)
            results = []
            for _ in range(2):
                reset_container()
                import api.routers.backtest as bt_mod
                with bt_mod._backtest_cache_lock:
                    bt_mod._backtest_cache.clear()
                resp = tc.post(
                    "/api/v1/backtest/run",
                    json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
                )
                assert resp.status_code == 200
                results.append(resp.json())

            assert results[0]["metrics"]["total_trades"] == results[1]["metrics"]["total_trades"]


class TestBacktestErrorHandling:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.backtest as bt_mod
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()
        yield
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()

    def test_no_historical_data_returns_404(self):
        with _make_client_with_gateway() as client:
            gateway = MagicMock()
            gateway.history.return_value = pd.DataFrame()
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "NOSYMBOL", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 404

    def test_gateway_none_returns_503(self):
        with TestClient(app) as tc:
            app = create_app(config=APIConfig(auth_mode="none"), datalake_gateway=None)
            response = tc.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 503

    def test_gateway_exception_returns_500(self):
        with _make_client_with_gateway() as client:
            gateway = MagicMock()
            gateway.history.side_effect = RuntimeError("Data lake connection failed")
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 500

    def test_get_nonexistent_result_returns_404(self):
        with _make_client_with_gateway() as client:
            response = client.get("/api/v1/backtest/results/nonexistent_run_id")
            assert response.status_code == 404

    def test_comparison_endpoint_returns_503(self):
        with _make_client_with_gateway() as client:
            response = client.get("/api/v1/backtest/comparison/some_id")
            assert response.status_code == 503


class TestBacktestMetricsCorrectness:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.backtest as bt_mod
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()
        yield
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()

    def test_metrics_fields_are_numeric(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 200
            metrics = response.json()["metrics"]
            assert isinstance(metrics["total_return_pct"], (int, float))
            assert isinstance(metrics["annualized_return_pct"], (int, float))
            assert isinstance(metrics["sharpe_ratio"], (int, float))
            assert isinstance(metrics["sortino_ratio"], (int, float))
            assert isinstance(metrics["max_drawdown_pct"], (int, float))
            assert isinstance(metrics["profit_factor"], (int, float))
            assert isinstance(metrics["win_rate"], (int, float))
            assert isinstance(metrics["total_trades"], int)
            assert isinstance(metrics["winning_trades"], int)
            assert isinstance(metrics["losing_trades"], int)

    def test_total_trades_equals_winning_plus_losing(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 200
            metrics = response.json()["metrics"]
            assert metrics["total_trades"] == metrics["winning_trades"] + metrics["losing_trades"]

    def test_win_rate_is_percentage(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 1, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 200
            metrics = response.json()["metrics"]
            assert 0 <= metrics["win_rate"] <= 100


class TestBacktestValidation:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.backtest as bt_mod
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()
        yield
        with bt_mod._backtest_cache_lock:
            bt_mod._backtest_cache.clear()
        reset_container()

    def test_years_too_large(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 20, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 422

    def test_years_zero(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/backtest/run",
                json={"symbol": "RELIANCE", "years": 0, "timeframe": "1d", "initial_capital": 100_000, "strategy": "momentum"},
            )
            assert response.status_code == 422
