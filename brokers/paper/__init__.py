"""PaperBroker — simulated broker for backtesting and paper trading.

Implements the Broker ABC with instant fills, no network calls.
Useful for strategy development, backtesting, and safe testing.

Usage::

    from brokers.paper import PaperBroker

    broker = PaperBroker(initial_capital=Decimal("1000000"))
    broker.connect()
    resp = broker.place_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"))
    assert resp.success
"""

from __future__ import annotations

import random
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import pandas as pd

from brokers.common.core.broker import Broker
from brokers.common.core.domain import (
    FundLimits,
    Holding,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Side,
    Trade,
    Validity,
)
from brokers.common.core.schemas import (
    build_historical_df,
    build_market_depth_df,
    build_option_chain_df,
    build_quote_df,
)


class PaperBroker(Broker):
    """Simulated broker with instant fills at quoted prices."""

    def __init__(self, initial_capital: Decimal = Decimal("1000000"), name: str = "paper") -> None:
        self._name = name
        self._id = f"paper-{random.randint(1000, 9999)}"
        self._connected = False
        self._orders: list[Order] = []
        self._trades: list[Trade] = []
        self._positions: dict[str, Position] = {}
        self._holdings: list[Holding] = []
        self._capital = initial_capital
        self._order_seq = 0
        self._trade_seq = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._id

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def is_connected(self) -> bool:
        return self._connected

    # ── Market data (simulated) ───────────────────────────────────

    def get_historical_data(
        self, symbol: str, exchange: str, from_date: date, to_date: date, timeframe: str = "1d"
    ) -> pd.DataFrame:
        from datetime import timedelta

        candles = []
        price = 1000.0
        curr = from_date
        while curr <= to_date:
            dt = datetime(curr.year, curr.month, curr.day, 15, 30, tzinfo=timezone.utc)
            change = random.uniform(-0.02, 0.02)
            o = price
            c = price * (1 + change)
            h = max(o, c) * (1 + random.uniform(0, 0.005))
            l = min(o, c) * (1 - random.uniform(0, 0.005))
            candles.append(
                {
                    "timestamp": dt,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": random.randint(10000, 500000),
                    "oi": 0,
                }
            )
            price = c
            curr += timedelta(days=1)
        return build_historical_df(candles, symbol, exchange, timeframe)

    def get_quote(self, symbol: str, exchange: str) -> pd.DataFrame:
        ltp = 1000.0 + random.uniform(-50, 50)
        return build_quote_df(
            symbol,
            exchange,
            ltp=ltp,
            bid=ltp - 0.5,
            ask=ltp + 0.5,
            volume=random.randint(50000, 500000),
        )

    def get_option_chain(self, underlying: str, exchange: str, expiry: str) -> pd.DataFrame:
        spot = 25000.0
        rows = []
        for strike in range(int(spot) - 500, int(spot) + 500, 100):
            for opt_type, sign in [("CE", 1), ("PE", -1)]:
                intrinsic = max(sign * (spot - strike), 0)
                ltp = intrinsic + random.uniform(5, 50)
                rows.append(
                    {
                        "underlying": underlying,
                        "expiry": expiry,
                        "strike": float(strike),
                        "option_type": opt_type,
                        "ltp": ltp,
                        "bid": ltp - 0.5,
                        "ask": ltp + 0.5,
                        "volume": random.randint(100, 5000),
                        "oi": random.randint(1000, 50000),
                        "iv": 15.0 + random.uniform(-3, 3),
                        "timestamp": datetime.now(timezone.utc),
                    }
                )
        return build_option_chain_df(rows)

    def get_market_depth(self, symbol: str, exchange: str) -> pd.DataFrame:
        base = 1000.0
        bids = [{"price": base - i * 0.5, "quantity": random.randint(50, 500)} for i in range(20)]
        asks = [{"price": base + i * 0.5, "quantity": random.randint(50, 500)} for i in range(20)]
        return build_market_depth_df(symbol, bids, asks)

    # ── Trading (instant fills) ───────────────────────────────────

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        self._order_seq += 1
        order_id = f"PPR-{self._order_seq:06d}"
        fill_price = price if price > 0 else Decimal(str(1000.0 + random.uniform(-5, 5)))

        order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=OrderType(order_type),
            quantity=quantity,
            filled_quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            status=OrderStatus.FILLED,
            timestamp=datetime.now(timezone.utc),
            product_type=ProductType(product_type),
            validity=Validity(validity),
            avg_price=fill_price,
            correlation_id=correlation_id,
        )
        self._orders.append(order)

        self._trade_seq += 1
        trade = Trade(
            trade_id=f"PPR-T-{self._trade_seq:06d}",
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=fill_price,
            trade_value=fill_price * quantity,
            timestamp=datetime.now(timezone.utc),
            product_type=ProductType(product_type),
        )
        self._trades.append(trade)

        self._update_position(symbol, exchange, side, quantity, fill_price)
        return OrderResponse.ok(order_id)

    def get_order(self, order_id: str) -> Order | None:
        for o in self._orders:
            if o.order_id == order_id:
                return o
        return None

    def get_orders(self) -> list[Order]:
        return list(self._orders)

    def cancel_order(self, order_id: str) -> bool:
        for o in self._orders:
            if o.order_id == order_id and o.status == OrderStatus.OPEN:
                o.status = OrderStatus.CANCELLED
                return True
        return False

    # ── Portfolio ─────────────────────────────────────────────────

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_holdings(self) -> list[Holding]:
        return list(self._holdings)

    def get_fund_limits(self) -> FundLimits:
        used = sum(abs(p.quantity) * p.avg_price for p in self._positions.values())
        return FundLimits(
            available_balance=self._capital - used, used_margin=used, total_margin=self._capital
        )

    def get_trades(self) -> list[Trade]:
        return list(self._trades)

    # ── Internal ──────────────────────────────────────────────────

    def _update_position(
        self, symbol: str, exchange: str, side: Side, quantity: int, price: Decimal
    ) -> None:
        key = f"{symbol}:{exchange}"
        if key not in self._positions:
            self._positions[key] = Position(symbol=symbol, exchange=exchange)
        pos = self._positions[key]
        delta = quantity if side == Side.BUY else -quantity
        if pos.quantity == 0:
            pos.avg_price = price
        elif (pos.quantity > 0 and delta < 0) or (pos.quantity < 0 and delta > 0):
            closed = min(abs(pos.quantity), abs(delta))
            pos.realized_pnl += (
                Decimal(str(closed)) * (price - pos.avg_price) * (1 if pos.quantity > 0 else -1)
            )
        pos.quantity += delta
        pos.ltp = price
        if pos.quantity == 0:
            pos.avg_price = Decimal("0")
