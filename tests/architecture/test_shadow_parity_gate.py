"""TRANS-P5-031 — 24h shadow parity gate (ledger projection vs live book)."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.oms.ledger_shadow import compare_ledger_vs_positions
from application.oms.position_manager import PositionManager
from domain.entities import Trade
from domain.execution_contracts import LedgerFillRecord
from domain.types import Side

_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "ledger" / "shadow_parity_24h.json"
)


def _parse_fill(row: dict) -> LedgerFillRecord:
    return LedgerFillRecord(
        fill_id=row["fill_id"],
        order_id=row["order_id"],
        symbol=row["symbol"],
        exchange=row["exchange"],
        side=Side(row["side"]),
        quantity=row["quantity"],
        cumulative_quantity=row["cumulative_quantity"],
        order_quantity=row["order_quantity"],
        price=Decimal(row["price"]),
        event_time=datetime.fromisoformat(row["event_time"]),
    )


def _fill_to_trade(record: LedgerFillRecord) -> Trade:
    return Trade(
        trade_id=record.fill_id,
        order_id=record.order_id,
        symbol=record.symbol,
        exchange=record.exchange,
        side=record.side,
        quantity=record.quantity,
        price=record.price,
        trade_value=record.price * record.quantity,
        timestamp=record.event_time,
    )


def _load_fixture_fills() -> list[LedgerFillRecord]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return [_parse_fill(row) for row in data["fills"]]


@pytest.mark.architecture
def test_shadow_parity_24h_fixture_zero_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replay 24h fixture: ledger projection must match live position book."""
    monkeypatch.setenv("TRADEX_LEDGER_AUTHORITY", "1")
    fills = _load_fixture_fills()
    assert len(fills) >= 20, "fixture must represent a full session"

    pm = PositionManager()
    for record in sorted(fills, key=lambda f: (f.event_time, f.fill_id)):
        pm.apply_trade(_fill_to_trade(record))

    ledger = MagicMock()
    ledger.list_fills.return_value = fills

    report = compare_ledger_vs_positions(ledger, pm)
    assert report.enabled is True
    assert report.compared_symbols > 0
    assert not report.has_drift, report.drifts