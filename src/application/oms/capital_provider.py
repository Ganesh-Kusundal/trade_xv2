"""CapitalProvider protocol - lazy capital retrieval for RiskManager.

Solves the initialization ordering problem: RiskManager needs capital
fn before gateway is constructed. CapitalProvider defers the call
until funds() is actually needed.

Usage:
    # In BrokerService:
    capital_provider = GatewayCapitalProvider(self._gateway)
    risk_manager = RiskManager(capital_provider=capital_provider)

    # In RiskManager:
    capital = self._capital_provider.get_available_balance()
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from decimal import Decimal

from domain.constants.defaults import RISK_FALLBACK_CAPITAL

logger = logging.getLogger(__name__)


class CapitalProvider(ABC):
    """Protocol for retrieving available trading capital."""

    @abstractmethod
    def get_available_balance(self) -> Decimal:
        """Return available balance for trading.

        Returns:
            Available balance in account currency (INR for Indian brokers)
        """
        ...


class GatewayCapitalProvider(CapitalProvider):
    """CapitalProvider that retrieves balance from a MarketDataGateway.

    By default fails closed on live paths when ``fail_closed=True`` (ENG-039).
    Paper/tests may keep fail_closed=False with an explicit fallback.
    """

    def __init__(
        self,
        gateway,  # MarketDataGateway - avoid circular import
        fallback_balance: Decimal = RISK_FALLBACK_CAPITAL,
        *,
        fail_closed: bool = True,
    ) -> None:
        """Initialize with gateway and fallback balance.

        Args:
            gateway: MarketDataGateway instance (can be None initially)
            fallback_balance: Balance used only when fail_closed is False
            fail_closed: If True (default), raise when funds unavailable
                instead of inventing phantom capital.
        """
        self._gateway = gateway
        self._fallback = fallback_balance
        self._fail_closed = fail_closed

    def get_available_balance(self) -> Decimal:
        """Get available balance from gateway.

        Deferred init (gateway still None) always uses fallback so
        composition roots can construct RiskManager before the gateway.
        Once a gateway is attached, fail_closed=True refuses soft phantom
        capital on funds() errors (ENG-039).
        """
        if self._gateway is None:
            logger.debug("Gateway not available yet; using fallback balance")
            return self._fallback

        try:
            # Prefer ExecutionProvider.get_funds(); fall back to wire .funds().
            getter = getattr(self._gateway, "get_funds", None)
            balance = getter() if callable(getter) else self._gateway.funds()
            avail = getattr(balance, "available_balance", None)
            if avail is None and isinstance(balance, dict):
                avail = balance.get("available_balance", balance.get("available_margin"))
            if avail is None:
                raise RuntimeError("funds response missing available_balance")
            return Decimal(str(avail))
        except Exception as exc:
            if self._fail_closed:
                raise RuntimeError(
                    f"GatewayCapitalProvider: funds() failed: {exc} (ENG-039)"
                ) from exc
            logger.warning("Failed to get funds from gateway: %s", exc)
            return self._fallback

    def update_gateway(self, gateway) -> None:
        """Update gateway reference (for deferred initialization).

        Args:
            gateway: New MarketDataGateway instance
        """
        self._gateway = gateway


def resolve_capital_provider(
    *,
    execution_kind=None,
    gateway=None,
    fixed_capital: Decimal | None = None,
    fail_closed: bool = True,
) -> CapitalProvider:
    """Select capital source by execution target (ADR-0017)."""
    from domain.constants.defaults import PAPER_INITIAL_CAPITAL
    from domain.ports.execution_target import ExecutionTargetKind

    kind = execution_kind or ExecutionTargetKind.PAPER
    if isinstance(kind, str):
        kind = ExecutionTargetKind(kind.lower())

    if kind is ExecutionTargetKind.LIVE:
        return GatewayCapitalProvider(gateway, fail_closed=fail_closed)

    cap = fixed_capital if fixed_capital is not None else PAPER_INITIAL_CAPITAL
    return FixedCapitalProvider(Decimal(str(cap)))


class FixedCapitalProvider(CapitalProvider):
    """CapitalProvider with fixed capital (for backtesting/paper trading)."""

    def __init__(self, capital: Decimal) -> None:
        """Initialize with fixed capital amount.

        Args:
            capital: Fixed capital amount
        """
        self._capital = capital

    def get_available_balance(self) -> Decimal:
        """Return fixed capital."""
        return self._capital
