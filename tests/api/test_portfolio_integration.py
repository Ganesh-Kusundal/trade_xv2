"""Integration tests for portfolio PnL and square-off endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from domain import Side, Trade
from brokers.common.oms.context import TradingContext
from brokers.common.oms.order_manager import OrderManager
from brokers.common.oms.position_manager import PositionManager
from infrastructure.event_bus.event_bus import EventBus
from api.config import APIConfig
from api.deps import get_trade_journal, reset_container
from api.main import create_app
from datalake.journal import TradeJournal


@pytest.fixture
def portfolio_app(tmp_path):
    reset_container()
    journal_path = tmp_path / "journal.sqlite"
    journal = TradeJournal(journal_path, read_only=False)
    journal.record_trade(
        trade_id="t1",
        symbol="RELIANCE",
        strategy="test",
        entry_time=datetime(2024, 6, 1, 10, 0, 0),
        entry_price=2500.0,
        quantity=10,
        side="BUY",
        exit_time=datetime(2024, 6, 1, 15, 0, 0),
        exit_price=2550.0,
    )

    event_bus = EventBus()
    trading_context = TradingContext(event_bus=event_bus)
    config = APIConfig(host="127.0.0.1", port=8000, cors_origins=[])
    app = create_app(
        config=config,
        trading_context=trading_context,
        broker_service=object(),
    )
    app.dependency_overrides[get_trade_journal] = lambda: TradeJournal(
        journal_path, read_only=True
    )
    yield app
    reset_container()


@pytest.fixture
def portfolio_client(portfolio_app):
    return TestClient(portfolio_app)


class TestPortfolioPnLIntegration:
    def test_pnl_from_journal_non_zero(self, portfolio_client: TestClient):
        response = portfolio_client.get("/api/v1/portfolio/pnl?group_by=day")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "journal"
        assert data["total_pnl"] == 500.0
        assert data["total_trades"] == 1


class TestSquareOffBrokerGuard:
    def test_square_off_503_without_submit_order(self, portfolio_client: TestClient):
        pm = portfolio_client.app.dependency_overrides  # noqa: SLF001
        from api.deps import get_position_manager

        position_manager = PositionManager()
        position_manager.apply_trade(
            Trade(
                trade_id="fill-1",
                order_id="order-1",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=5,
                price=Decimal("2500"),
            )
        )

        def _pm_override():
            return position_manager

        portfolio_client.app.dependency_overrides[get_position_manager] = _pm_override

        response = portfolio_client.post("/api/v1/portfolio/square-off")
        assert response.status_code == 503
