"""Execution composer — order execution with routing and quota management.

Delegates to BrokerRegistry, BrokerRouter, and QuotaScheduler rather than
calling broker gateways directly. Ensures all order operations have proper
routing, quota acquisition, and audit trails.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal
from typing import Any

from domain.entities import Order, OrderResponse, Position, Trade
from domain.orders.requests import ModifyOrderRequest, OrderRequest
from domain.types import OrderStatus

logger = logging.getLogger(__name__)


class ExecutionComposer:
    """High-level order execution interface for application code.

    Usage::

        composer = ExecutionComposer(
            registry=registry,
            router=router,
            quota_scheduler=scheduler,
            risk_manager=risk_manager,  # optional kill-switch guard
        )

        # Place order with automatic routing and quota
        response = await composer.place_order(request)

        # Query positions
        positions = await composer.get_positions()
    """

    def __init__(
        self,
        registry: Any,  # BrokerRegistry — injected at composition root
        router: Any,  # BrokerRouter — injected at composition root
        quota_scheduler: Any,  # QuotaScheduler — injected at composition root
        risk_manager: Any,  # Mandatory kill-switch + risk guard (fail-closed)
        order_manager: Any | None = None,  # Optional OMS spine for place/cancel/modify
    ) -> None:
        if risk_manager is None:
            raise ValueError(
                "ExecutionComposer requires risk_manager (fail-closed). "
                "Wire RiskManager from the composition root."
            )
        if order_manager is None:
            raise ValueError(
                "ExecutionComposer requires order_manager (OMS spine). "
                "Wire OrderManager from TradingContext / composition root."
            )
        self._registry = registry
        self._router = router
        self._quota_scheduler = quota_scheduler
        self._risk_manager = risk_manager
        self._order_manager = order_manager

    def _check_kill_switch(self, operation: str) -> None:
        """Raise OrderBlockedError if kill switch is active."""
        if self._risk_manager.is_kill_switch_active():
            from application.oms.errors import OrderBlockedError

            raise OrderBlockedError(
                f"Order blocked: kill switch active ({operation})",
                operation=operation,
                reason="Kill switch active",
            )

    async def place_order(
        self,
        request: OrderRequest,
        broker_id: str | None = None,
    ) -> OrderResponse:
        """Place an order with automatic routing and quota acquisition.

        Parameters
        ----------
        request
            Order request with all required fields.
        broker_id
            Optional explicit broker selection. If None, uses router policy.

        Returns
        -------
        OrderResponse
            Normalized order response with broker-assigned order ID.

        Raises
        ------
        OrderBlockedError
            If kill switch is active.
        RoutingError
            If no eligible broker can be selected.
        QuotaExhaustedError
            If quota is exhausted and wait deadline exceeded.
        BrokerUnavailableError
            If selected broker is unavailable.
        """
        # 0. Risk check (kill-switch guard)
        self._check_kill_switch("place_order")

        # 1. Route to broker
        target_broker = broker_id or self._route_order()

        # 2. Acquire quota
        quota = await self._acquire_quota(target_broker, "orders", "EXECUTION_CRITICAL")

        gateway = self._registry.get_gateway(target_broker)
        logger.info(
            "execution.place_order",
            extra={
                "broker_id": target_broker,
                "symbol": request.symbol,
                "side": getattr(request, "transaction_type", getattr(request, "side", None)),
                "quantity": request.quantity,
            },
        )

        try:
            response = await self._place_via_oms(request, gateway, quota, target_broker)
            logger.info(
                "execution.place_order.complete",
                extra={
                    "broker_id": target_broker,
                    "order_id": response.order_id,
                    "status": response.status,
                },
            )
            return response
        except Exception:
            logger.exception(
                "execution.place_order.failed",
                extra={"broker_id": target_broker, "symbol": request.symbol},
            )
            raise

    async def cancel_order(
        self,
        order_id: str,
        broker_id: str | None = None,
    ) -> OrderResponse:
        """Cancel an order with quota acquisition.

        Parameters
        ----------
        order_id
            Broker-assigned order ID to cancel.
        broker_id
            Optional explicit broker selection. If None, uses router policy.

        Returns
        -------
        OrderResponse
            Cancellation result.
        """
        # Risk check (kill-switch guard)
        self._check_kill_switch("cancel_order")

        target_broker = broker_id or self._route_order()
        quota = await self._acquire_quota(target_broker, "orders", "EXECUTION_CRITICAL")

        gateway = self._registry.get_gateway(target_broker)
        logger.info(
            "execution.cancel_order", extra={"broker_id": target_broker, "order_id": order_id}
        )

        try:
            response = await self._cancel_via_oms(order_id, gateway, quota, target_broker)
            logger.info(
                "execution.cancel_order.complete",
                extra={"broker_id": target_broker, "order_id": order_id},
            )
            return response
        except Exception:
            logger.exception(
                "execution.cancel_order.failed",
                extra={"broker_id": target_broker, "order_id": order_id},
            )
            raise

    async def modify_order(
        self,
        request: ModifyOrderRequest,
        broker_id: str | None = None,
    ) -> OrderResponse:
        """Modify an order with quota acquisition.

        Parameters
        ----------
        request
            Modify order request with order ID and changes.
        broker_id
            Optional explicit broker selection. If None, uses router policy.

        Returns
        -------
        OrderResponse
            Modification result.
        """
        # Risk check (kill-switch guard)
        self._check_kill_switch("modify_order")

        target_broker = broker_id or self._route_order()
        quota = await self._acquire_quota(target_broker, "orders", "EXECUTION_CRITICAL")

        gateway = self._registry.get_gateway(target_broker)
        logger.info(
            "execution.modify_order",
            extra={"broker_id": target_broker, "order_id": request.order_id},
        )

        try:
            response = await self._modify_via_oms(request, gateway, quota, target_broker)
            logger.info(
                "execution.modify_order.complete",
                extra={"broker_id": target_broker, "order_id": request.order_id},
            )
            return response
        except Exception:
            logger.exception(
                "execution.modify_order.failed",
                extra={"broker_id": target_broker, "order_id": request.order_id},
            )
            raise

    async def get_positions(self, broker_id: str | None = None) -> list[Position]:
        """Get current positions.

        Parameters
        ----------
        broker_id
            Optional explicit broker selection. If None, uses router policy.

        Returns
        -------
        list[Position]
            Normalized position snapshots.
        """
        target_broker = broker_id or self._route_portfolio()
        quota = await self._acquire_quota(target_broker, "quotes", "PORTFOLIO_READ")

        gateway = self._registry.get_gateway(target_broker)
        return await gateway.get_positions(quota=quota)

    async def get_orders(self, broker_id: str | None = None) -> list[Order]:
        """Get current order book.

        Parameters
        ----------
        broker_id
            Optional explicit broker selection. If None, uses router policy.

        Returns
        -------
        list[Order]
            Normalized order book.
        """
        target_broker = broker_id or self._route_portfolio()
        quota = await self._acquire_quota(target_broker, "quotes", "PORTFOLIO_READ")

        gateway = self._registry.get_gateway(target_broker)
        return await gateway.get_orders(quota=quota)

    async def get_trades(self, broker_id: str | None = None) -> list[Trade]:
        """Get trade book.

        Parameters
        ----------
        broker_id
            Optional explicit broker selection. If None, uses router policy.

        Returns
        -------
        list[Trade]
            Normalized trade book.
        """
        target_broker = broker_id or self._route_portfolio()
        quota = await self._acquire_quota(target_broker, "quotes", "PORTFOLIO_READ")

        gateway = self._registry.get_gateway(target_broker)
        return await gateway.get_trades(quota=quota)

    async def _place_via_oms(
        self,
        request: OrderRequest,
        gateway: Any,
        quota: Any,
        broker_id: str,
    ) -> OrderResponse:
        """Route placement through OrderManager (idempotency + risk + audit)."""
        from application.oms.order_manager import OmsOrderCommand, OrderResult

        cmd = self._to_oms_command(request)

        def submit_fn(oms_cmd: OmsOrderCommand) -> Order:
            resp = asyncio.run(gateway.place_order(request, quota=quota))
            return self._broker_order_from_response(resp, oms_cmd)

        result: OrderResult = await asyncio.to_thread(
            self._order_manager.place_order, cmd, submit_fn
        )
        return self._order_result_to_response(result, broker_id)

    async def _cancel_via_oms(
        self,
        order_id: str,
        gateway: Any,
        quota: Any,
        broker_id: str,
    ) -> OrderResponse:
        from application.oms.order_manager import OrderResult

        def cancel_fn(oid: str) -> bool:
            resp = asyncio.run(gateway.cancel_order(oid, quota=quota))
            return bool(getattr(resp, "success", True))

        result: OrderResult = await asyncio.to_thread(
            self._order_manager.cancel_order, order_id, cancel_fn
        )
        return self._order_result_to_response(result, broker_id)

    async def _modify_via_oms(
        self,
        request: ModifyOrderRequest,
        gateway: Any,
        quota: Any,
        broker_id: str,
    ) -> OrderResponse:
        from application.oms.order_manager import OrderResult

        def modify_fn(req: ModifyOrderRequest) -> OrderResponse:
            return asyncio.run(gateway.modify_order(req, quota=quota))

        result: OrderResult = await asyncio.to_thread(
            self._order_manager.modify_order, request, modify_fn
        )
        return self._order_result_to_response(result, broker_id)

    @staticmethod
    def _to_oms_command(request: OrderRequest) -> Any:
        from application.oms.order_manager import OmsOrderCommand

        side = getattr(request, "transaction_type", None) or getattr(request, "side", None)
        raw_price = getattr(request, "price", None)
        try:
            price = Decimal(str(raw_price)) if raw_price is not None else Decimal("0")
        except Exception:
            price = Decimal("0")
        return OmsOrderCommand(
            symbol=request.symbol,
            exchange=getattr(request, "exchange", "NSE"),
            side=side,
            quantity=request.quantity,
            price=price,
            order_type=request.order_type,
            product_type=request.product_type,
            correlation_id=request.correlation_id or str(uuid.uuid4()),
        )

    @staticmethod
    def _broker_order_from_response(response: Any, cmd: Any) -> Order:
        status = getattr(response, "status", OrderStatus.OPEN)
        if isinstance(status, str):
            try:
                status = OrderStatus(status)
            except ValueError:
                status = OrderStatus.OPEN
        return Order(
            order_id=getattr(response, "order_id", "") or getattr(response, "broker_order_id", ""),
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            side=cmd.side,
            order_type=cmd.order_type,
            quantity=cmd.quantity,
            price=cmd.price,
            product_type=cmd.product_type,
            status=status,
            correlation_id=cmd.correlation_id,
        )

    @staticmethod
    def _order_result_to_response(result: Any, broker_id: str) -> OrderResponse:
        if result.success and result.order is not None:
            order = result.order
            return OrderResponse.ok(
                order_id=order.order_id,
                status=order.status,
                message="OK",
            )
        return OrderResponse.fail(
            message=result.error or "Order failed",
            error_code="oms_rejected",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _route_order(self) -> str:
        """Route order operation to broker via policy."""
        from tradex.runtime.models import OperationKind, RoutingRequest

        request = RoutingRequest(
            operation=OperationKind.PLACE_ORDER,
            trace_id="",  # Will be set by router
        )
        decision = self._router.route(request)
        return decision.primary_broker

    def _route_portfolio(self) -> str:
        """Route portfolio read operation to broker via policy."""
        from tradex.runtime.models import OperationKind, RoutingRequest

        request = RoutingRequest(
            operation=OperationKind.GET_POSITIONS,
            trace_id="",
        )
        decision = self._router.route(request)
        return decision.primary_broker

    async def _acquire_quota(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str,
    ) -> Any:
        """Acquire quota token for the operation."""
        return await self._quota_scheduler.acquire_async(broker_id, endpoint_class, priority_class)
