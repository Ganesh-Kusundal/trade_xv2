"""Shadow ledger vs position book parity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.oms.ledger_shadow import compare_ledger_vs_positions
from application.oms.position_manager import PositionManager
from domain.entities import Trade
from domain.execution_contracts import LedgerFillRecord
from domain.types import Side


def test_shadow_compare_disabled_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADEX_LEDGER_AUTHORITY", raising=False)
    pm = PositionManager()
    report = compare_ledger_vs_positions(MagicMock(), pm)
    assert report.enabled is False


def test_shadow_detects_quantity_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEX_LEDGER_AUTHORITY", "1")
    ledger = MagicMock()
    ledger.list_fills.return_value = [
        LedgerFillRecord(
            fill_id="f1",
            order_id="o1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            cumulative_quantity=10,
            price=Decimal("100"),
            order_quantity=10,
            event_time=datetime.now(timezone.utc),
        )
    ]
    pm = PositionManager()
    pm.apply_trade(
        Trade(
            trade_id="f1",
            order_id="o1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("100"),
            trade_value=Decimal("500"),
        )
    )
    report = compare_ledger_vs_positions(ledger, pm)
    assert report.enabled is True
    assert report.has_drift
    assert report.drifts[0].field == "quantity"
