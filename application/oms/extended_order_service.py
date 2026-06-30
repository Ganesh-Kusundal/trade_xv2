"""Service for extended broker order types with OMS risk integration.

Routes super orders, forever orders, GTT, cover orders, slice orders,
and exit-all through the risk pipeline before broker transport.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from brokers.common.resilience.errors import TradeXV2Error
from domain.events.types import EventType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtendedOrderResult:
    success: bool
    response: Any = None
    error: str | None = None
    risk_rejected: bool = False


class ExtendedOrderService:
    """Wraps broker-specific extended order types with risk checks and events.

    This service sits between the API layer and the broker gateway,
    ensuring that every order-modifying operation goes through:
    1. Kill switch check
    2. Risk manager validation (where applicable)
    3. Event publishing for audit trail
    """

    def __init__(
        self,
        risk_manager: Any,
        event_bus: Any,
        broker_service: Any,
    ) -> None:
        self._risk = risk_manager
        self._events = event_bus
        self._broker_service = broker_service

    def _check_kill_switch(self) -> None:
        if self._risk is not None and self._risk.is_kill_switch_active():
            raise KillSwitchActiveError("Kill switch is active — order rejected")

    def _publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        symbol: str | None = None,
    ) -> None:
        if self._events is None:
            return
        try:
            from infrastructure.event_bus.event_bus import DomainEvent

            event = DomainEvent.now(
                event_type=event_type,
                payload=payload,
                symbol=symbol,
            )
            self._events.publish(event)
        except Exception:
            logger.exception("Failed to publish event %s", event_type)

    def _broker_name(self) -> str:
        svc = self._broker_service
        if svc is None:
            return "unknown"
        return str(getattr(svc, "active_broker_name", "unknown"))

    def _get_extended(self, gw: Any) -> Any:
        ext = getattr(gw, "extended", None)
        if ext is None:
            raise ExtendedFeatureUnavailableError(
                "Extended capabilities not available on this gateway"
            )
        return ext

    def _get_broker(self, gw: Any) -> Any:
        broker = getattr(gw, "_broker", None)
        if broker is None:
            raise ExtendedFeatureUnavailableError(
                "Broker adapter unavailable"
            )
        return broker

    def _get_conn(self, gw: Any) -> Any:
        conn = getattr(gw, "_conn", None)
        if conn is None:
            raise ExtendedFeatureUnavailableError(
                "Broker connection unavailable"
            )
        return conn

    # ── Super Order ──────────────────────────────────────────────────────

    def place_super_order(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()
            self._require_broker("dhan")
            ext = self._get_extended(gw)
            resp = ext.place_super_order(**payload)
            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "super_order", "payload_keys": list(payload.keys())},
                symbol=payload.get("symbol"),
            )
            return ExtendedOrderResult(success=True, response=resp)
        except KillSwitchActiveError as exc:
            return ExtendedOrderResult(success=False, error=str(exc), risk_rejected=True)
        except Exception as exc:
            logger.exception("Super order failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── Forever Order ────────────────────────────────────────────────────

    def place_forever_order(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()
            broker_name = self._broker_name()

            if broker_name == "dhan":
                ext = self._get_extended(gw)
                resp = ext.place_forever_order(payload)
            elif broker_name == "upstox":
                broker = self._get_broker(gw)
                resp = broker.gtt.place_forever_order(payload)
            else:
                raise ExtendedFeatureUnavailableError("Forever orders not supported")

            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "forever_order", "broker": broker_name},
                symbol=payload.get("symbol"),
            )
            return ExtendedOrderResult(success=True, response=resp)
        except KillSwitchActiveError as exc:
            return ExtendedOrderResult(success=False, error=str(exc), risk_rejected=True)
        except Exception as exc:
            logger.exception("Forever order failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── Conditional Trigger ──────────────────────────────────────────────

    def place_trigger(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()
            broker_name = self._broker_name()

            if broker_name == "dhan":
                ext = self._get_extended(gw)
                resp = ext.place_conditional_trigger(payload)
            else:
                broker = self._get_broker(gw)
                if hasattr(broker, "alert"):
                    resp = broker.alert.place_alert(payload)
                else:
                    raise ExtendedFeatureUnavailableError("Triggers not supported")

            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "conditional_trigger", "broker": broker_name},
                symbol=payload.get("symbol"),
            )
            return ExtendedOrderResult(success=True, response=resp)
        except KillSwitchActiveError as exc:
            return ExtendedOrderResult(success=False, error=str(exc), risk_rejected=True)
        except Exception as exc:
            logger.exception("Trigger order failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── Exit All ─────────────────────────────────────────────────────────

    def exit_all(self, gw: Any) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()

            ext = self._get_extended(gw)
            if hasattr(ext, "exit_all"):
                resp = ext.exit_all()
            else:
                broker = self._get_broker(gw)
                resp = broker.exit_all.exit_all()

            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "exit_all", "response": str(resp)[:200]},
            )
            return ExtendedOrderResult(success=True, response=resp)
        except KillSwitchActiveError as exc:
            return ExtendedOrderResult(success=False, error=str(exc), risk_rejected=True)
        except Exception as exc:
            logger.exception("Exit all failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── GTT Order ────────────────────────────────────────────────────────

    def place_gtt(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()
            self._require_broker("upstox")

            broker = self._get_broker(gw)
            resp = broker.gtt.place_gtt_single(payload)
            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "gtt", "payload_keys": list(payload.keys())},
                symbol=payload.get("symbol"),
            )
            return ExtendedOrderResult(success=True, response=resp)
        except KillSwitchActiveError as exc:
            return ExtendedOrderResult(success=False, error=str(exc), risk_rejected=True)
        except Exception as exc:
            logger.exception("GTT order failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── Cover Order ──────────────────────────────────────────────────────

    def place_cover_order(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()
            self._require_broker("upstox")

            broker = self._get_broker(gw)
            from decimal import Decimal

            from domain import OrderRequest, OrderType, ProductType, Side, Validity

            req = OrderRequest(
                symbol=payload.get("symbol", ""),
                exchange=payload.get("exchange", "NSE"),
                side=Side(payload.get("side", "BUY")),
                quantity=int(payload.get("quantity", 0)),
                order_type=OrderType(payload.get("order_type", "MARKET")),
                product_type=ProductType(payload.get("product_type", "INTRADAY")),
                validity=Validity(payload.get("validity", "DAY")),
                price=Decimal(str(payload.get("price", "0"))),
            )
            resp = broker.cover.place_cover_order(
                req, Decimal(str(payload.get("stop_loss_price", "0")))
            )
            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "cover_order", "symbol": req.symbol},
                symbol=req.symbol,
            )
            return ExtendedOrderResult(success=True, response=resp)
        except KillSwitchActiveError as exc:
            return ExtendedOrderResult(success=False, error=str(exc), risk_rejected=True)
        except Exception as exc:
            logger.exception("Cover order failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── Slice Order ──────────────────────────────────────────────────────

    def place_slice_order(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()
            broker_name = self._broker_name()

            if broker_name == "dhan":
                conn = self._get_conn(gw)
                resp = conn.orders.place_slice_order(**payload)
            else:
                broker = self._get_broker(gw)
                from domain.requests import SliceOrderRequest

                req = SliceOrderRequest(**payload)
                resp = broker.slice.place_slice_order(req)

            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "slice_order", "broker": broker_name},
                symbol=payload.get("symbol"),
            )
            return ExtendedOrderResult(success=True, response=resp)
        except KillSwitchActiveError as exc:
            return ExtendedOrderResult(success=False, error=str(exc), risk_rejected=True)
        except Exception as exc:
            logger.exception("Slice order failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── Kill Switch ──────────────────────────────────────────────────────

    def set_kill_switch(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        self._require_broker("upstox")

        broker = self._get_broker(gw)
        try:
            updates = payload.get("updates", [])
            resp = broker.kill_switch.set_status(updates)

            # Sync OMS risk manager kill switch
            if self._risk is not None and hasattr(self._risk, "set_kill_switch"):
                enabled = any(u.get("enabled", False) for u in updates) if updates else False
                self._risk.set_kill_switch(enabled)

            self._publish_event(
                EventType.KILL_SWITCH_TOGGLED,
                {"updates": updates, "response": str(resp)[:200]},
            )
            return ExtendedOrderResult(success=True, response=resp)
        except Exception as exc:
            logger.exception("Kill switch update failed")
            return ExtendedOrderResult(success=False, error=str(exc))

    # ── Helpers ──────────────────────────────────────────────────────────

    def _require_broker(self, expected: str) -> None:
        if self._broker_name() != expected:
            raise ExtendedFeatureUnavailableError(
                f"Feature not supported on broker {self._broker_name()}"
            )


class KillSwitchActiveError(TradeXV2Error):
    """Raised when an order is rejected due to active kill switch."""


class ExtendedFeatureUnavailableError(TradeXV2Error):
    """Raised when an extended feature is not available on the current broker."""
