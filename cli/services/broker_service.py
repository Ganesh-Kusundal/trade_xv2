"""Broker service layer — bridges CLI/TUI to the new BrokerGateway architecture."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock

from brokers.common.core.domain import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side as OrderSide,
    Trade,
)
from brokers.common.gateway import MarketDataGateway
from brokers.common.oms.context import TradingContext
from brokers.common.oms.factory import create_trading_context
from brokers.dhan import BrokerFactory
from brokers.paper import PaperGateway
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env.local"


def _load_broker_env() -> None:
    """Ensure .env.local credentials are loaded into the environment."""
    if _ENV_PATH.exists() and _ENV_PATH.stat().st_size > 0:
        load_dotenv(_ENV_PATH, override=True)


# ---------------------------------------------------------------------------
# Mock broker — lightweight fallback when .env.local is absent
# ---------------------------------------------------------------------------

class MockBroker:
    """In-memory broker returning realistic simulated data for CLI/TUI testing.

    Mirrors the ``BrokerGateway`` public interface so consumers can treat both
    interchangeably.
    """

    def __init__(self, name: str = "dhan", client_id: str = "MOCK0001"):
        self._name = name
        self._client_id = client_id
        self._connected = True  # mock is always "live"
        self._lock = RLock()
        self._order_seq = 100
        self._trade_seq = 200

        now = datetime.now(timezone.utc)

        self._orders: list[Order] = [
            Order(
                order_id=f"{name.upper()}-ORD-101",
                symbol="RELIANCE",
                exchange="NSE",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
                filled_quantity=10,
                price=Decimal("2550.00"),
                status=OrderStatus.FILLED,
                product_type=ProductType.INTRADAY,
                avg_price=Decimal("2550.00"),
                timestamp=now - timedelta(hours=2),
            ),
            Order(
                order_id=f"{name.upper()}-ORD-102",
                symbol="SBIN",
                exchange="NSE",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=50,
                filled_quantity=0,
                price=Decimal("590.00"),
                status=OrderStatus.OPEN,
                product_type=ProductType.INTRADAY,
                timestamp=now - timedelta(minutes=15),
            ),
        ]

        self._trades: list[Trade] = [
            Trade(
                trade_id=f"{name.upper()}-TRD-201",
                order_id=f"{name.upper()}-ORD-101",
                symbol="RELIANCE",
                exchange="NSE",
                side=OrderSide.BUY,
                quantity=10,
                price=Decimal("2550.00"),
                timestamp=now - timedelta(hours=2),
            ),
        ]

        self._positions: list[Position] = [
            Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                avg_price=Decimal("2550.00"),
                ltp=Decimal("2565.50"),
                unrealized_pnl=Decimal("155.00"),
                realized_pnl=Decimal("0.00"),
                product_type=ProductType.INTRADAY,
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

        self._balance = Balance(
            available_balance=Decimal("452300.50"),
            sod_limit=Decimal("500000.00"),
            collateral_amount=Decimal("0.00"),
            utilized_amount=Decimal("47700.00"),
            withdrawable_balance=Decimal("452300.50"),
        )

    # -- identity -----------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def client_id(self) -> str:
        return self._client_id

    # -- lifecycle ----------------------------------------------------------

    def load_instruments(self, **_kw) -> None:
        pass  # nothing to load for mock

    def close(self) -> None:
        self._connected = False

    # -- market data shortcuts ----------------------------------------------

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        base = {"RELIANCE": Decimal("2565.50"), "SBIN": Decimal("590.00")}
        return base.get(symbol, Decimal("25010.00"))

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        ltp = self.get_ltp(symbol, exchange)
        return Quote(
            symbol=symbol,
            ltp=ltp,
            open=ltp * Decimal("0.998"),
            high=ltp * Decimal("1.005"),
            low=ltp * Decimal("0.995"),
            close=ltp * Decimal("0.999"),
            volume=random.randint(50_000, 2_000_000),
            change=Decimal("0"),
        )

    def get_depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        ltp = self.get_ltp(symbol, exchange)
        bids = [
            DepthLevel(price=ltp - Decimal(str(i)), quantity=random.randint(75, 1500))
            for i in range(1, 6)
        ]
        asks = [
            DepthLevel(price=ltp + Decimal(str(i)), quantity=random.randint(75, 1500))
            for i in range(1, 6)
        ]
        return MarketDepth(bids=bids, asks=asks)

    # -- order shortcuts ----------------------------------------------------

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | OrderSide = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str | OrderType = "MARKET",
        product_type: str | ProductType = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> Order:
        if isinstance(side, str):
            side = OrderSide(side)
        if isinstance(order_type, str):
            order_type = OrderType(order_type)

        is_market = order_type == OrderType.MARKET
        fill_price = price or Decimal("1250.00")

        with self._lock:
            self._order_seq += 1
            order_id = f"{self._name.upper()}-ORD-{self._order_seq:05d}"

            order = Order(
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                filled_quantity=quantity if is_market else 0,
                price=price,
                status=OrderStatus.FILLED if is_market else OrderStatus.OPEN,
                product_type=ProductType.INTRADAY,
                avg_price=fill_price,
                timestamp=datetime.now(timezone.utc),
            )
            self._orders.append(order)

            if is_market:
                self._trade_seq += 1
                self._trades.append(
                    Trade(
                        trade_id=f"{self._name.upper()}-TRD-{self._trade_seq:05d}",
                        order_id=order_id,
                        symbol=symbol,
                        exchange=exchange,
                        side=side,
                        quantity=quantity,
                        price=fill_price,
                        trade_value=fill_price * quantity,
                    )
                )
                self._positions = self._update_position(
                    symbol, exchange, side, quantity, fill_price
                )
            return order

    def _update_position(
        self, symbol: str, exchange: str, side: OrderSide, quantity: int, price: Decimal
    ) -> list[Position]:
        delta = quantity if side == OrderSide.BUY else -quantity
        for i, pos in enumerate(self._positions):
            if pos.symbol == symbol and pos.exchange == exchange:
                new_pos = pos.with_fill(delta, price)
                new_positions = list(self._positions)
                new_positions[i] = new_pos
                return new_positions
        # New position
        new_pos = Position(
            symbol=symbol,
            exchange=exchange,
            quantity=delta,
            avg_price=price,
            ltp=price,
            product_type=ProductType.INTRADAY,
        )
        return self._positions + [new_pos]

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            for i, order in enumerate(self._orders):
                if order.order_id == order_id and order.status in (
                    OrderStatus.OPEN,
                    OrderStatus.PARTIALLY_FILLED,
                ):
                    self._orders[i] = order.with_status(OrderStatus.CANCELLED)
                    return True
            return False

    def get_orderbook(self) -> list[Order]:
        with self._lock:
            return list(self._orders)

    def get_trade_book(self) -> list[Trade]:
        with self._lock:
            return list(self._trades)

    # -- portfolio shortcuts ------------------------------------------------

    def get_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions)

    def get_holdings(self) -> list[Holding]:
        with self._lock:
            return list(self._holdings)

    def get_balance(self) -> Balance:
        with self._lock:
            return self._balance

    @property
    def portfolio(self) -> _MockPortfolio:
        """Expose a ``portfolio`` sub-object mirroring ``BrokerGateway.portfolio``."""
        return _MockPortfolio(self)


class _MockPortfolio:
    """Thin adapter that delegates to ``MockBroker`` for portfolio data.

    Matches the interface expected by ``cli.commands.portfolio``
    (``gw.portfolio.get_holdings()``, ``gw.portfolio.get_positions()``).
    """

    def __init__(self, broker: MockBroker) -> None:
        self._broker = broker

    def get_holdings(self) -> list[Holding]:
        return self._broker.get_holdings()

    def get_positions(self) -> list[Position]:
        return self._broker.get_positions()

    def get_balance(self) -> Balance:
        return self._broker.get_balance()


def _order_to_dict(o: Order) -> dict:
    """Helper to rebuild a frozen Order with overrides."""
    return {
        "order_id": o.order_id,
        "symbol": o.symbol,
        "exchange": o.exchange,
        "side": o.side,
        "order_type": o.order_type,
        "quantity": o.quantity,
        "filled_quantity": o.filled_quantity,
        "price": o.price,
        "trigger_price": o.trigger_price,
        "status": o.status,
        "product_type": o.product_type,
        "validity": o.validity,
        "avg_price": o.avg_price,
        "correlation_id": o.correlation_id,
        "reject_reason": o.reject_reason,
        "timestamp": o.timestamp,
    }


# ---------------------------------------------------------------------------
# BrokerService
# ---------------------------------------------------------------------------

class BrokerService:
    """Resolves and manages the active broker (live Dhan gateway or mock)."""

    def __init__(self) -> None:
        self._gateway: MarketDataGateway | None = None
        self._paper: PaperGateway | None = None
        self._mock: MockBroker | None = None
        self._active_name: str = "dhan"
        self._dhan_load_error: str | None = None
        self._initialized = False
        self._trading_context: TradingContext | None = None

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        _load_broker_env()
        if _ENV_PATH.exists():
            try:
                self._gateway = BrokerFactory.create(
                    env_path=_ENV_PATH,
                    load_instruments=True,
                )
                self._create_trading_context()
                logger.info("Dhan BrokerGateway created successfully")
            except Exception as exc:
                self._dhan_load_error = str(exc)
                logger.warning("Failed to create Dhan gateway: %s", exc)

        if self._gateway is None:
            self._mock = MockBroker("dhan", "MOCK0001")

    def _create_trading_context(self) -> None:
        """Create a TradingContext with reconciliation for the active gateway."""
        reconciliation_service = None

        if self._gateway is not None:
            # Extract broker-specific reconciliation service from the gateway
            conn = getattr(self._gateway, "_conn", None)
            if conn is not None:
                # Dhan gateway — build reconciliation from connection adapters
                try:
                    from brokers.dhan.reconciliation import DhanReconciliationService
                    reconciliation_service = DhanReconciliationService(
                        orders=conn.orders,
                        portfolio=conn.portfolio,
                        oms=getattr(conn, "_order_manager", None),
                    )
                except Exception as exc:
                    logger.debug("Dhan reconciliation service unavailable: %s", exc)
            else:
                broker = getattr(self._gateway, "_broker", None)
                if broker is not None and hasattr(broker, "reconciliation_service"):
                    # Upstox gateway — use pre-built reconciliation service
                    reconciliation_service = broker.reconciliation_service

        self._trading_context = create_trading_context(
            reconciliation_service=reconciliation_service,
            reconciliation_interval_seconds=300.0,
        )

    @property
    def trading_context(self) -> TradingContext | None:
        """Return the shared TradingContext (may be *None* before init)."""
        self._ensure_initialized()
        return self._trading_context

    # -- properties ---------------------------------------------------------

    @property
    def active_broker(self) -> MarketDataGateway | PaperGateway | MockBroker:
        """Return the active broker: live Dhan, paper, or mock."""
        self._ensure_initialized()
        if self._active_name == "paper" and self._paper is not None:
            return self._paper
        if self._gateway is not None:
            return self._gateway
        if self._paper is not None:
            return self._paper
        assert self._mock is not None
        return self._mock

    @property
    def active_broker_name(self) -> str:
        return self._active_name

    @property
    def is_live_dhan_active(self) -> bool:
        """``True`` when a real ``BrokerGateway`` is connected (not mock)."""
        self._ensure_initialized()
        return self._gateway is not None

    @property
    def dhan_load_error(self) -> str | None:
        return self._dhan_load_error

    # -- broker management --------------------------------------------------

    def set_active_broker(self, name: str) -> None:
        self._ensure_initialized()
        name_lower = name.lower()
        if name_lower == "paper":
            if self._paper is None:
                self._paper = PaperGateway()
            self._active_name = "paper"
        elif name_lower == "dhan":
            if self._gateway is None:
                raise ValueError("Dhan broker not available. Check .env.local credentials.")
            self._active_name = "dhan"
        else:
            raise ValueError(f"Broker '{name}' is not registered. Use 'dhan' or 'paper'.")
        self._active_name = name_lower

    def use_paper(self) -> None:
        """Switch to paper trading mode."""
        self.set_active_broker("paper")

    def get_broker_statuses(self) -> list[dict[str, str]]:
        self._ensure_initialized()
        statuses = []
        if self._gateway is not None:
            statuses.append({"broker": "Dhan", "status": "Connected"})
        else:
            statuses.append({"broker": "Dhan", "status": "Unavailable"})
        statuses.append({"broker": "Paper", "status": "Available"})
        return statuses

    def close(self) -> None:
        """Clean up the live gateway connection and stop reconciliation."""
        if self._trading_context is not None:
            try:
                self._trading_context.stop_reconciliation()
            except Exception:
                pass
            self._trading_context = None
        if self._gateway is not None:
            try:
                self._gateway.close()
            except Exception:
                pass
