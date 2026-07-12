"""Ledger outbox — intent before submit (TRANS-P5-030)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.oms.ledger_outbox import persist_intent_then_submit
from domain import OrderType, ProductType, Side
from domain.execution_contracts import OrderIntent


def _intent() -> OrderIntent:
    return OrderIntent(
        intent_id="intent-1",
        order_id="intent-1",
        correlation_id="corr-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        created_at=datetime.now(timezone.utc),
    )


def test_persist_intent_before_submit_order() -> None:
    ledger = MagicMock()
    calls: list[str] = []

    def submit() -> str:
        calls.append("submit")
        return "ok"

    ledger.record_intent.side_effect = lambda _i: calls.append("intent")

    result = persist_intent_then_submit(ledger, _intent(), submit)

    assert result == "ok"
    assert calls == ["intent", "submit"]
    ledger.record_intent.assert_called_once()


def test_require_ledger_when_authority_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from runtime.ledger_policy import require_execution_ledger

    monkeypatch.setenv("TRADEX_LEDGER_AUTHORITY", "1")
    with pytest.raises(RuntimeError, match="requires execution ledger"):
        require_execution_ledger(None)