"""Margin calculator client.

Design reference: Trade_J ``DhanMarginProvider``.
"""

from __future__ import annotations

from typing import Any

from brokers.common.resilience.retry import RetryExecutor


class DhanMarginClient:
    """Margin calculator — submit a payload and receive margin requirements."""

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor

    def calculate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a margin-calculator request.

        :param payload: Broker-specific margin-calculator payload.
        :returns: Raw margin response dict from the API.
        """
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.margin_calculator_url(), payload)
        )
