"""Restart replay must not duplicate trades when ledger is persisted."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain import Order, OrderStatus, OrderType, ProductType, Side, Trade
from infrastructure.event_bus import ProcessedTradeRepository, TradeIdKey
from tests.conftest import build_test_trading_context


@pytest.fixture(autouse=True)
def _clear_trade_repo_singletons():
    ProcessedTradeRepository.clear_instances()
    yield
    ProcessedTradeRepository.clear_instances()


def test_persisted_ledger_survives_restart_and_rejects_duplicate_trade(tmp_path):
    ledger_path = tmp_path / "trades.jsonl"
    repo1 = ProcessedTradeRepository.get_instance(persistence_path=ledger_path)

    order = Order(
        order_id="O1",
        symbol="INFY",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        filled_quantity=0,
        price=Decimal("1500"),
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
    )
    trade = Trade(
        trade_id="T1",
        order_id="O1",
        symbol="INFY",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("1500"),
        timestamp=datetime.now(timezone.utc),
        product_type=ProductType.INTRADAY,
    )

    ctx1 = build_test_trading_context(
        replay_events=False,
        processed_trade_repository=repo1,
    )
    ctx1.order_manager.upsert_order(order)
    assert ctx1.order_manager.record_trade(trade) is True
    assert ctx1.position_manager.get_positions()[0].quantity == 10

    repo2 = ProcessedTradeRepository.get_instance(persistence_path=ledger_path)
    key = TradeIdKey.from_trade(trade)
    assert repo2.is_processed(key)

    ctx2 = build_test_trading_context(
        replay_events=False,
        processed_trade_repository=repo2,
    )
    ctx2.order_manager.upsert_order(order)
    assert ctx2.order_manager.record_trade(trade) is False
    assert len(ctx2.position_manager.get_positions()) == 0
