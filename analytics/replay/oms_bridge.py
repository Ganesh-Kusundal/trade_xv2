"""OMS Backtest Adapter — drives backtest fills through the OMS.

Phase 4: this is the missing link in the zero-parity invariant. The
:class:`ReplayEngine` previously maintained its own ``SimulatedPosition``
state independent of the OMS, which meant a strategy that worked in
backtest could fail in live (different risk gate, different idempotency
ledger, different event bus). This adapter routes every backtest fill
through :class:`OrderManager.record_trade` so backtest and live share
the same code paths.

Usage::

    from cli.services.compose import build_runtime
    from analytics.replay.engine import ReplayEngine
    from analytics.replay.oms_bridge import OmsBacktestAdapter

    runtime = build_runtime("dhan")
    adapter = OmsBacktestAdapter(
        oms_service=runtime.oms_service,
        trading_context=runtime.trading_context,
    )
    # Engine.run() returns fills via ``adapter.fills`` and the OMS
    # book matches live behaviour exactly.

The adapter is intentionally minimal. It does not replace the
ReplayEngine's bar-by-bar loop — that logic is unchanged. It only
ensures that fills are recorded in the OMS so the same risk gate,
idempotency ledger, and event bus that protect live trading also
protect backtests.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from brokers.common.core.domain import Order, OrderStatus, OrderType, ProductType, Side, Trade
from brokers.common.oms.context import TradingContext
from brokers.common.oms.order_manager import OmsOrderCommand

logger = logging.getLogger(__name__)


@dataclass
class BacktestFill:
    """A single fill recorded by :class:`OmsBacktestAdapter`."""

    order_id: str
    trade_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal
    timestamp: datetime
    strategy: str | None = None
    reasons: list[str] = field(default_factory=list)


class OmsBacktestAdapter:
    """Routes backtest signals through the OMS.

    Phase 4 invariants
    ------------------
    * Every fill is recorded via :meth:`OrderManager.record_trade`,
      which consults the same idempotency ledger and publishes the
      same ``TRADE_APPLIED`` event consumed by the position manager.
    * ``OmsService.place_order`` is called for every entry signal so
      the OMS risk gate (``RiskManager.check_order``) is consulted
      exactly as in live trading.
    * The adapter does NOT mutate the broker gateway — fills are
      simulated locally and published to the OMS event bus. This is
      intentional: the OMS must remain the single source of truth
      for order/trade state.

    Parameters
    ----------
    trading_context:
        The OMS ``TradingContext``. Required.
    slippage_pct:
        Per-side slippage in percent (e.g. 0.05 for 0.05%). Matches
        :class:`ReplayConfig.slippage_pct`.
    commission_flat:
        Flat commission per fill in INR. Matches
        :class:`ReplayConfig.commission_flat`.
    """

    def __init__(
        self,
        trading_context: TradingContext,
        slippage_pct: float = 0.0,
        commission_flat: Decimal = Decimal("0"),
    ) -> None:
        self._ctx = trading_context
        self._slippage_pct = slippage_pct
        self._commission_flat = Decimal(str(commission_flat))
        self._open_orders: dict[str, str] = {}  # correlation_id -> order_id
        self._fills: list[BacktestFill] = []

    @property
    def fills(self) -> list[BacktestFill]:
        """All fills recorded in this backtest run."""
        return list(self._fills)

    def open_long(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        *,
        strategy: str | None = None,
        reasons: list[str] | None = None,
    ) -> str | None:
        """Open a long position via the OMS.

        Returns the canonical ``order_id`` if the order was accepted,
        ``None`` if the OMS risk gate rejected it.
        """
        order = OmsOrderCommand(
            symbol=symbol,
            exchange=exchange,
            side=Side.BUY,
            quantity=quantity,
            price=price,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
        )
        # The OMS's ``submit_fn`` is the broker gateway. In backtest
        # we have no broker — simulate a synchronous fill at the
        # requested price. The OMS's risk gate, idempotency check,
        # and event publishing are all preserved.
        def _submit(req: OmsOrderCommand) -> Order:
            order_id = f"BT-{uuid.uuid4().hex[:12]}"
            return Order(
                order_id=order_id,
                symbol=req.symbol,
                exchange=req.exchange,
                side=req.side,
                order_type=req.order_type,
                quantity=req.quantity,
                filled_quantity=0,
                price=req.price,
                product_type=req.product_type,
                status=OrderStatus.OPEN,
                timestamp=timestamp,
                correlation_id=req.correlation_id,
            )

        result = self._ctx.order_manager.place_order(order, submit_fn=_submit)
        if not result.success:
            logger.info(
                "backtest_order_rejected: %s %s qty=%s reason=%s",
                symbol,
                Side.BUY,
                quantity,
                result.error,
            )
            return None

        # Record the synchronous fill via the OMS so the position
        # book and event bus are populated identically to live.
        fill_price = self._apply_slippage(price, side="BUY")
        trade = Trade(
            trade_id=f"{result.order.order_id}:{quantity}",
            order_id=result.order.order_id,
            symbol=symbol,
            exchange=exchange,
            side=Side.BUY,
            quantity=quantity,
            price=fill_price,
            timestamp=timestamp,
            product_type=ProductType.INTRADAY,
            cumulative_filled=quantity,
        )
        accepted = self._ctx.order_manager.record_trade(trade)
        if accepted:
            self._fills.append(
                BacktestFill(
                    order_id=result.order.order_id,
                    trade_id=trade.trade_id,
                    symbol=symbol,
                    exchange=exchange,
                    side=Side.BUY,
                    quantity=quantity,
                    price=fill_price,
                    timestamp=timestamp,
                    strategy=strategy,
                    reasons=list(reasons or []),
                )
            )
        return result.order.order_id

    def close_long(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        *,
        strategy: str | None = None,
        reasons: list[str] | None = None,
    ) -> str | None:
        """Close a long position via the OMS (sells qty at ``price``)."""
        order = OmsOrderCommand(
            symbol=symbol,
            exchange=exchange,
            side=Side.SELL,
            quantity=quantity,
            price=price,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
        )

        def _submit(req: OmsOrderCommand) -> Order:
            order_id = f"BT-{uuid.uuid4().hex[:12]}"
            return Order(
                order_id=order_id,
                symbol=req.symbol,
                exchange=req.exchange,
                side=req.side,
                order_type=req.order_type,
                quantity=req.quantity,
                filled_quantity=0,
                price=req.price,
                product_type=req.product_type,
                status=OrderStatus.OPEN,
                timestamp=timestamp,
                correlation_id=req.correlation_id,
            )

        result = self._ctx.order_manager.place_order(order, submit_fn=_submit)
        if not result.success:
            logger.info(
                "backtest_close_rejected: %s %s qty=%s reason=%s",
                symbol,
                Side.SELL,
                quantity,
                result.error,
            )
            return None

        fill_price = self._apply_slippage(price, side="SELL")
        trade = Trade(
            trade_id=f"{result.order.order_id}:{quantity}",
            order_id=result.order.order_id,
            symbol=symbol,
            exchange=exchange,
            side=Side.SELL,
            quantity=quantity,
            price=fill_price,
            timestamp=timestamp,
            product_type=ProductType.INTRADAY,
            cumulative_filled=quantity,
        )
        accepted = self._ctx.order_manager.record_trade(trade)
        if accepted:
            self._fills.append(
                BacktestFill(
                    order_id=result.order.order_id,
                    trade_id=trade.trade_id,
                    symbol=symbol,
                    exchange=exchange,
                    side=Side.SELL,
                    quantity=quantity,
                    price=fill_price,
                    timestamp=timestamp,
                    strategy=strategy,
                    reasons=list(reasons or []),
                )
            )
        return result.order.order_id

    def _apply_slippage(self, price: Decimal, *, side: str) -> Decimal:
        """Apply per-side slippage. Buy = price up, Sell = price down."""
        if self._slippage_pct == 0:
            return price
        factor = (1 + self._slippage_pct / 100) if side == "BUY" else (1 - self._slippage_pct / 100)
        return (price * Decimal(str(factor))).quantize(Decimal("0.0001"))