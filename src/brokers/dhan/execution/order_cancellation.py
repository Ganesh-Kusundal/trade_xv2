"""Order cancellation and modification for the Dhan broker adapter.

Extracted from :class:`brokers.dhan.execution.orders.OrdersAdapter` god class.
Owns cancel, modify, kill-switch, and cancel-all operations.
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.exceptions import OrderError
from domain import OrderResponse, OrderStatus
from infrastructure.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)


class OrderCanceller:
    """Handles order modification, cancellation, and kill-switch operations.

    Each method checks the ``allow_live_orders`` guard before issuing
    HTTP calls to the Dhan API.
    """

    def __init__(
        self,
        client: DhanHttpClient,
        event_bus: EventBus | None = None,
        allow_live_orders: bool = False,
    ) -> None:
        self._client = client
        self._event_bus = event_bus
        self._allow_live_orders = allow_live_orders

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an existing order via PUT /orders/{order_id}.

        The Dhan API returns a dict with updated order fields on success,
        or an error dict with ``errorCode``/``errorMessage`` on failure.

        Returns:
            :class:`OrderResponse` with success/failure status.
        """
        # Safety guard: prevent live order modifications if disabled
        if not self._allow_live_orders:
            return OrderResponse.fail(
                "Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable."
            )

        payload = {k: v for k, v in changes.items() if v is not None}
        try:
            result = self._client.put(f"/orders/{order_id}", json=payload)
        except Exception as exc:
            return OrderResponse.fail(f"Broker API error: {exc}")

        if not isinstance(result, dict):
            return OrderResponse.fail(f"Unexpected modify response: {result}")

        error_code = result.get("errorCode")
        if error_code:
            error_msg = result.get("errorMessage", "modify_order_failed")
            return OrderResponse.fail(f"Modify order failed [{error_code}]: {error_msg}")

        logger.info("order_modified", extra={"order_id": order_id, "changes": list(changes.keys())})

        return OrderResponse(
            success=True,
            order_id=order_id,
            broker_order_id=order_id,
            message="Order modified successfully",
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order via DELETE /orders/{order_id}.

        The Dhan cancel endpoint returns a body whose ``status`` field
        is ``"success"`` on cancellation, or an error payload with a
        non-empty ``errorCode`` / ``errorMessage`` on failure. The
        previous implementation treated *any* dict response as success
        — that was a P0 bug because the broker also returns dicts on
        authentication errors and on unknown-order errors.

        Returns:
            :class:`OrderResponse` with ``success`` set from the
            broker's ``status`` field (or inferred from
            ``errorCode`` being absent).
        """
        # Safety guard: prevent live order cancellations if disabled
        if not self._allow_live_orders:
            return OrderResponse.fail(
                "Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable."
            )

        try:
            data = self._client.delete(f"/orders/{order_id}")
        except Exception as exc:  # pragma: no cover - network path
            logger.warning(
                "order_cancel_network_error",
                extra={"order_id": order_id, "error": str(exc)},
            )
            return OrderResponse.fail(
                message=f"network error: {exc}",
                error_code="BRO_ERR_CONNECTION_FAILED",
            )

        if not isinstance(data, dict):
            return OrderResponse.fail(
                message="malformed broker response (not a dict)",
                raw_payload={"raw": repr(data)},
            )

        broker_status = str(data.get("status", "")).lower()
        # Dhan uses both "success" and "ok"; both mean "cancelled".
        success = broker_status in {"success", "ok"}
        if success:
            return OrderResponse.ok(
                order_id=order_id,
                message=str(data.get("message", "Order cancelled")),
                status=OrderStatus.CANCELLED,
                raw_payload=data,
            )
        # Failure path
        return OrderResponse.fail(
            message=str(data.get("errorMessage") or data.get("message") or "Cancel failed"),
            error_code=str(data.get("errorCode", "")),
            raw_payload=data,
        )

    def cancel_all_orders(self) -> list[tuple[str, bool]]:
        # Safety guard: prevent live order cancellations if disabled
        if not self._allow_live_orders:
            return []

        data = self._client.delete("/orders")
        # Defensive: the broker may return a list/None instead of a dict on
        # certain error paths. Treat any non-dict as an empty payload rather
        # than raising AttributeError. A genuine error response (a dict with
        # error fields and no cancellable items) is surfaced via the warning
        # below instead of being silently treated as a successful empty result.
        data = data if isinstance(data, dict) else {}
        items = data.get("data", [])
        items = items if isinstance(items, list) else []
        if data and not items:
            logger.warning(
                "cancel_all_orders_unexpected_response",
                extra={"raw": repr(data)[:500]},
            )
        result = [(str(i.get("orderId", i)), True) for i in items]
        logger.info("all_orders_cancelled", extra={"count": len(result)})
        return result

    def kill_switch(self, enable: bool) -> bool:
        # Safety guard: prevent kill switch activation if live orders disabled
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        action = "ACTIVATE" if enable else "DEACTIVATE"
        data = self._client.post(f"/killswitch?killSwitchStatus={action}", json={})
        success = isinstance(data, dict) and data.get("status", "").lower() == "success"
        logger.info("kill_switch", extra={"action": action, "success": success})
        return success

    def status_kill_switch(self) -> dict:
        """Read-only kill-switch status check; no live-order guard needed."""
        data = self._client.get("/killswitch")
        return data if isinstance(data, dict) else {}
