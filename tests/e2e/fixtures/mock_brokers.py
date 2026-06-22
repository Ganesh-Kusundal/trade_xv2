"""Mock broker gateways for E2E testing.

Provides controllable broker behavior:
- MockBrokerGateway: Normal mock that succeeds
- MockFailingBroker: Configurable failure modes
- MockLatencyBroker: Simulates network latency
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.core.domain import (
    FundLimits,
    MarketDepth,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    ProductType,
    Quote,
    Side,
)


@dataclass
class MockBrokerGateway:
    """Mock broker gateway that simulates successful operations.

    Tracks all calls for verification.
    """

    name: str = "mock"
    _orders: dict[str, Order] = field(default_factory=dict)
    _order_counter: int = 0
    _fail_on: set[str] = field(default_factory=set)
    _ltp_override: dict[str, Decimal] = field(default_factory=dict)
    _positions: list[dict] = field(default_factory=list)
    _holdings: list[dict] = field(default_factory=list)
    _funds: FundLimits = field(default_factory=FundLimits)

    def place_order(self, request: Any) -> OrderResponse:
        """Simulate order placement."""
        if "place_order" in self._fail_on:
            raise RuntimeError(f"{self.name}: place_order failed (configured)")

        self._order_counter += 1
        order_id = f"{self.name.upper()}-{self._order_counter:04d}"

        order = Order(
            order_id=order_id,
            symbol=request.symbol.upper(),
            exchange=request.exchange.upper(),
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.price,
            product_type=request.product_type,
            status=OrderStatus.OPEN,
            correlation_id=getattr(request, 'correlation_id', None),
        )

        # Auto-fill market orders immediately
        if request.order_type == OrderType.MARKET:
            order = Order(
                order_id=order_id,
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=request.price,
                filled_quantity=order.quantity,
                product_type=order.product_type,
                status=OrderStatus.FILLED,
                correlation_id=order.correlation_id,
            )

        self._orders[order_id] = order
        return OrderResponse(order_id=order_id, status=order.status, success=True)

    def modify_order(self, order_id: str, **kwargs) -> bool:
        if "modify_order" in self._fail_on:
            raise RuntimeError(f"{self.name}: modify_order failed")
        return True

    def cancel_order(self, order_id: str) -> bool:
        if "cancel_order" in self._fail_on:
            raise RuntimeError(f"{self.name}: cancel_order failed")
        if order_id in self._orders:
            self._orders[order_id] = self._orders[order_id].with_status(OrderStatus.CANCELLED)
        return True

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        if "ltp" in self._fail_on:
            raise RuntimeError(f"{self.name}: ltp failed")
        key = f"{symbol.upper()}:{exchange.upper()}"
        if key in self._ltp_override:
            return self._ltp_override[key]
        return Decimal("100.0")

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        if "ltp_batch" in self._fail_on:
            raise RuntimeError(f"{self.name}: ltp_batch failed")
        return {s: Decimal("100.0") for s in symbols}

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        if "quote" in self._fail_on:
            raise RuntimeError(f"{self.name}: quote failed")
        return Quote(symbol=symbol, exchange=exchange, ltp=Decimal("100.0"))

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return {s: Quote(symbol=s, exchange=exchange, ltp=Decimal("100.0")) for s in symbols}

    def history(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "1m",
        lookback_days: int = 90,
        **kwargs,
    ) -> pd.DataFrame:
        if "history" in self._fail_on:
            raise RuntimeError(f"{self.name}: history failed")
        return pd.DataFrame()

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        if "depth" in self._fail_on:
            raise RuntimeError(f"{self.name}: depth failed")
        return MarketDepth(symbol=symbol, exchange=exchange)

    def positions(self) -> list[dict]:
        if "positions" in self._fail_on:
            raise RuntimeError(f"{self.name}: positions failed")
        return list(self._positions)

    def holdings(self) -> list[dict]:
        return list(self._holdings)

    def funds(self) -> FundLimits:
        return self._funds

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_all_orders(self) -> list[Order]:
        return list(self._orders.values())

    def set_ltp(self, symbol: str, exchange: str, price: Decimal) -> None:
        """Override LTP for a symbol."""
        key = f"{symbol.upper()}:{exchange.upper()}"
        self._ltp_override[key] = price

    def reset(self) -> None:
        """Clear all state."""
        self._orders.clear()
        self._order_counter = 0
        self._ltp_override.clear()


@dataclass
class MockFailingBroker:
    """Mock broker that fails on specific operations.

    Useful for testing failover and error handling.
    """

    name: str = "failing"
    fail_operations: set[str] = field(default_factory=lambda: {"place_order", "ltp"})
    fail_count: int = 0
    max_fails: int = -1  # -1 = fail forever

    def place_order(self, request: Any) -> OrderResponse:
        self._maybe_fail("place_order")
        # If we get here, succeed
        return OrderResponse(order_id="OK-001", status=OrderStatus.FILLED, success=True)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        self._maybe_fail("ltp")
        return Decimal("100.0")

    def history(self, symbol: str, **kwargs) -> pd.DataFrame:
        self._maybe_fail("history")
        return pd.DataFrame()

    def positions(self) -> list[dict]:
        self._maybe_fail("positions")
        return []

    def funds(self) -> FundLimits:
        self._maybe_fail("funds")
        return FundLimits()

    def _maybe_fail(self, operation: str) -> None:
        if operation in self.fail_operations:
            if self.max_fails < 0 or self.fail_count < self.max_fails:
                self.fail_count += 1
                raise RuntimeError(f"{self.name}: {operation} failed (#{self.fail_count})")

    def reset(self) -> None:
        self.fail_count = 0


@dataclass
class MockLatencyBroker:
    """Mock broker that simulates network latency.

    Useful for testing timeout and async behavior.
    """

    name: str = "latency"
    latency_seconds: float = 0.01  # 10ms default
    _delegate: MockBrokerGateway = field(default_factory=MockBrokerGateway)

    def place_order(self, request: Any) -> OrderResponse:
        time.sleep(self.latency_seconds)
        return self._delegate.place_order(request)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        time.sleep(self.latency_seconds)
        return self._delegate.ltp(symbol, exchange)

    def history(self, symbol: str, **kwargs) -> pd.DataFrame:
        time.sleep(self.latency_seconds)
        return self._delegate.history(symbol, **kwargs)

    def positions(self) -> list[dict]:
        time.sleep(self.latency_seconds)
        return self._delegate.positions()

    def funds(self) -> FundLimits:
        time.sleep(self.latency_seconds)
        return self._delegate.funds()

    def cancel_order(self, order_id: str) -> bool:
        time.sleep(self.latency_seconds)
        return self._delegate.cancel_order(order_id)

    def __getattr__(self, name: str) -> Any:
        """Delegate all other calls."""
        return getattr(self._delegate, name)
