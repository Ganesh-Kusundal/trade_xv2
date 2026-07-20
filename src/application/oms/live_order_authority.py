"""Single live-order authority (drift D2 remediation).

Every order-placing surface — normal orders, super/forever/exit-all extended
orders, the FastAPI live router, and the Textual CLI — MUST call
:func:`authorize_live_order` before any broker executor touches the wire.

Before this module existed, the ``allow_live_orders`` flag was checked only
inside individual leaf adapters (``OrderPlacer``, ``UpstoxOrderGateway``), so
the extended-order executors (super/forever/exit-all) and the API
``require_live_broker`` dependency reached the broker with no such check. This
module lifts the gate to one composition-root-enforced authority so a new order
path cannot silently inherit "no guard".

Checks run fail-closed in this order:

1. **Live-actionable gate** — the composition-root-registered readiness gate
   (``brokers.services._session.check_live_actionable`` / ``_LiveGateState``).
   Injectable via ``live_actionable`` for testing; when omitted, the
   module-global gate is consulted, which blocks live brokers if unset.
2. **allow_live_orders flag** — the env/profile switch
   (``config/profiles/*.allow_live_orders_by_default``). Off => blocked for
   live brokers.
3. **Kill switch** — via the risk manager.
4. **Full pre-trade risk path** — an order whose payload cannot be modelled into
   a domain ``Order`` is a REJECTION, never a silent pass (this was the D2
   ``ExtendedOrderService._check_risk`` bug, which returned ``None`` on coercion
   failure and let the order through).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from application.oms._internal.order_mutation_guard import MutationAction, OrderMutationGuard
from domain.exceptions import LiveBrokerBlockedError, TradeXV2Error

logger = logging.getLogger(__name__)

# Brokers that require the live-order gate. Mirrors
# ``brokers.services._session.LIVE_BROKERS`` (kept local so the application layer
# does not import the brokers/infrastructure layer — see the layering contract).
_LIVE_BROKERS = frozenset({"dhan", "upstox"})


class RiskRejectedError(TradeXV2Error):
    """Raised when an order fails the pre-trade risk path.

    Includes the case where a payload cannot be coerced into a domain ``Order``
    (unbuildable payloads are rejected, not skipped).
    """


def authorize_live_order(
    *,
    broker: str,
    allow_live_orders: bool,
    risk_manager: Any | None,
    live_actionable: Callable[[], bool] | None = None,
    risk_payload: dict[str, Any] | None = None,
    mutation_action: MutationAction = "place",
) -> None:
    """Authorize a live order or raise. Returns ``None`` only when it may proceed.

    Args:
        broker: Active broker id (``"dhan"``/``"upstox"``/``"paper"``/...).
        allow_live_orders: The resolved ``allow_live_orders`` flag for the broker.
        risk_manager: Object exposing ``is_kill_switch_active()`` and
            ``check_order(order) -> result`` (``result.allowed``/``result.reason``).
            ``None`` skips risk (used where risk is enforced elsewhere).
        live_actionable: Optional readiness-gate callable returning ``True`` when
            the runtime is live-actionable. When omitted, the composition-root
            module-global gate is consulted instead.
        risk_payload: Optional order payload for the full pre-trade risk check.
        mutation_action: Kill-switch action label (``place``/``modify``/``cancel``).

    Raises:
        LiveBrokerBlockedError: The broker is live but the gate blocks it, or
            ``allow_live_orders`` is off.
        RiskRejectedError: Kill switch active, payload unbuildable, or risk
            manager rejected the order.
    """
    is_live = broker.lower() in _LIVE_BROKERS

    if is_live:
        # 1. Live-actionable readiness gate (fail-closed). The gate is injected
        # by the composition root from
        # ``brokers.services._session._LiveGateState``. If no gate was injected
        # we block, matching ``check_live_actionable``'s fail-closed default —
        # a live broker with no readiness gate cannot place orders.
        if live_actionable is None:
            raise LiveBrokerBlockedError(
                f"OMS refused: no live-actionable gate registered for broker '{broker}'. "
                "Run `tradex doctor` for the production readiness report."
            )
        if not live_actionable():
            raise LiveBrokerBlockedError(
                f"OMS refused: runtime is not live-actionable for broker '{broker}'. "
                "Run `tradex doctor` for the production readiness report."
            )

        # 2. allow_live_orders flag.
        if not allow_live_orders:
            raise LiveBrokerBlockedError(
                f"OMS refused: allow_live_orders is disabled for broker '{broker}'."
            )

    if risk_manager is None:
        from runtime.production_config import is_production_environment

        if is_production_environment():
            raise RiskRejectedError(
                "OMS refused: risk manager unavailable in production"
            )
        return

    # 3. Kill switch (OrderMutationGuard — same policy as OMS lifecycle).
    guard = OrderMutationGuard(risk_manager)
    ks = guard.check(mutation_action)
    if not ks.allowed:
        raise RiskRejectedError(ks.reason or "Kill switch active — order rejected")

    if risk_payload is None:
        return

    # 4. Full pre-trade risk path.
    from decimal import Decimal

    from domain import Order, OrderStatus, OrderType, ProductType, Side, Validity

    try:
        order = Order(
            order_id="",
            symbol=risk_payload.get("symbol", ""),
            exchange=risk_payload.get("exchange", "NSE"),
            side=Side(risk_payload.get("side", "BUY")),
            order_type=OrderType(risk_payload.get("order_type", "MARKET")),
            quantity=int(risk_payload.get("quantity", 0)),
            price=Decimal(str(risk_payload.get("price", "0"))),
            product_type=ProductType(risk_payload.get("product_type", "INTRADAY")),
            status=OrderStatus.OPEN,
            validity=Validity(risk_payload.get("validity", "DAY")),
        )
    except (ValueError, TypeError) as exc:
        # ponytail: ceiling = an order we cannot model is an order we cannot
        # risk-check, so we hard-reject instead of returning None (the old
        # _check_risk silent-skip). Upgrade path = schema-validate the payload at
        # the API/CLI boundary so this branch becomes unreachable.
        raise RiskRejectedError(f"Order payload could not be risk-modelled: {exc}") from exc

    result = risk_manager.check_order(order)
    if not result.allowed:
        raise RiskRejectedError(result.reason or "Risk check rejected order")
