"""Tracked Capital Provider — wraps GatewayCapitalProvider with fallback tracking.

This module provides a capital provider that monitors fallback usage and
implements fail-open/fail-closed logic based on the RISK_FAIL_OPEN environment
variable.

When the broker gateway is unavailable or returns invalid balance:
- If RISK_FAIL_OPEN=1: allows trading with placeholder capital (logged as WARNING)
- Otherwise: blocks all trading by returning zero balance (logged as ERROR)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from application.oms.capital_provider import CapitalProvider
from domain.constants.defaults import RISK_FAIL_OPEN_THRESHOLD

if TYPE_CHECKING:
    from application.oms.capital_provider import GatewayCapitalProvider
    from cli.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


class TrackedCapitalProvider(CapitalProvider):
    """Capital provider wrapper that tracks fallback usage and enforces risk policy.

    This class wraps a GatewayCapitalProvider and adds:
    - Fallback usage tracking (counts how often fallback balance is used)
    - Fail-open/fail-closed logic based on RISK_FAIL_OPEN env var
    - Validation to block trading on zero/negative balances

    The design is fail-safe: no order can be placed against an unknown
    capital baseline unless the operator has explicitly opted into
    fail-open mode.
    """

    def __init__(self, inner: GatewayCapitalProvider, service: BrokerService):
        """Initialize the tracked provider.

        Args:
            inner: The underlying GatewayCapitalProvider to wrap
            service: BrokerService instance for tracking fallback count
        """
        self._inner = inner
        self._service = service

    def get_available_balance(self) -> Decimal:
        """Get available balance with fallback tracking and validation.

        Returns:
            Available balance as Decimal. Returns:
            - Real balance from gateway when available
            - Decimal("1000000") if RISK_FAIL_OPEN=1 and gateway failed
            - Decimal("0") if gateway failed and RISK_FAIL_OPEN is not set
            - Decimal("0") if balance is zero or negative
        """
        balance = self._inner.get_available_balance()

        # Track fallback usage
        if balance == self._inner._fallback:
            self._service._capital_fallback_count += 1
            if self._service._risk_fail_open:
                logger.warning(
                    "risk_capital_using_placeholder",
                    extra={
                        "reason": "gateway_unavailable_or_failed",
                        "placeholder": f"Decimal('{self._inner._fallback}')",
                        "fallback_count": self._service._capital_fallback_count,
                    },
                )
                return RISK_FAIL_OPEN_THRESHOLD

            logger.error(
                "risk_capital_blocking",
                extra={
                    "reason": "gateway_unavailable_or_failed",
                    "fallback_count": self._service._capital_fallback_count,
                    "override": "set RISK_FAIL_OPEN=1 to allow",
                },
            )
            return Decimal("0")

        # Check for zero/negative balance
        if balance <= 0:
            self._service._capital_fallback_count += 1
            logger.error(
                "risk_capital_blocking",
                extra={
                    "reason": f"balance_non_positive:{balance}",
                    "fallback_count": self._service._capital_fallback_count,
                },
            )
            return Decimal("0")

        return Decimal(str(balance))
