"""Port for the durable execution ledger."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.execution_contracts import LedgerFillRecord, OrderIntent, SubmissionOutcome


@runtime_checkable
class ExecutionLedgerPort(Protocol):
    """Durable boundary for order intent and broker submission state."""

    def record_intent(self, intent: OrderIntent) -> None:
        """Persist an intent before broker I/O."""
        ...

    def record_outcome(self, outcome: SubmissionOutcome) -> None:
        """Persist accepted, rejected, or unknown broker outcome."""
        ...

    def outcome_for(self, intent_id: str) -> SubmissionOutcome | None:
        """Return the latest durable outcome for an intent."""
        ...

    def intent_for_correlation(self, correlation_id: str) -> OrderIntent | None:
        """Return the durable intent for a correlation id (F6 restart safety)."""
        ...

    def order_id_for_correlation(self, correlation_id: str) -> str | None:
        """Return order_id for a correlation id, or None if unknown."""
        ...

    def record_fill(self, fill: LedgerFillRecord) -> None:
        """Persist an accepted fill for recovery projection."""
        ...

    def list_fills(self) -> list[LedgerFillRecord]:
        """Return fills in chronological order."""
        ...

    def close(self) -> None:
        """Release storage resources."""
        ...
