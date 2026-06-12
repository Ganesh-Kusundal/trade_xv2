"""Conditional alert provider for Dhan.

Implements conditional alert functionality for Dhan trades.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from brokers.common.core.enums import (
    ExchangeSegment,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.websocket.market_data import DhanMarketFeedWebSocketClient


class DhanConditionalAlertProvider:
    """Conditional alert provider for Dhan.

    Manages conditional alerts for Dhan trades, including price-based,
    time-based, and indicator-based alerts.
    """

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
        websocket_client: DhanMarketFeedWebSocketClient | None = None,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor
        self._websocket_client = websocket_client

        # Alert tracking
        self._active_alerts: dict[str, dict[str, Any]] = {}
        self._alert_history: list[dict[str, Any]] = []

    def create_conditional_alert(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        transaction_type: TransactionType,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
        order_type: OrderType = OrderType.LIMIT,
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        comparison_type: str = "LTP",
        operator: str | None = None,
        time_frame: str | None = None,
        comparing_value: Decimal | None = None,
        indicator_name: str | None = None,
        comparing_indicator_name: str | None = None,
        frequency: str | None = None,
        expiry_date: str | None = None,
        user_note: str | None = None,
    ) -> dict[str, Any]:
        """Create a conditional alert."""
        alert_id = f"alert_{datetime.now().timestamp()}"

        alert = {
            "alert_id": alert_id,
            "security_id": security_id,
            "exchange_segment": exchange_segment.value,
            "transaction_type": transaction_type.value,
            "quantity": quantity,
            "price": float(price),
            "trigger_price": float(trigger_price),
            "order_type": order_type.value,
            "product_type": product_type.value,
            "validity": validity.value,
            "comparison_type": comparison_type,
            "operator": operator,
            "time_frame": time_frame,
            "comparing_value": float(comparing_value) if comparing_value else None,
            "indicator_name": indicator_name,
            "comparing_indicator_name": comparing_indicator_name,
            "frequency": frequency,
            "expiry_date": expiry_date,
            "user_note": user_note,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "triggered_at": None,
        }

        # Validate alert
        if not self._validate_alert(alert):
            return {"success": False, "message": "Invalid alert parameters"}

        # Store alert
        self._active_alerts[alert_id] = alert

        # In a real implementation, this would send the alert to Dhan API
        # For now, return success
        return {"success": True, "alert_id": alert_id, "message": "Alert created successfully"}

    def cancel_conditional_alert(self, alert_id: str) -> bool:
        """Cancel a conditional alert."""
        if alert_id in self._active_alerts:
            self._active_alerts[alert_id]["status"] = "cancelled"
            self._active_alerts[alert_id]["cancelled_at"] = datetime.now().isoformat()
            return True
        return False

    def get_active_alerts(self) -> list[dict[str, Any]]:
        """Get all active conditional alerts."""
        return list(self._active_alerts.values())

    def get_alert_history(self) -> list[dict[str, Any]]:
        """Get alert history."""
        return list(self._alert_history)

    def check_alerts(
        self, security_id: str, exchange_segment: ExchangeSegment, current_price: Decimal
    ) -> list[dict[str, Any]]:
        """Check if any alerts should be triggered."""
        triggered_alerts = []

        for _alert_id, alert in self._active_alerts.items():
            if alert["status"] != "active":
                continue

            if (
                alert["security_id"] != security_id
                or alert["exchange_segment"] != exchange_segment.value
            ):
                continue

            if self._should_trigger_alert(alert, current_price):
                alert["status"] = "triggered"
                alert["triggered_at"] = datetime.now().isoformat()
                alert["triggered_price"] = float(current_price)
                self._alert_history.append(alert.copy())
                triggered_alerts.append(alert)

        return triggered_alerts

    def _should_trigger_alert(self, alert: dict[str, Any], current_price: Decimal) -> bool:
        """Check if an alert should be triggered based on current price."""
        comparison_type = alert["comparison_type"]
        operator = alert["operator"]
        comparing_value = alert["comparing_value"]

        if not comparing_value:
            return False

        if comparison_type == "LTP":
            if (
                (operator == "GT" and current_price > Decimal(str(comparing_value)))
                or (operator == "LT" and current_price < Decimal(str(comparing_value)))
                or (operator == "EQ" and current_price == Decimal(str(comparing_value)))
            ):
                return True

        return False

    def _validate_alert(self, alert: dict[str, Any]) -> bool:
        """Validate alert parameters."""
        required_fields = [
            "security_id",
            "exchange_segment",
            "transaction_type",
            "quantity",
            "price",
            "trigger_price",
            "comparison_type",
            "operator",
            "expiry_date",
        ]

        for field in required_fields:
            if not alert.get(field):
                return False

        if alert["quantity"] <= 0:
            return False

        if alert["price"] <= 0:
            return False

        if alert["trigger_price"] <= 0:
            return False

        return not (alert["comparison_type"] == "LTP" and not alert["operator"])

    def subscribe_to_alert_updates(self, callback: callable) -> bool:
        """Subscribe to real-time alert updates."""
        if self._websocket_client:
            # In a real implementation, this would subscribe to alert WebSocket
            return True
        return False

    def get_alert_by_id(self, alert_id: str) -> dict[str, Any] | None:
        """Get alert by ID."""
        return self._active_alerts.get(alert_id)

    def update_alert(self, alert_id: str, **updates) -> bool:
        """Update alert parameters."""
        if alert_id in self._active_alerts:
            self._active_alerts[alert_id].update(updates)
            return True
        return False
