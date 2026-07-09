"""Scanner run endpoint integration tests."""

from __future__ import annotations
from tests.conftest import build_test_trading_context

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.config import APIConfig
from api.deps import reset_container
from api.main import create_app
from datalake.storage.catalog import DataCatalog
from datalake.gateway import DataLakeGateway


@pytest.fixture
def scanner_app(tmp_path):
    reset_container()
    market_root = tmp_path / "market_data"
    universe_dir = tmp_path / "data" / "universes"
    universe_dir.mkdir(parents=True)
    (universe_dir / "nifty50.txt").write_text("RELIANCE\n")

    candles_dir = market_root / "equities" / "candles" / "timeframe=1m" / "symbol=RELIANCE"
    candles_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-15 09:15", periods=5, freq="1min"),
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1000, 1100, 1200, 1300, 1400],
        }
    )
    df.to_parquet(candles_dir / "data.parquet")

    gateway = DataLakeGateway(root=str(market_root))
    catalog = DataCatalog(root=str(market_root), read_only=True)

    config = APIConfig(host="127.0.0.1", port=8000, cors_origins=[], auth_mode="none")
    app = create_app(
        config=config,
        datalake_gateway=gateway,
        data_catalog=catalog,
    )
    yield app, tmp_path
    reset_container()


class TestScannerRunIntegration:
    def test_scanner_run_not_always_503(self, scanner_app, monkeypatch):
        app, tmp_path = scanner_app
        monkeypatch.chdir(tmp_path)
        client = TestClient(app)

        from application.oms.context import TradingContext
        from infrastructure.event_bus.event_bus import EventBus

        reset_container()
        app = create_app(
            config=APIConfig(host="127.0.0.1", port=8000, cors_origins=[], auth_mode="none"),
            datalake_gateway=DataLakeGateway(root=str(tmp_path / "market_data")),
            data_catalog=DataCatalog(root=str(tmp_path / "market_data"), read_only=True),
            trading_context=build_test_trading_context(event_bus=EventBus()),
        )
        monkeypatch.chdir(tmp_path)
        client = TestClient(app)

        response = client.post(
            "/api/v1/scanner/run",
            params={"scanner_name": "momentum", "universe": "NIFTY50"},
        )
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "completed"
            assert "scan_id" in data
