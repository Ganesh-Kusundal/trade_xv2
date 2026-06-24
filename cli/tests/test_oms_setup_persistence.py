"""Tests for OMS setup wiring on the CLI path."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.oms import PositionManager, RiskConfig, RiskManager
from cli.services.oms_setup import register_oms_services
from infrastructure.event_bus import ProcessedTradeRepository


@pytest.fixture(autouse=True)
def _clear_trade_repo_singletons():
    ProcessedTradeRepository.clear_instances()
    yield
    ProcessedTradeRepository.clear_instances()


def test_register_oms_services_wires_persisted_trade_ledger(tmp_path, monkeypatch):
    """CLI OMS setup must pass a durable ProcessedTradeRepository."""
    monkeypatch.chdir(tmp_path)
    from unittest.mock import MagicMock

    service = MagicMock()
    service._gateway = None
    service._event_bus = None
    service._lifecycle = MagicMock()
    risk_manager = RiskManager(PositionManager(), RiskConfig())

    register_oms_services(service, risk_manager)

    ctx = service._trading_context
    assert ctx is not None
    repo = ctx.order_manager._processed_trades
    assert repo._path is not None
    assert repo._path.parent.name == "runtime"
    assert repo._path.name == "processed-trades.jsonl"
