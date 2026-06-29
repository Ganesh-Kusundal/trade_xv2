"""Tests for backtest service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.backtest.backtest_service import BacktestService


def _make_gateway(data_available: bool = True):
    gw = MagicMock()
    if data_available:
        import numpy as np
        import pandas as pd
        gw.history.return_value = pd.DataFrame({
            "open": np.random.randn(100) + 100,
            "high": np.random.randn(100) + 102,
            "low": np.random.randn(100) + 98,
            "close": np.random.randn(100) + 100,
            "volume": np.random.randint(1000, 10000, 100),
        })
    else:
        gw.history.return_value = None
    return gw


class TestBacktestService:
    def test_no_data_raises(self):
        gw = _make_gateway(data_available=False)
        svc = BacktestService(gw)

        with pytest.raises(ValueError, match="No historical data"):
            svc.run_backtest("RELIANCE")

    def test_service_instantiation(self):
        gw = _make_gateway()
        svc = BacktestService(gw)
        assert svc._gateway is gw
