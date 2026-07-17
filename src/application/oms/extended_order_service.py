"""Service for extended broker order types with OMS risk integration.

Routes super orders, forever orders, GTT, cover orders, slice orders,
and exit-all through the risk pipeline before broker transport.

Broker-agnostic (DR-B1): this service never branches on broker **name** and
never probes gateway internals. Every broker-specific execution detail is
resolved through ``BrokerExtensionRegistry.require(broker_id,
OrderCapabilityPort)`` and delegated to that executor. The capability port
(:class:`domain.extensions.order_capability.OrderCapabilityPort`, whose
canonical implementation is
:class:`domain.extensions.extended_order.ExtendedOrderExecutor`) is the only
interface this service depends on. Adding a broker means implementing the port
(only for the operations it supports) and registering it in the broker's
extension bundle — no edits here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TypeVar

from domain.events.types import EventType
from domain.exceptions import TradeXV2Error
from domain.extensions.order_capability import OrderCapabilityPort
from domain.ports.execution_context import oms_managed

logger = logging.getLogger(__name__)

T = TypeVar("T")


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

    Extension Resolution:
        Broker-specific execution is resolved via
        ``registry.require(broker_id, ExtendedOrderExecutor)``. The OMS owns
        the kill-switch, risk, ``oms_managed`` and event-publishing concerns;
        the resolved executor owns only the broker wire calls.
    """

    def __init__(
        self,
        risk_manager: Any,
        event_bus: Any,
        broker_service: Any,
        extension_registry: Any | None = None,
    ) -> None:
        self._risk = risk_manager
        self._events = event_bus
        self._broker_service = broker_service
        self._extensions = extension_registry

    def _check_kill_switch(self) -> None:
        if self._risk is not None and self._risk.is_kill_switch_active():
            raise KillSwitchActiveError("Kill switch is active — order rejected")

    def _check_risk(self, payload: dict[str, Any]) -> ExtendedOrderResult | None:
        """Run the FULL pre-trade risk path on an order built from ``payload``.

        Normal (non-extended) orders go through ``RiskManager.check_order`` which
        enforces kill switch, daily-loss circuit breaker, margin, concentration,
        and notional limits. Extended orders previously only ran the kill-switch
        check (R7). This method routes them through the same gate.

        Returns an :class:`ExtendedOrderResult` describing the rejection when the
        order fails any risk limit, or ``None`` when it passes (or when no risk
        manager is wired). The kill-switch check is preserved separately by
        :meth:`_check_kill_switch` and short-circuits before this runs.
        """
        if self._risk is None:
            return None
        from decimal import Decimal

        from domain import Order, OrderStatus, OrderType, ProductType, Side, Validity

        try:
            order = Order(
                order_id="",
                symbol=payload.get("symbol", ""),
                exchange=payload.get("exchange", "NSE"),
                side=Side(payload.get("side", "BUY")),
                order_type=OrderType(payload.get("order_type", "MARKET")),
                quantity=int(payload.get("quantity", 0)),
                price=Decimal(str(payload.get("price", "0"))),
                product_type=ProductType(payload.get("product_type", "INTRADAY")),
                status=OrderStatus.OPEN,
                validity=Validity(payload.get("validity", "DAY")),
            )
        except (ValueError, TypeError) as exc:
            # D2 fix: a payload we cannot model into a domain order is a payload
            # we cannot risk-check, so we REJECT it — never silently allow it
            # through on the kill-switch-only path (the old silent-skip bug).
            return ExtendedOrderResult(
                success=False,
                error=f"Order payload could not be risk-modelled: {exc}",
                risk_rejected=True,
            )

        result = self._risk.check_order(order)
        if not result.allowed:
            return ExtendedOrderResult(
                success=False,
                error=result.reason or "Risk check rejected order",
                risk_rejected=True,
            )
        return None

    def _publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        symbol: str | None = None,
    ) -> None:
        if self._events is None:
            return
        try:
            from domain.events.types import DomainEvent

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

    def _require_extension(self, extension_type: type[T]) -> T:
        """Acquire extension via ExtensionRegistry (broker-agnostic path).

        Raises :class:`ExtendedFeatureUnavailableError` if the registry is not
        configured, or ``UnsupportedExtensionError`` if the active broker did
        not register the requested extension.
        """
        if self._extensions is None:
            raise ExtendedFeatureUnavailableError(
                "ExtensionRegistry not configured — cannot resolve extensions"
            )
        broker_id = self._broker_name()
        return self._extensions.require(broker_id, extension_type)

    def _executor(self) -> OrderCapabilityPort:
        """Resolve the active broker's extended-order executor.

        Resolved via the capability port (``OrderCapabilityPort``), so the OMS
        asks the registry *"is an extended-order executor declared for this
        broker?"* rather than branching on a broker name.
        """
        return self._require_extension(OrderCapabilityPort)

    # ── Super Order ──────────────────────────────────────────────────────

    def place_super_order(self, gw: Any, payload: dict[str, Any]) -> ExtendedOrderResult:
        try:
            self._check_kill_switch()
            risk_result = self._check_risk(payload)
            if risk_result is not None:
                return risk_result
            with oms_managed():
                resp = self._executor().place_super_order(payload)
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
            risk_result = self._check_risk(payload)
            if risk_result is not None:
                return risk_result
            executor = self._executor()
            with oms_managed():
                resp = executor.place_forever_order(payload)
            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "forever_order", "broker": executor.broker_id},
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
            risk_result = self._check_risk(payload)
            if risk_result is not None:
                return risk_result
            executor = self._executor()
            with oms_managed():
                resp = executor.place_trigger(payload)
            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "conditional_trigger", "broker": executor.broker_id},
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
        """Flatten all positions.

        Desk policy (freeze_all): kill switch blocks *all* order actions
        including ``exit_all`` / emergency flatten. Intentional so a
        compromised or buggy process cannot "emergency exit" destructively;
        operators clear the kill switch, then exit. See
        :class:`application.oms._internal.risk_manager.RiskManager` and
        Part 5 §3.1.
        """
        try:
            self._check_kill_switch()
            with oms_managed():
                resp = self._executor().exit_all()
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
            risk_result = self._check_risk(payload)
            if risk_result is not None:
                return risk_result
            with oms_managed():
                resp = self._executor().place_gtt(payload)
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
            risk_result = self._check_risk(payload)
            if risk_result is not None:
                return risk_result
            with oms_managed():
                resp = self._executor().place_cover_order(payload)
            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "cover_order", "symbol": payload.get("symbol", "")},
                symbol=payload.get("symbol"),
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
            risk_result = self._check_risk(payload)
            if risk_result is not None:
                return risk_result
            executor = self._executor()
            with oms_managed():
                resp = executor.place_slice_order(payload)
            self._publish_event(
                EventType.ORDER_PLACED,
                {"order_type": "slice_order", "broker": executor.broker_id},
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
        try:
            resp = self._executor().set_kill_switch(payload)

            # Sync OMS risk manager kill switch
            updates = payload.get("updates", [])
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


class KillSwitchActiveError(TradeXV2Error):
    """Raised when an order is rejected due to active kill switch."""


class ExtendedFeatureUnavailableError(TradeXV2Error):
    """Raised when an extended feature is not available on the current broker."""
