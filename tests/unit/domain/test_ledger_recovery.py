"""Ledger-backed portfolio recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain import Side
from domain.execution_contracts import LedgerFillRecord
from domain.ledger_recovery import rebuild_projector_from_fills
from infrastructure.persistence.sqlite_execution_ledger import SqliteExecutionLedger


def _fill(
    fill_id: str,
    *,
    order_id: str = "ord-1",
    qty: int = 10,
    side: Side = Side.BUY,
    price: str = "100",
) -> LedgerFillRecord:
    return LedgerFillRecord(
        fill_id=fill_id,
        order_id=order_id,
        symbol="TEST",
        exchange="NSE",
        side=side,
        quantity=qty,
        cumulative_quantity=qty,
        order_quantity=qty,
        price=Decimal(price),
        event_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def test_rebuild_open_close_round_trip() -> None:
    projector = rebuild_projector_from_fills(
        [
            _fill("f1", side=Side.BUY, qty=10, price="100"),
            _fill("f2", order_id="ord-2", side=Side.SELL, qty=10, price="110"),
        ]
    )
    pos = projector.get_position("TEST", "NSE")
    assert pos is None or pos.quantity == 0


def test_sqlite_ledger_round_trip_rebuild(tmp_path) -> None:
    ledger = SqliteExecutionLedger(tmp_path / "ledger.sqlite")
    try:
        ledger.record_fill(_fill("f1", side=Side.BUY, qty=5, price="200"))
        ledger.record_fill(_fill("f2", order_id="ord-2", side=Side.SELL, qty=5, price="210"))
        from domain.ledger_recovery import rebuild_projector_from_ledger

        projector = rebuild_projector_from_ledger(ledger)
        pos = projector.get_position("TEST", "NSE")
        assert pos is None or pos.quantity == 0
        assert len(ledger.list_fills()) == 2
    finally:
        ledger.close()