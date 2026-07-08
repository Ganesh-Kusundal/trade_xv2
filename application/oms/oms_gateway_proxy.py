"""OMS Gateway Proxy — enforces OMS-only access for order operations.

This proxy wraps the real broker gateway and intercepts all order
operations (place_order, cancel_order, modify_order). It ensures:

1. Kill switch is NOT active before allowing any order operation
2. All order operations are audited (allowed or blocked)
3. Market data, portfolio, and instrument operations pass through
   unchanged (they are read-only and don't need OMS enforcement)

Design principle:
    "The OMS is the single owner of order state. Any path that places,
    modifies, or cancels an order MUST pass through the OMS. The proxy
    enforces this at the gateway boundary so no caller — strategy, CLI,
    API, or operator — can bypass risk checks."

As Dr. Venkat says: "A system that is fast and wrong is more dangerous
than a system that is slow and right." The proxy adds microseconds of
overhead but guarantees correctness.

Usage::

    proxy = OMSGatewayProxy(
        real_gateway=dhan_gateway,
        risk_manager=risk_manager,
        audit_logger=audit_logger,
        strict_mode=True,  # Block if OMS unavailable
    )
    # Use proxy exactly like the real gateway
    proxy.place_order(...)  # Enforced through OMS checks
    proxy.quote(...)        # Passes through (market data)
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.entities import OrderResponse
from domain.exceptions import TradeXV2Error

if TYPE_CHECKING:
    from application.oms.risk_manager import RiskManager
    from domain.ports.broker_transport import BrokerTransport as MarketDataGateway

logger = logging.getLogger(__name__)


class OrderBlockedError(TradeXV2Error):
    """Raised when an order operation is blocked by OMS enforcement.

    Attributes
    ----------
    operation : str
        The operation that was blocked (place_order, cancel_order, modify_order).
    reason : str
        Human-readable explanation of why the operation was blocked.
    timestamp : float
        Unix timestamp when the block occurred.
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation or "unknown"
        self.reason = reason or message
        self.timestamp = time.time()


class OMSGatewayProxy:
    """Proxy that enforces OMS-only access for order operations.

    Market data and account info can bypass OMS.
    Order placement, modification, cancellation MUST go through OMS.

    Parameters
    ----------
    real_gateway : MarketDataGateway
        The actual broker gateway to delegate to.
    risk_manager : RiskManager
        The OMS risk manager. Used to check kill switch status.
    audit_logger : Any, optional
        Callable that accepts a dict with audit fields. If None,
        logging is used instead.
    strict_mode : bool, default True
        When True, raises OrderBlockedError if kill switch is active
        or OMS is unavailable. When False, logs a warning but allows
        the operation through (audit-only mode for migration).
    """

    # Order operations that MUST go through OMS
    _ORDER_OPERATIONS = frozenset(
        {
            "place_order",
            "cancel_order",
            "modify_order",
        }
    )

    def __init__(
        self,
        real_gateway: MarketDataGateway,
        risk_manager: RiskManager,
        audit_logger: Any | None = None,
        *,
        strict_mode: bool = True,
    ) -> None:
        self._real_gateway = real_gateway
        self._risk_manager = risk_manager
        self._audit_logger = audit_logger
        self._strict_mode = strict_mode
        self._operation_count: int = 0
        self._blocked_count: int = 0

    # -- Audit helpers --------------------------------------------------------

    def _audit(
        self,
        operation: str,
        symbol: str | None,
        outcome: str,
        reason: str | None = None,
        **extra: Any,
    ) -> None:
        """Record an audit entry for an order operation."""
        self._operation_count += 1
        entry = {
            "timestamp": time.time(),
            "operation": operation,
            "symbol": symbol,
            "outcome": outcome,
            "reason": reason,
            "strict_mode": self._strict_mode,
            "gateway": type(self._real_gateway).__name__,
            **extra,
        }
        if outcome == "BLOCKED":
            self._blocked_count += 1

        if self._audit_logger is not None:
            try:
                self._audit_logger(entry)
            except Exception:
                logger.exception("audit_logger_failed")

        logger.info(
            "oms_gateway_proxy: %s %s for %s — %s%s",
            operation,
            outcome,
            symbol or "N/A",
            f"reason={reason}" if reason else "",
            f" [{extra}]" if extra else "",
        )

    def _check_oms_available(self, operation: str, symbol: str | None) -> bool:
        """Check if OMS is available and kill switch is NOT active.

        Returns True if the operation is allowed, False if blocked.
        """
        if self._risk_manager is None:
            if self._strict_mode:
                self._audit(
                    operation,
                    symbol,
                    "BLOCKED",
                    reason="OMS risk_manager unavailable (strict mode)",
                )
                return False
            else:
                self._audit(
                    operation,
                    symbol,
                    "ALLOWED_AUDIT_ONLY",
                    reason="OMS unavailable — audit-only mode",
                )
                return True

        if self._risk_manager.is_kill_switch_active():
            self._audit(
                operation,
                symbol,
                "BLOCKED",
                reason="Kill switch active",
            )
            return False

        return True

    # -- Order operations (ENFORCED) -----------------------------------------

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        """Place an order — enforced through OMS kill switch check.

        Raises OrderBlockedError if kill switch is active or OMS is
        unavailable in strict mode.
        """
        if not self._check_oms_available("place_order", symbol):
            raise OrderBlockedError(
                f"Order blocked: kill switch active or OMS unavailable. "
                f"symbol={symbol}, side={side}, quantity={quantity}",
                operation="place_order",
                reason="Kill switch active or OMS unavailable",
            )

        self._audit("place_order", symbol, "ALLOWED", correlation_id=correlation_id)
        return self._real_gateway.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order — enforced through OMS kill switch check.

        Raises OrderBlockedError if kill switch is active or OMS is
        unavailable in strict mode.
        """
        if not self._check_oms_available("cancel_order", None):
            raise OrderBlockedError(
                f"Cancel blocked: kill switch active or OMS unavailable. order_id={order_id}",
                operation="cancel_order",
                reason="Kill switch active or OMS unavailable",
            )

        self._audit("cancel_order", None, "ALLOWED", order_id=order_id)
        return self._real_gateway.cancel_order(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an order — enforced through OMS kill switch check.

        Raises OrderBlockedError if kill switch is active or OMS is
        unavailable in strict mode.
        """
        if not self._check_oms_available("modify_order", None):
            raise OrderBlockedError(
                f"Modify blocked: kill switch active or OMS unavailable. order_id={order_id}",
                operation="modify_order",
                reason="Kill switch active or OMS unavailable",
            )

        self._audit("modify_order", None, "ALLOWED", order_id=order_id, changes=changes)
        return self._real_gateway.modify_order(order_id, **changes)

    # -- Market data operations (PASS-THROUGH) -------------------------------
    # These are read-only and do not need OMS enforcement.

    def history(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.history(*args, **kwargs)

    def quote(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.quote(*args, **kwargs)

    def ltp(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.ltp(*args, **kwargs)

    def depth(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.depth(*args, **kwargs)

    def option_chain(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.option_chain(*args, **kwargs)

    def future_chain(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.future_chain(*args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.stream(*args, **kwargs)

    def ltp_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.ltp_batch(*args, **kwargs)

    def quote_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.quote_batch(*args, **kwargs)

    def history_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.history_batch(*args, **kwargs)

    # -- Portfolio operations (PASS-THROUGH) ---------------------------------

    def positions(self) -> Any:
        return self._real_gateway.positions()

    def holdings(self) -> Any:
        return self._real_gateway.holdings()

    def funds(self) -> Any:
        return self._real_gateway.funds()

    def trades(self) -> Any:
        return self._real_gateway.trades()

    def get_orderbook(self) -> Any:
        return self._real_gateway.get_orderbook()

    def get_trade_book(self) -> Any:
        return self._real_gateway.get_trade_book()

    # -- Instrument operations (PASS-THROUGH) --------------------------------

    def search(self, *args: Any, **kwargs: Any) -> Any:
        return self._real_gateway.search(*args, **kwargs)

    def load_instruments(self, *args: Any, **kwargs: Any) -> None:
        return self._real_gateway.load_instruments(*args, **kwargs)

    # -- Lifecycle (PASS-THROUGH) --------------------------------------------

    def capabilities(self) -> Any:
        return self._real_gateway.capabilities()

    def describe(self) -> dict:
        return self._real_gateway.describe()

    def close(self) -> None:
        return self._real_gateway.close()

    # -- Observability -------------------------------------------------------

    @property
    def operation_count(self) -> int:
        """Total order operations attempted (allowed + blocked)."""
        return self._operation_count

    @property
    def blocked_count(self) -> int:
        """Total order operations blocked."""
        return self._blocked_count

    @property
    def strict_mode(self) -> bool:
        return self._strict_mode

    def snapshot(self) -> dict:
        """Return a snapshot of proxy state for observability."""
        return {
            "operation_count": self._operation_count,
            "blocked_count": self._blocked_count,
            "strict_mode": self._strict_mode,
            "kill_switch_active": (
                self._risk_manager.is_kill_switch_active() if self._risk_manager else None
            ),
            "real_gateway": type(self._real_gateway).__name__,
        }
