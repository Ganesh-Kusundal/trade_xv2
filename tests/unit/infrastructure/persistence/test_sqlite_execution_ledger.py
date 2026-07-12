"""Durable execution ledger — intent before submit, outcome after broker I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain import OrderType, ProductType, Side
from domain.execution_contracts import OrderIntent, SubmissionOutcome, SubmissionState
from infrastructure.persistence.sqlite_execution_ledger import SqliteExecutionLedger


def _intent(intent_id: str = "intent-1", correlation_id: str = "corr-1") -> OrderIntent:
    return OrderIntent(
        intent_id=intent_id,
        order_id=intent_id,
        correlation_id=correlation_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        created_at=datetime.now(timezone.utc),
    )


def test_record_intent_and_outcome_round_trip(tmp_path):
    ledger = SqliteExecutionLedger(tmp_path / "ledger.sqlite")
    try:
        intent = _intent()
        ledger.record_intent(intent)
        ledger.record_outcome(SubmissionOutcome.accepted(intent.intent_id, "BRK-99"))

        outcome = ledger.outcome_for(intent.intent_id)
        assert outcome is not None
        assert outcome.state is SubmissionState.ACCEPTED
        assert outcome.broker_order_id == "BRK-99"
    finally:
        ledger.close()


def test_record_intent_is_idempotent_on_same_correlation(tmp_path):
    ledger = SqliteExecutionLedger(tmp_path / "ledger.sqlite")
    try:
        ledger.record_intent(_intent())
        ledger.record_intent(_intent())
    finally:
        ledger.close()


def test_record_intent_rejects_correlation_collision(tmp_path):
    ledger = SqliteExecutionLedger(tmp_path / "ledger.sqlite")
    try:
        ledger.record_intent(_intent(intent_id="intent-a", correlation_id="shared"))
        with pytest.raises(ValueError, match="correlation_id collision"):
            ledger.record_intent(_intent(intent_id="intent-b", correlation_id="shared"))
    finally:
        ledger.close()


def test_unknown_outcome_persists(tmp_path):
    ledger = SqliteExecutionLedger(tmp_path / "ledger.sqlite")
    try:
        intent = _intent()
        ledger.record_intent(intent)
        ledger.record_outcome(SubmissionOutcome.unknown(intent.intent_id, "timeout"))

        outcome = ledger.outcome_for(intent.intent_id)
        assert outcome is not None
        assert outcome.state is SubmissionState.UNKNOWN
        assert "timeout" in outcome.reason
    finally:
        ledger.close()