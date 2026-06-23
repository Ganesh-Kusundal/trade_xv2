"""OMS Backtest Adapter — drives backtest fills through the OMS."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from domain import OrderType, ProductType, Side
from brokers.common.execution.execution_mode_adapter import (
    ExecutionModeAdapter,
    ReplayOMSAdapter,
    create_execution_adapter,
)
from brokers.common.execution.simulated_fill import (
    apply_slippage,
    build_backtest_correlation_id,
    make_simulated_submit_fn,
    record_simulated_trade,
)
from brokers.common.oms.context import TradingContext
from brokers.common.oms.order_manager import OmsOrderCommand

if TYPE_CHECKING:
    pass

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
    """Routes backtest signals through the OMS via :class:`ReplayOMSAdapter`."""

    def __init__(
        self,
        trading_context: TradingContext,
        slippage_pct: float = 0.0,
        commission_flat: Decimal = Decimal("0"),
        execution_adapter: ExecutionModeAdapter | None = None,
    ) -> None:
        self._ctx = trading_context
        self._slippage_pct = slippage_pct
        self._commission_flat = Decimal(str(commission_flat))
        self._adapter = execution_adapter or create_execution_adapter("replay", trading_context)
        self._fills: list[BacktestFill] = []
        self._orders: list = []  # Track all orders placed

    @property
    def fills(self) -> list[BacktestFill]:
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
        return self._execute_side(
            symbol=symbol,
            exchange=exchange,
            side=Side.BUY,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            strategy=strategy,
            reasons=reasons,
        )

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
        return self._execute_side(
            symbol=symbol,
            exchange=exchange,
            side=Side.SELL,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            strategy=strategy,
            reasons=reasons,
        )

    def _execute_side(
        self,
        *,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        strategy: str | None,
        reasons: list[str] | None,
    ) -> str | None:
        correlation_id = build_backtest_correlation_id(symbol, side)
        command = OmsOrderCommand(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id=correlation_id,
        )
        submit_fn = make_simulated_submit_fn(
            command,
            timestamp=timestamp,
            order_id_prefix="BT",
        )
        result = self._adapter.place_order(command, submit_fn=submit_fn)
        if not result.success or result.order is None:
            logger.info(
                "backtest_order_rejected: %s %s qty=%s reason=%s",
                symbol,
                side,
                quantity,
                result.error,
            )
            return None

        fill_price = apply_slippage(price, side=side, slippage_pct=self._slippage_pct)
        trade = record_simulated_trade(
            self._ctx.order_manager,
            order_id=result.order.order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=fill_price,
            timestamp=timestamp,
        )
        if trade:
            self._fills.append(
                BacktestFill(
                    order_id=result.order.order_id,
                    trade_id=trade.trade_id,
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    quantity=quantity,
                    price=fill_price,
                    timestamp=timestamp,
                    strategy=strategy,
                    reasons=list(reasons or []),
                )
            )
        self._orders.append(result.order)
        return result.order.order_id

    def modify_order(
        self,
        order_id: str,
        *,
        price: Decimal | None = None,
        quantity: int | None = None,
        trigger_price: Decimal | None = None,
    ) -> bool:
        """Modify an open order. Returns True if modification accepted."""
        for order in self._orders:
            if order.order_id == order_id and not order.is_complete:
                logger.info("backtest_order_modified: %s price=%s qty=%s", order_id, price, quantity)
                return True
        return False

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancellation accepted."""
        for order in self._orders:
            if order.order_id == order_id and not order.is_complete:
                logger.info("backtest_order_cancelled: %s", order_id)
                return True
        return False

    def get_position(self, symbol: str, exchange: str = "NSE") -> dict | None:
        """Return current position for a symbol, or None if flat."""
        pm = self._ctx.position_manager
        positions = pm.get_all_positions() if hasattr(pm, "get_all_positions") else []
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange and pos.quantity != 0:
                return {
                    "symbol": pos.symbol,
                    "exchange": pos.exchange,
                    "quantity": pos.quantity,
                    "avg_price": float(pos.avg_price),
                    "ltp": float(pos.ltp),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                    "realized_pnl": float(pos.realized_pnl),
                }
        return None

    def get_orders(self) -> list:
        """Return all orders placed through this adapter."""
        return list(self._orders)
