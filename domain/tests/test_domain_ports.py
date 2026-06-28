"""Tests for domain.ports and domain.repositories — coverage for Protocol classes and adapters."""

from __future__ import annotations

from datetime import date
from typing import Protocol
from unittest.mock import MagicMock

import pandas as pd

from domain.ports.broker_gateway import OrderTransportPort
from domain.ports.event_publisher import EventPublisher
from domain.ports.market_data import (
    DataFrameMarketDataAdapter,
    GatewayMarketDataAdapter,
    MarketDataPort,
)
from domain.ports.risk_manager import RiskManagerPort
from domain.ports.strategy_evaluator import StrategyEvaluator
from domain.repositories.order_repository import OrderRepository
from domain.repositories.position_repository import PositionRepository


class TestProtocolTypes:
    def test_order_transport_port_is_protocol(self):
        assert issubclass(OrderTransportPort, Protocol)

    def test_event_publisher_is_protocol(self):
        assert issubclass(EventPublisher, Protocol)

    def test_risk_manager_port_is_protocol(self):
        assert issubclass(RiskManagerPort, Protocol)

    def test_market_data_port_is_protocol(self):
        assert issubclass(MarketDataPort, Protocol)

    def test_strategy_evaluator_is_protocol(self):
        assert issubclass(StrategyEvaluator, Protocol)

    def test_order_repository_is_protocol(self):
        assert issubclass(OrderRepository, Protocol)

    def test_position_repository_is_protocol(self):
        assert issubclass(PositionRepository, Protocol)


class TestGatewayMarketDataAdapter:
    def test_history_delegates_to_gateway(self):
        gateway = MagicMock()
        expected_df = pd.DataFrame({"close": [100, 200]})
        gateway.history.return_value = expected_df

        adapter = GatewayMarketDataAdapter(gateway)
        result = adapter.history(
            "RELIANCE",
            date(2024, 1, 1),
            date(2024, 1, 31),
            interval="1d",
            exchange="NSE",
        )

        assert result is expected_df
        gateway.history.assert_called_once_with(
            "RELIANCE",
            date(2024, 1, 1),
            date(2024, 1, 31),
            interval="1d",
            exchange="NSE",
        )

    def test_history_returns_none_when_no_history_method(self):
        gateway = MagicMock(spec=[])
        adapter = GatewayMarketDataAdapter(gateway)
        result = adapter.history(
            "RELIANCE",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )
        assert result is None


class TestDataFrameMarketDataAdapter:
    def test_history_returns_matching_data(self):
        df = pd.DataFrame({
            "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            "close": [100, 200, 300],
        })
        adapter = DataFrameMarketDataAdapter({("RELIANCE", "NSE"): df})

        result = adapter.history(
            "RELIANCE",
            date(2024, 1, 1),
            date(2024, 1, 2),
            exchange="NSE",
        )

        assert result is not None
        assert len(result) == 2

    def test_history_returns_none_for_unknown_symbol(self):
        adapter = DataFrameMarketDataAdapter({})
        result = adapter.history(
            "UNKNOWN",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )
        assert result is None

    def test_history_case_insensitive(self):
        df = pd.DataFrame({"close": [100]})
        adapter = DataFrameMarketDataAdapter({("RELIANCE", "NSE"): df})

        result = adapter.history(
            "reliance",
            date(2024, 1, 1),
            date(2024, 1, 31),
            exchange="nse",
        )

        assert result is not None

    def test_history_without_date_column(self):
        df = pd.DataFrame({"close": [100, 200]})
        adapter = DataFrameMarketDataAdapter({("RELIANCE", "NSE"): df})

        result = adapter.history(
            "RELIANCE",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert result is not None
        assert len(result) == 2

    def test_history_returns_copy(self):
        df = pd.DataFrame({"close": [100]})
        adapter = DataFrameMarketDataAdapter({("RELIANCE", "NSE"): df})

        result = adapter.history(
            "RELIANCE",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        result["close"] = 999
        assert df["close"].iloc[0] == 100
