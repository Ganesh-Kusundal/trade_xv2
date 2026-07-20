"""Audit logging for order state changes.

Extracted from OrderManager to follow SRP. This collaborator is responsible
solely for recording audit trails of order lifecycle events.

Thread Safety
-------------
This class is thread-safe. Internal audit log is protected by a dedicated
threading.Lock to avoid contention with the OrderManager's RLock.

Usage:
    audit_logger = OrderAuditLogger()
    audit_logger.log_state_change(order_id, old_status, new_status, details)
    history = audit_logger.get_history(order_id)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from domain.types import OrderStatus
from domain.ports.time_service import get_current_clock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit log entry for an order state change.

    Attributes
    ----------
    timestamp:
        UTC timestamp when the change occurred.
    order_id:
            Unique order identifier.
    old_status:
        Status before the change (None for new orders).
    new_status:
        Status after the change.
    details:
        Additional context (e.g., trade_id, reason, etc.).
    """

    timestamp: datetime
    order_id: str
    old_status: OrderStatus | None
    new_status: OrderStatus
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "order_id": self.order_id,
            "old_status": self.old_status.value if self.old_status else None,
            "new_status": self.new_status.value,
            "details": self.details,
        }


class OrderAuditLogger:
    """Records audit trails for order lifecycle events.

    Parameters
    ----------
    max_entries_per_order:
        Maximum number of audit entries to retain per order.
        Older entries are evicted when limit is reached.
        Default: 100 (sufficient for typical order lifecycles).

    Thread Safety
    -------------
    All public methods are thread-safe with internal locking.
    """

    def __init__(self, max_entries_per_order: int = 100) -> None:
        self._lock = threading.Lock()
        self._audit_log: dict[str, list[AuditEntry]] = {}
        self._max_entries = max_entries_per_order

    def log_new_order(
        self,
        order_id: str,
        initial_status: OrderStatus,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log creation of a new order.

        Parameters
        ----------
        order_id:
            Unique order identifier.
        initial_status:
            Initial status (typically OPEN).
        details:
            Additional context (symbol, side, quantity, etc.).
        """
        entry = AuditEntry(
            timestamp=get_current_clock().now(),
            order_id=order_id,
            old_status=None,
            new_status=initial_status,
            details=details or {},
        )
        self._append_entry(order_id, entry)
        logger.debug("Audit: new order %s -> %s", order_id, initial_status.value)

    def log_state_change(
        self,
        order_id: str,
        old_status: OrderStatus,
        new_status: OrderStatus,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an order state change.

        Parameters
        ----------
        order_id:
            Unique order identifier.
        old_status:
            Status before the change.
        new_status:
            Status after the change.
        details:
            Additional context (e.g., reason, trade_id, etc.).
        """
        entry = AuditEntry(
            timestamp=get_current_clock().now(),
            order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            details=details or {},
        )
        self._append_entry(order_id, entry)
        logger.debug(
            "Audit: order %s %s -> %s",
            order_id,
            old_status.value,
            new_status.value,
        )

    def log_trade_applied(
        self,
        order_id: str,
        trade_id: str,
        filled_quantity: int,
        avg_price: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a trade application to an order.

        Parameters
        ----------
        order_id:
            Unique order identifier.
        trade_id:
            Unique trade identifier.
        filled_quantity:
            Total filled quantity after this trade.
        avg_price:
            Average fill price as string.
        details:
            Additional context.
        """
        entry = AuditEntry(
            timestamp=get_current_clock().now(),
            order_id=order_id,
            old_status=None,  # Will be filled by caller if needed
            new_status=OrderStatus.PARTIALLY_FILLED,  # Placeholder
            details={
                "trade_id": trade_id,
                "filled_quantity": filled_quantity,
                "avg_price": avg_price,
                **(details or {}),
            },
        )
        self._append_entry(order_id, entry)
        logger.debug("Audit: trade %s applied to order %s", trade_id, order_id)

    def get_history(self, order_id: str) -> list[AuditEntry]:
        """Retrieve audit history for an order.

        Parameters
        ----------
        order_id:
            Unique order identifier.

        Returns
        -------
        list[AuditEntry]:
            Chronological list of audit entries. Empty if order not found.
        """
        with self._lock:
            return list(self._audit_log.get(order_id, []))

    def get_entry_count(self, order_id: str) -> int:
        """Get number of audit entries for an order.

        Parameters
        ----------
        order_id:
            Unique order identifier.

        Returns
        -------
        int:
            Number of entries. Zero if order not found.
        """
        with self._lock:
            return len(self._audit_log.get(order_id, []))

    def clear(self, order_id: str | None = None) -> None:
        """Clear audit log.

        Parameters
        ----------
        order_id:
            If provided, clear only this order's history.
            If None, clear all audit logs.
        """
        with self._lock:
            if order_id is not None:
                self._audit_log.pop(order_id, None)
            else:
                self._audit_log.clear()

    def _append_entry(self, order_id: str, entry: AuditEntry) -> None:
        """Append an audit entry with eviction policy.

        Parameters
        ----------
        order_id:
            Unique order identifier.
        entry:
            Audit entry to append.
        """
        with self._lock:
            if order_id not in self._audit_log:
                self._audit_log[order_id] = []

            self._audit_log[order_id].append(entry)

            # Evict oldest entries if over limit
            if len(self._audit_log[order_id]) > self._max_entries:
                self._audit_log[order_id] = self._audit_log[order_id][-self._max_entries :]
