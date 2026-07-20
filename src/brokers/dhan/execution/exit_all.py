"""Exit All adapter — close all positions and cancel all orders."""

from __future__ import annotations

import logging
from collections.abc import Callable

from brokers.common.transport_errors import map_transport_exception
from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.domain import ExitAllResponse
from brokers.dhan.exceptions import ExitAllError

logger = logging.getLogger(__name__)


class ExitAllAdapter:
    """Adapter for Dhan Exit All API (v2.5)."""

    def __init__(self, client: DhanHttpClient):
        self._client = client

    def exit_all(self, authorize: Callable[[], None] | None = None) -> ExitAllResponse:
        """Close all positions and cancel all orders.

        Args:
            authorize: Optional live-order authority; called before the wire
                call. Raises to block.

        Returns:
            ExitAllResponse with operation results

        Raises:
            ExitAllError: If API call fails
            LiveBrokerBlockedError / RiskRejectedError: If ``authorize`` blocks.
        """
        if authorize is not None:
            authorize()
        try:
            data = self._client.post("/exitall")
        except Exception as exc:
            mapped = map_transport_exception(exc)
            raise ExitAllError(str(mapped)) from mapped

        response_data = data.get("data", data)
        response = self._parse_response(response_data)

        logger.info(
            "exit_all_executed",
            extra={
                "positions_closed": response.positions_closed,
                "orders_cancelled": response.orders_cancelled,
                "success": response.success,
            },
        )
        return response

    def _parse_response(self, data: dict) -> ExitAllResponse:
        """Parse exit all response from API."""
        return ExitAllResponse(
            positions_closed=data.get("positionsClosed", 0),
            orders_cancelled=data.get("ordersCancelled", 0),
            success=data.get("success", False),
            message=data.get("message", ""),
        )
