"""Ledger outbox write boundary — intent durable before broker I/O (TRANS-P5-030)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from domain.execution_contracts import OrderIntent
from domain.ports.execution_ledger import ExecutionLedgerPort

T = TypeVar("T")


def persist_intent_then_submit(
    ledger: ExecutionLedgerPort,
    intent: OrderIntent,
    submit_fn: Callable[[], T],
) -> T:
    """Record intent on the ledger, then invoke broker submit (record-then-submit)."""
    ledger.record_intent(intent)
    return submit_fn()