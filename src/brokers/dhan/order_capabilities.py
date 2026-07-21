"""Dhan order capabilities — super orders, forever orders, conditional triggers.

Extracted from ``broker_extensions.py`` to keep the broker-specific surface focused.
This module must NOT import from ``broker_extensions`` to avoid circular deps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.entities import OrderResponse

if TYPE_CHECKING:
    from brokers.dhan.streaming.connection import DhanConnection


class DhanOrderCapabilities:
    """Super orders (bracket), forever orders (GTT), and conditional triggers."""

    def __init__(self, conn: DhanConnection) -> None:
        self._conn = conn

    # ── Super Orders (Bracket Orders) ─────────────────────────────────

    def place_super_order(self, **kwargs: Any) -> Any:
        """Place a super order (bracket order with target, SL, trail)."""
        return self._conn.super_orders.place_super_order(**kwargs)

    def modify_super_order(self, order_id: str, **kwargs: Any) -> Any:
        """Modify a super order."""
        return self._conn.super_orders.modify_super_order(order_id, **kwargs)

    def cancel_super_order_leg(self, order_id: str, leg_name: str) -> OrderResponse:
        """Cancel a specific leg of a super order."""
        return self._conn.super_orders.cancel_super_order_leg(order_id, leg_name)

    def get_super_orders(self) -> list[Any]:
        """Get all super orders."""
        return self._conn.super_orders.get_super_orders()

    # ── Forever Orders (GTT) ──────────────────────────────────────────

    def place_forever_order(self, request: Any) -> Any:
        """Place a forever (GTT) order."""
        return self._conn.forever_orders.place_forever_order(request)

    def modify_forever_order(self, order_id: str, request: Any) -> Any:
        """Modify a forever order."""
        return self._conn.forever_orders.modify_forever_order(order_id, request)

    def cancel_forever_order(self, order_id: str) -> OrderResponse:
        """Cancel a forever order."""
        return self._conn.forever_orders.cancel_forever_order(order_id)

    def get_all_forever_orders(self) -> list[Any]:
        """Get all forever orders."""
        return self._conn.forever_orders.get_all_forever_orders()

    # ── Conditional Triggers ──────────────────────────────────────────

    def place_conditional_trigger(self, request: Any) -> Any:
        """Place a conditional trigger/alert."""
        return self._conn.conditional_triggers.place_trigger(request)

    def modify_conditional_trigger(self, alert_id: str, request: Any) -> Any:
        """Modify a conditional trigger."""
        return self._conn.conditional_triggers.modify_trigger(alert_id, request)

    def delete_conditional_trigger(self, alert_id: str) -> bool:
        """Delete a conditional trigger."""
        return self._conn.conditional_triggers.delete_trigger(alert_id)

    def get_conditional_trigger(self, alert_id: str) -> Any:
        """Get a conditional trigger by ID."""
        return self._conn.conditional_triggers.get_trigger(alert_id)

    def get_all_conditional_triggers(self) -> list[Any]:
        """Get all conditional triggers."""
        return self._conn.conditional_triggers.get_all_triggers()
