"""Bridge domain OrderIntent → OMS OrderManager → ExecutionProvider.

This is the institutional order spine for ``tradex.connect`` / Session.buy.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from application.oms._internal.risk_manager import RiskConfig
from application.oms.order_command_mapper import order_intent_to_oms_command
from application.oms.order_manager import OmsOrderCommand, OrderManager
from application.oms.order_manager import OrderResult as OmsOrderResult
from domain.entities.order import Order, OrderResponse
from domain.enums import OrderStatus
from domain.orders.intent import OrderIntent
from domain.orders.requests import OrderRequest
from domain.ports.protocols import ExecutionProvider, OrderResult


def _execution_result_to_order(cmd: OmsOrderCommand, result: OrderResult) -> Order:
    """Normalize ExecutionProvider payload into a domain Order for the OMS book."""
    payload = result.order
    if isinstance(payload, Order):
        # Prefer OMS correlation; keep broker order_id.
        return Order(
            order_id=payload.order_id,
            symbol=payload.symbol or cmd.symbol,
            exchange=payload.exchange or cmd.exchange,
            side=payload.side if payload.side is not None else cmd.side,
            order_type=payload.order_type if payload.order_type is not None else cmd.order_type,
            quantity=payload.quantity or cmd.quantity,
            filled_quantity=payload.filled_quantity,
            price=payload.price if payload.price is not None else cmd.price,
            trigger_price=payload.trigger_price,
            status=payload.status,
            timestamp=payload.timestamp,
            product_type=payload.product_type
            if payload.product_type is not None
            else cmd.product_type,
            validity=payload.validity,
            avg_price=payload.avg_price,
            reject_reason=payload.reject_reason,
            correlation_id=cmd.correlation_id,
            instrument_id=payload.instrument_id,
        )

    if isinstance(payload, OrderResponse):
        status = payload.status if payload.status is not None else OrderStatus.OPEN
        filled = cmd.quantity if status == OrderStatus.FILLED else 0
        return Order(
            order_id=payload.order_id or f"EXT-{cmd.correlation_id[:12]}",
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            side=cmd.side,
            order_type=cmd.order_type,
            quantity=cmd.quantity,
            filled_quantity=filled,
            price=cmd.price,
            status=status,
            product_type=cmd.product_type,
            correlation_id=cmd.correlation_id,
            avg_price=cmd.price if filled else Decimal("0"),
            reject_reason="" if payload.success else (payload.message or "rejected"),
        )

    # Duck-typed broker responses (order_id/status attributes)
    if payload is not None and hasattr(payload, "order_id"):
        raw_status = getattr(payload, "status", OrderStatus.OPEN)
        if isinstance(raw_status, OrderStatus):
            status = raw_status
        else:
            try:
                status = OrderStatus(str(raw_status).upper())
            except ValueError:
                # ENG-005: fail closed — never invent OPEN for unknown statuses
                status = OrderStatus.REJECTED
        filled = cmd.quantity if status == OrderStatus.FILLED else 0
        reject_reason = ""
        if status == OrderStatus.REJECTED and not isinstance(raw_status, OrderStatus):
            reject_reason = f"unmapped broker status: {raw_status!r}"
        return Order(
            order_id=str(payload.order_id or f"EXT-{cmd.correlation_id[:12]}"),
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            side=cmd.side,
            order_type=cmd.order_type,
            quantity=cmd.quantity,
            filled_quantity=filled,
            price=cmd.price,
            status=status,
            product_type=cmd.product_type,
            correlation_id=cmd.correlation_id,
            avg_price=cmd.price if filled else Decimal("0"),
            reject_reason=reject_reason,
        )

    raise RuntimeError(result.error or "ExecutionProvider returned no order payload")


def make_submit_fn(
    execution_provider: ExecutionProvider,
) -> Callable[[OmsOrderCommand], Order]:
    """Build OMS ``submit_fn`` that calls the domain ExecutionProvider port."""

    def submit_fn(cmd: OmsOrderCommand) -> Order:
        request = OrderRequest(
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            transaction_type=cmd.side,
            quantity=cmd.quantity,
            price=cmd.price,
            order_type=cmd.order_type,
            product_type=cmd.product_type,
            correlation_id=cmd.correlation_id,
        )
        result = execution_provider.place_order(request)
        if not result.success:
            raise RuntimeError(result.error or "execution rejected order")
        return _execution_result_to_order(cmd, result)

    return submit_fn


class OmsOrderService:
    """OrderServicePort implementation: Risk + OrderManager + transport submit_fn."""

    def __init__(
        self,
        order_manager: OrderManager,
        submit_fn: Callable[[OmsOrderCommand], Order],
        *,
        execution_provider: ExecutionProvider | None = None,
    ) -> None:
        self._oms = order_manager
        self._submit_fn = submit_fn
        self._execution = execution_provider

    @property
    def order_manager(self) -> OrderManager:
        return self._oms

    def place(self, intent: OrderIntent) -> OrderResult:
        cmd = order_intent_to_oms_command(intent)
        oms_result: OmsOrderResult = self._oms.place_order(cmd, submit_fn=self._submit_fn)
        if oms_result.success and oms_result.order is not None:
            return OrderResult.ok(oms_result.order)
        return OrderResult.fail(oms_result.error or "OMS rejected order")

    def cancel(self, order_id: str) -> OrderResult:
        """Cancel via OMS book; broker cancel through ExecutionProvider when wired."""

        def _cancel_fn(oid: str) -> bool:
            if self._execution is None:
                return True  # local-only book update
            result = self._execution.cancel_order(oid)
            return bool(result.success)

        oms_result: OmsOrderResult = self._oms.cancel_order(order_id, cancel_fn=_cancel_fn)
        if oms_result.success and oms_result.order is not None:
            return OrderResult.ok(oms_result.order)
        if oms_result.success:
            return OrderResult.ok(oms_result.order)  # type: ignore[arg-type]
        return OrderResult.fail(oms_result.error or "OMS cancel failed")

    def modify(self, request: Any) -> OrderResult:
        """Modify via OMS; broker modify through ExecutionProvider when wired."""
        from domain.orders.requests import ModifyOrderRequest

        req = (
            request
            if isinstance(request, ModifyOrderRequest)
            else ModifyOrderRequest(
                order_id=str(getattr(request, "order_id", "")),
                quantity=getattr(request, "quantity", None),
                price=getattr(request, "price", None),
                trigger_price=getattr(request, "trigger_price", None),
                order_type=getattr(request, "order_type", None),
                validity=getattr(request, "validity", None),
                product_type=getattr(request, "product_type", None),
            )
        )

        def _modify_fn(mod_req: Any) -> Any:
            if self._execution is None:
                return True
            result = self._execution.modify_order(mod_req)
            if not result.success:
                raise RuntimeError(result.error or "broker modify failed")
            return result.order if result.order is not None else True

        oms_result: OmsOrderResult = self._oms.modify_order(req, modify_fn=_modify_fn)
        if oms_result.success and oms_result.order is not None:
            return OrderResult.ok(oms_result.order)
        if oms_result.success:
            return OrderResult.ok(oms_result.order)  # type: ignore[arg-type]
        return OrderResult.fail(oms_result.error or "OMS modify failed")


# Synthetic (non-live) brokers that are safe to run with an in-memory OMS
# and fixed simulation capital. Everything NOT in this set is treated as a
# live broker and must supply a real composition root (fail-closed).
#
# This is deliberately an allowlist of *synthetic* brokers rather than a
# hardcoded list of live broker names (DR-B1): adding a new live broker needs
# no edit here, and an unknown/misspelled broker id is treated as live and
# refused rather than silently granted phantom capital (ENG-001).
_NON_LIVE_BROKER_IDS = frozenset({"paper", "datalake"})


def build_oms_service(
    execution_provider: ExecutionProvider,
    *,
    event_bus: Any | None = None,
    processed_trade_repository: Any | None = None,
    capital: Decimal = Decimal("1000000"),
    broker_id: str = "paper",
    allow_unsafe_standalone: bool = False,
) -> OmsOrderService:
    """OrderServicePort for ``tradex.connect(...)`` (paper and live).

    CRITICAL: prefers the process-wide OMS singleton registered by the
    composition root (CLI BrokerService / FastAPI create_app) so fills land
    in the SAME book the API/CLI later query.

    Standalone fallback (no registered context):
    - **paper / datalake**: builds an in-memory OMS with fixed capital and
      margin checks off (safe for simulation).
    - **live brokers** (dhan, upstox): **refused** unless
      ``allow_unsafe_standalone=True`` is passed explicitly. Silent phantom
      capital + margin-off was a money-safety defect (ENG-001).
    """
    from application.oms import get_oms_context, has_oms_context

    if has_oms_context():
        ctx = get_oms_context()
        if ctx is None:  # defensive
            raise RuntimeError("OMS context flag set but context is None")
        return OmsOrderService(
            ctx.order_manager,
            make_submit_fn(execution_provider),
            execution_provider=execution_provider,
        )

    bid = (broker_id or "paper").lower().strip()
    is_live = bid not in _NON_LIVE_BROKER_IDS
    if is_live and not allow_unsafe_standalone:
        raise RuntimeError(
            f"Live broker {bid!r} requires a process OMS composition root "
            f"(CLI/API TradingContext) before placing orders. "
            f"Call register_oms_context(...) from create_app/oms_setup, "
            f"or pass allow_unsafe_standalone=True only for controlled tests. "
            f"(ENG-001: refusing phantom-capital live OMS)"
        )

    # Paper / explicit unsafe standalone — fixed capital, no live margin API.
    from application.oms.factory import create_trading_context

    ctx = create_trading_context(
        event_bus=event_bus,
        processed_trade_repository=processed_trade_repository,
        risk_config=RiskConfig(enable_margin_check=False),
        capital_fn=lambda _c=capital: _c,
        replay_events=False,
    )

    if is_live and allow_unsafe_standalone:
        import logging

        logging.getLogger(__name__).warning(
            "ENG-001: building standalone live OMS for %s with fixed capital "
            "and margin checks OFF — not production-safe",
            bid,
        )
    return OmsOrderService(
        ctx.order_manager,
        make_submit_fn(execution_provider),
        execution_provider=execution_provider,
    )


# Backward-compatible alias (paper-oriented name; same function)