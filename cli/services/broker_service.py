"""Broker service layer for diagnostics and operation terminal."""

from __future__ import annotations

import contextlib
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from pandas import DataFrame

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
from brokers.dhan import DhanBroker
from brokers.dhan.mapper.instruments import DhanInstrumentResolver


class MockBroker(Broker):
    """Mock broker adapter returning realistic simulated data for TUI/CLI testing."""

    def __init__(self, name: str, broker_id: str):
        self._name = name
        self._broker_id = broker_id
        self._connected = False
        self.instrument_resolver = DhanInstrumentResolver()

        # Internal state to track simulated orders and trades placed during CLI session
        self._orders: list[Order] = [
            Order(
                order_id=f"{self.name.upper()}-ORD-101",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
                filled_quantity=10,
                price=Decimal("2550.00"),
                status=OrderStatus.FILLED,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
                product_type=ProductType.INTRADAY,
                avg_price=Decimal("2550.00"),
            ),
            Order(
                order_id=f"{self.name.upper()}-ORD-102",
                symbol="SBIN",
                exchange="NSE",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                quantity=50,
                filled_quantity=0,
                price=Decimal("590.00"),
                status=OrderStatus.OPEN,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=15),
                product_type=ProductType.INTRADAY,
            ),
            Order(
                order_id=f"{self.name.upper()}-ORD-103",
                symbol="NIFTY26JUN25000CE",
                exchange="NFO",
                side=Side.SELL,
                order_type=OrderType.MARKET,
                quantity=75,
                filled_quantity=75,
                price=Decimal("120.00"),
                status=OrderStatus.FILLED,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
                product_type=ProductType.INTRADAY,
                avg_price=Decimal("122.50"),
            ),
        ]

        self._trades: list[Trade] = [
            Trade(
                trade_id=f"{self.name.upper()}-TRD-201",
                order_id=f"{self.name.upper()}-ORD-101",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                price=Decimal("2550.00"),
                timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            ),
            Trade(
                trade_id=f"{self.name.upper()}-TRD-203",
                order_id=f"{self.name.upper()}-ORD-103",
                symbol="NIFTY26JUN25000CE",
                exchange="NFO",
                side=Side.SELL,
                quantity=75,
                price=Decimal("122.50"),
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
            ),
        ]

        self._positions: list[Position] = [
            Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                avg_price=Decimal("2550.00"),
                ltp=Decimal("2565.50"),
                realized_pnl=Decimal("0.00"),
                unrealized_pnl=Decimal("155.00"),
            ),
            Position(
                symbol="NIFTY26JUN25000CE",
                exchange="NFO",
                quantity=-75,
                avg_price=Decimal("122.50"),
                ltp=Decimal("118.00"),
                realized_pnl=Decimal("0.00"),
                unrealized_pnl=Decimal("337.50"),
            ),
        ]

        self._holdings: list[Holding] = [
            Holding(
                symbol="INFY",
                exchange="NSE",
                quantity=20,
                available_quantity=20,
                avg_price=Decimal("1420.00"),
                ltp=Decimal("1435.00"),
                pnl=Decimal("300.00"),
            ),
            Holding(
                symbol="HDFCBANK",
                exchange="NSE",
                quantity=50,
                available_quantity=50,
                avg_price=Decimal("1580.00"),
                ltp=Decimal("1565.00"),
                pnl=Decimal("-750.00"),
            ),
        ]

        self._funds = FundLimits(
            available_balance=Decimal("452300.50"),
            used_margin=Decimal("47700.00"),
            total_margin=Decimal("500000.00"),
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._broker_id

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def is_connected(self) -> bool:
        return self._connected

    def get_historical_data(
        self,
        symbol: str,
        exchange: str,
        from_date: date,
        to_date: date,
        timeframe: str = "1d",
    ) -> DataFrame:
        # Generate random OHLCV candles
        candles = []
        curr = from_date
        price = 2500.0 if "NIFTY" not in symbol else 25000.0
        while curr <= to_date:
            dt = datetime(curr.year, curr.month, curr.day, 9, 15, tzinfo=timezone.utc)
            chg = random.uniform(-0.02, 0.02)
            o = price
            c = price * (1 + chg)
            h = max(o, c) * (1 + random.uniform(0.001, 0.01))
            l = min(o, c) * (1 - random.uniform(0.001, 0.01))
            vol = random.randint(10000, 500000)
            oi = random.randint(0, 100000)
            candles.append(
                {
                    "timestamp": dt,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": vol,
                    "oi": oi,
                }
            )
            price = c
            curr += timedelta(days=1)
        return build_historical_df(candles, symbol, exchange, timeframe)

    def get_quote(self, symbol: str, exchange: str) -> DataFrame:
        base_price = 2565.50 if symbol == "RELIANCE" else (590.00 if symbol == "SBIN" else 25010.00)
        ltp = base_price * (1 + random.uniform(-0.002, 0.002))
        bid = ltp - random.uniform(0.1, 0.5)
        ask = ltp + random.uniform(0.1, 0.5)
        vol = random.randint(50000, 2000000)
        oi = random.randint(10000, 5000000)
        return build_quote_df(symbol, exchange, ltp, bid, ask, vol, oi)

    def get_option_chain(
        self,
        underlying: str,
        exchange: str,
        expiry: str,
    ) -> DataFrame:
        spot = 25000.0 if "NIFTY" in underlying else 2500.0
        strike_diff = 100.0 if spot > 10000.0 else 20.0
        strikes = [int(spot - spot % strike_diff + (i * strike_diff)) for i in range(-5, 6)]

        rows = []
        for strike in strikes:
            # Call option
            c_dist = spot - strike
            c_ltp = max(c_dist, 5.0) + random.uniform(1, 10)
            rows.append(
                {
                    "underlying": underlying,
                    "expiry": expiry,
                    "strike": float(strike),
                    "option_type": "CE",
                    "ltp": c_ltp,
                    "bid": c_ltp - 0.5,
                    "ask": c_ltp + 0.5,
                    "volume": random.randint(100, 5000),
                    "oi": random.randint(1000, 50000),
                    "iv": 15.4 + random.uniform(-1, 1),
                    "delta": 0.5 + (c_dist / spot) * 5,
                    "gamma": 0.002,
                    "theta": -5.4,
                    "vega": 10.2,
                    "rho": 0.01,
                    "timestamp": datetime.now(timezone.utc),
                }
            )

            # Put option
            p_dist = strike - spot
            p_ltp = max(p_dist, 5.0) + random.uniform(1, 10)
            rows.append(
                {
                    "underlying": underlying,
                    "expiry": expiry,
                    "strike": float(strike),
                    "option_type": "PE",
                    "ltp": p_ltp,
                    "bid": p_ltp - 0.5,
                    "ask": p_ltp + 0.5,
                    "volume": random.randint(100, 5000),
                    "oi": random.randint(1000, 50000),
                    "iv": 16.2 + random.uniform(-1, 1),
                    "delta": -0.5 + (p_dist / spot) * 5,
                    "gamma": 0.002,
                    "theta": -5.1,
                    "vega": 9.8,
                    "rho": -0.01,
                    "timestamp": datetime.now(timezone.utc),
                }
            )

        return build_option_chain_df(rows)

    def get_market_depth(self, symbol: str, exchange: str) -> DataFrame:
        base_price = 2500.0 if "NIFTY" not in symbol else 25000.0
        bids = []
        asks = []
        b_price = base_price - 0.10
        a_price = base_price + 0.10
        for _ in range(20):
            bids.append({"price": b_price, "quantity": random.randint(75, 1500)})
            asks.append({"price": a_price, "quantity": random.randint(75, 1500)})
            b_price -= random.choice([0.05, 0.10, 0.15])
            a_price += random.choice([0.05, 0.10, 0.15])
        return build_market_depth_df(symbol, bids, asks)

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
        order_id = f"{self.name.upper()}-ORD-{random.randint(10000, 99999)}"
        new_order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=OrderType(order_type),
            quantity=quantity,
            filled_quantity=quantity if order_type == "MARKET" else 0,
            price=price,
            trigger_price=trigger_price,
            status=OrderStatus.FILLED if order_type == "MARKET" else OrderStatus.OPEN,
            timestamp=datetime.now(timezone.utc),
            product_type=ProductType(product_type),
            validity=Validity(validity),
            avg_price=price if order_type != "MARKET" else (price or Decimal("1250.00")),
            correlation_id=correlation_id,
        )
        self._orders.append(new_order)

        if order_type == "MARKET":
            new_trade = Trade(
                trade_id=f"{self.name.upper()}-TRD-{random.randint(10000, 99999)}",
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=new_order.avg_price,
                timestamp=datetime.now(timezone.utc),
            )
            self._trades.append(new_trade)

            # Update positions dynamically
            found = False
            for pos in self._positions:
                if pos.symbol == symbol:
                    found = True
                    q_delta = quantity if side == Side.BUY else -quantity
                    pos.quantity += q_delta
                    break
            if not found:
                self._positions.append(
                    Position(
                        symbol=symbol,
                        exchange=exchange,
                        quantity=quantity if side == Side.BUY else -quantity,
                        avg_price=new_order.avg_price,
                        ltp=new_order.avg_price,
                    )
                )

        return OrderResponse.ok(order_id, "Order placed successfully")

    def get_order(self, order_id: str) -> Order | None:
        for order in self._orders:
            if order.order_id == order_id:
                return order
        return None

    def get_orders(self) -> list[Order]:
        return list(self._orders)

    def cancel_order(self, order_id: str) -> bool:
        for order in self._orders:
            if order.order_id == order_id:
                if order.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
                    order.status = OrderStatus.CANCELLED
                    return True
        return False

    def get_positions(self) -> list[Position]:
        # Live recalculation of PnL for mocks
        for pos in self._positions:
            pos.ltp = pos.avg_price * Decimal(str(random.uniform(0.99, 1.01)))
            pos.unrealized_pnl = pos.pnl
        return list(self._positions)

    def get_holdings(self) -> list[Holding]:
        for hld in self._holdings:
            hld.ltp = hld.avg_price * Decimal(str(random.uniform(0.99, 1.01)))
            hld.pnl = Decimal(str(hld.quantity)) * (hld.ltp - hld.avg_price)
        return list(self._holdings)

    def get_fund_limits(self) -> FundLimits:
        return self._funds

    def get_trades(self) -> list[Trade]:
        return list(self._trades)


class BrokerService:
    """Manager resolving real and mock brokers."""

    def __init__(self):
        self._brokers: dict[str, Broker] = {}
        self._active_name = "dhan"
        self._dhan_load_error: str | None = None

        # Load Dhan broker if .env.local exists
        dhan_loaded = False
        env_path = Path(".env.local")
        if env_path.exists():
            try:
                # Instantiate DhanBroker
                broker = DhanBroker.from_env(env_path=env_path)
                # Load the instrument catalog so symbol resolution works.
                # Use the same cache dir as the CLI instruments command
                # (runtime-dev/instruments).  Falls back to the broker's own
                # cache dir (.cache/dhan/instruments/) if the primary is empty.
                self._load_instrument_catalog(broker)
                self._brokers["dhan"] = broker
                dhan_loaded = True
            except Exception as exc:
                self._dhan_load_error = str(exc)

        if not dhan_loaded:
            self._brokers["dhan"] = MockBroker("dhan", "1106251237")

        # Register other mock brokers
        self._brokers["zerodha"] = MockBroker("zerodha", "ZR1234")
        self._brokers["upstox"] = MockBroker("upstox", "UP9876")

    @staticmethod
    def _load_instrument_catalog(broker: DhanBroker) -> None:
        """Load the Dhan instrument catalog into the broker's InstrumentService.

        Resolution order:
        1. Today's snapshot in ``runtime-dev/instruments/`` (the canonical
           CLI location, populated by ``tradex instruments refresh``).
        2. The broker's own ``refresh_instrument_snapshot()`` which looks in
           ``.cache/dhan/instruments/`` and downloads from Dhan if absent.

        Errors are suppressed so broker initialisation always succeeds.
        """
        from datetime import date as _date

        cli_cache_dir = Path("runtime-dev/instruments")
        today_snapshot = cli_cache_dir / f"api-scrip-master-{_date.today()}.csv"
        try:
            if today_snapshot.exists() and today_snapshot.stat().st_size > 0:
                broker.load_instrument_catalog(today_snapshot)
                return
        except Exception:
            pass
        # Fallback: let the service download/use its own cache
        with contextlib.suppress(Exception):
            broker.refresh_instrument_snapshot(force=False)

    @property
    def brokers(self) -> dict[str, Broker]:
        return self._brokers

    @property
    def active_broker(self) -> Broker:
        return self._brokers[self._active_name]

    @property
    def active_broker_name(self) -> str:
        return self._active_name

    @property
    def is_live_dhan_active(self) -> bool:
        return isinstance(self._brokers.get("dhan"), DhanBroker)

    @property
    def dhan_load_error(self) -> str | None:
        return self._dhan_load_error

    def set_active_broker(self, name: str) -> None:
        name_lower = name.lower()
        if name_lower not in self._brokers:
            raise ValueError(f"Broker '{name}' is not registered.")
        self._active_name = name_lower

    def get_broker_statuses(self) -> list[dict[str, str]]:
        statuses = []
        for name, b in self._brokers.items():
            if isinstance(b, DhanBroker):
                # Real Dhan Broker connection check
                connected = b.is_connected()
                status = "Connected" if connected else "Disconnected"
            else:
                connected = b.is_connected()
                status = "Connected" if connected else "Disabled"
            statuses.append({"broker": name.capitalize(), "status": status})
        return statuses
