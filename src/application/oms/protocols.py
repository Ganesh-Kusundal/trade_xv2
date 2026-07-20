"""OMS protocols with multiple production implementations only.

ponytail: Single-impl mirrors (IOrderManager, IRiskManager, …) removed in
Wave 2 — use concrete types or domain ports (OrderServicePort, RiskManagerPort).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.reconciliation import ReconciliationReport


@runtime_checkable
class IReconciliationService(Protocol):
    """Broker reconciliation adapters (Dhan, Upstox, …)."""

    def reconcile(
        self,
        local_orders: list | None = ...,
        local_positions: list | None = ...,
    ) -> ReconciliationReport:
        """Compare local OMS state with broker state."""
        ...


__all__ = ["IReconciliationService"]
