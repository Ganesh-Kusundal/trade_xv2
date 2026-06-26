"""Execution composer — order execution with routing and quota management.

Delegates to BrokerRegistry, BrokerRouter, and QuotaScheduler rather than
calling broker gateways directly. Ensures all order operations have proper
routing, quota acquisition, and audit trails.
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.common.broker_port import QuotaToken
from brokers.common.models import OperationKind, RoutingRequest
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter
from domain.entities import Order, OrderResponse, Position, Trade
from domain.requests import ModifyOrderRequest, OrderRequest

logger = logging.getLogger(__name__)


class ExecutionComposer:
    """High-level order execution interface for application code.

    Usage::

        composer = ExecutionComposer(
            registry=registry,
            router=router,
            quota_scheduler=scheduler,
        )

        # Place order with automatic routing and quota
        response = await composer.place_order(request)

        # Query positions
        positions = await composer.get_positions()
    """

    def __init__(
        self,
        registry: BrokerRegistry,
        router: BrokerRouter,
        quota_scheduler: object,  # QuotaScheduler (circular import)
    ) -> None:
        self._registry = registry
        self._router = router
        self._quota_scheduler = quota_scheduler

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
        RoutingError
            If no eligible broker can be selected.
        QuotaExhaustedError
            If quota is exhausted and wait deadline exceeded.
        BrokerUnavailableError
            If selected broker is unavailable.
        """
        # 1. Route to broker
        target_broker = broker_id or self._route_order()

        # 2. Acquire quota
        quota = await self._acquire_quota(target_broker, "orders", "EXECUTION_CRITICAL")

        # 3. Execute
        gateway = self._registry.get_gateway(target_broker)
        logger.info(
            "execution.place_order",
            extra={
                "broker_id": target_broker,
                "symbol": request.symbol,
                "side": request.side,
                "quantity": request.quantity,
            },
        )

        try:
            response = await gateway.place_order(request, quota=quota)
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
        target_broker = broker_id or self._route_order()
        quota = await self._acquire_quota(target_broker, "orders", "EXECUTION_CRITICAL")

        gateway = self._registry.get_gateway(target_broker)
        logger.info(
            "execution.cancel_order", extra={"broker_id": target_broker, "order_id": order_id}
        )

        try:
            response = await gateway.cancel_order(order_id, quota=quota)
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
        target_broker = broker_id or self._route_order()
        quota = await self._acquire_quota(target_broker, "orders", "EXECUTION_CRITICAL")

        gateway = self._registry.get_gateway(target_broker)
        logger.info(
            "execution.modify_order",
            extra={"broker_id": target_broker, "order_id": request.order_id},
        )

        try:
            response = await gateway.modify_order(request, quota=quota)
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _route_order(self) -> str:
        """Route order operation to broker via policy."""
        request = RoutingRequest(
            operation=OperationKind.PLACE_ORDER,
            trace_id="",  # Will be set by router
        )
        decision = self._router.route(request)
        return decision.primary_broker

    def _route_portfolio(self) -> str:
        """Route portfolio read operation to broker via policy."""
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
    ) -> QuotaToken:
        """Acquire quota token for the operation."""
        return await self._quota_scheduler.acquire_async(broker_id, endpoint_class, priority_class)
