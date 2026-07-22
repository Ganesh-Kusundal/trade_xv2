"""UnifiedStrategy — Zero-parity strategy base class.

Strategies inheriting from UnifiedStrategy run identically across Backtest, Replay,
Paper Trading, and Live Execution without code modification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from domain.candles.historical import HistoricalBar
from domain.entities import Quote, Trade
from domain.enums import OrderType, ProductType, Side, Validity


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    symbol: str
    exchange: str = "NSE"
    capital_allocation: Decimal = Decimal("100000.00")
    parameters: dict[str, Any] = None


class EngineContext(ABC):
    """Abstract Execution Engine context provided to strategies."""

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: OrderType = OrderType.MARKET,
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
    ) -> str:
        """Submit order to ExecutionEngine. Returns assigned order ID."""
        ...


class UnifiedStrategy(ABC):
    """Zero-parity strategy base class."""

    def __init__(self, config: StrategyConfig, context: EngineContext) -> None:
        self.config = config
        self.context = context
        self.is_active = True

    @abstractmethod
    async def on_bar(self, bar: HistoricalBar) -> None:
        """Invoked on every historical or real-time candle bar."""
        ...

    @abstractmethod
    async def on_quote(self, quote: Quote) -> None:
        """Invoked on every market depth or L1 quote update."""
        ...

    async def on_fill(self, fill: Trade) -> None:
        """Invoked on every order execution fill."""
        pass

    async def submit_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: OrderType = OrderType.MARKET,
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
    ) -> str:
        """Submit order through the injected EngineContext."""
        if not self.is_active:
            raise RuntimeError(f"Strategy {self.config.name} is inactive")

        return await self.context.submit_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
        )
