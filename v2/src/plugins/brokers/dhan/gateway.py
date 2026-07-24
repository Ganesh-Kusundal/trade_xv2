"""DhanGateway — BrokerAdapter facade over DhanConnection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Bar, Instrument, MarketDepth, Order, Position, Quote
from domain.enums import AssetClass
from domain.ports.types import BrokerSnapshot
from domain.value_objects import InstrumentId, OrderId, Price, TimeFrame
from plugins.brokers.common.capabilities import BrokerCapabilities
from plugins.brokers.common.extensions import BrokerExtensions
from plugins.brokers.common.transport import BaseTransport
from plugins.brokers.dhan.auth import DhanTokenManager
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.dhan.connection import DhanConnection
from plugins.brokers.dhan.extensions import DhanDepth20Extension, DhanDepth200Extension

DHAN_CAPABILITIES = BrokerCapabilities(
    supports_market_order=True,
    supports_limit_order=True,
    supports_stop_order=True,
    supports_modify=True,
    supports_cancel=True,
    # Reflects the real wire surface (verified in dhan/wire.py + adapters):
    # NSE/BSE equity+derivatives, NFO/BFO F&O, MCX commodity futures/options,
    # CDS/BCD currency. Historical + live market data supported for all.
    supported_asset_classes=frozenset(
        {AssetClass.EQUITY, AssetClass.DERIVATIVE, AssetClass.COMMODITY, AssetClass.CURRENCY}
    ),
)


class DhanGateway:
    def __init__(
        self,
        config: DhanConfig | None = None,
        transport: BaseTransport | None = None,
        token_manager: DhanTokenManager | None = None,
        ws_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.connection = DhanConnection(
            config=config,
            transport=transport,
            token_manager=token_manager,
            ws_factory=ws_factory,
        )
        self.extensions = BrokerExtensions(
            DhanDepth20Extension(_streaming=self.connection.streaming),
            DhanDepth200Extension(_streaming=self.connection.streaming),
        )

    def extension(self, ext_type: type) -> Any:
        """Look up a Dhan-specific capability (super orders, EDIS, ...) by type."""
        return self.extensions.get(ext_type)

    def connect(self) -> None:
        self.connection.connect()
        # Proactive first-load: warm the instrument master on connect so the
        # first ltp()/quote()/order call never pays the download latency.
        # Run off the caller thread — a cold cache means a ~28 MB Dhan
        # CSV (or 3.6 MB Upstox gz) download that must NOT block
        # connect() in a live trading loop. The lazy ensure_fresh() on each
        # data/order method still blocks if a caller needs symbols before the
        # background warm-load finishes (same as before).
        import threading

        threading.Thread(target=self.ensure_fresh, daemon=True).start()

    def authenticate(self) -> bool:
        return self.connection.authenticate()

    def close(self) -> None:
        self.connection.disconnect()

    def disconnect(self) -> None:
        self.close()

    def ensure_fresh(self, *, force_refresh: bool = False) -> None:
        """Lazy auto-load of the instrument master on first use.

        The gateway triggers the scrip-master download/registration the first
        time any market-data or order method is called, so callers never have
        to remember to call ``load_instruments()`` manually. The connection's
        own lock makes this safe to call on every request.
        """
        self.connection.ensure_fresh(force_refresh=force_refresh)

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        self.ensure_fresh()
        return self.connection.market_data.get_quote(instrument_id)

    def ltp(self, instrument_id: InstrumentId) -> Price:
        self.ensure_fresh()
        return self.connection.market_data.get_ltp(instrument_id)

    def depth(self, instrument_id: InstrumentId) -> MarketDepth:
        self.ensure_fresh()
        return self.connection.market_data.get_depth(instrument_id)

    def history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        self.ensure_fresh()
        return self.connection.market_data.get_history(instrument_id, timeframe, start, end)

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        self.ensure_fresh()
        if not self.connection.config.allow_live_orders:
            raise RuntimeError(
                "Live orders disabled; set DhanConfig.allow_live_orders=True "
                "(env DHAN_ALLOW_LIVE_ORDERS=true) to enable"
            )
        return self.connection.orders.place_order(command)

    def submit_order(self, command: PlaceOrderCommand) -> OrderId:
        return self.place_order(command)

    def cancel_order(self, order_id: OrderId) -> None:
        self.connection.orders.cancel_order(order_id)

    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None:
        self.connection.orders.modify_order(order_id, command)

    def get_order(self, order_id: OrderId) -> Order:
        return self.connection.orders.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self.connection.orders.get_orderbook()

    def get_positions(self) -> list[Position]:
        return self.connection.portfolio.get_positions()

    def get_holdings(self) -> list[Position]:
        return self.connection.portfolio.get_holdings()

    def get_funds(self) -> Account:
        return self.connection.portfolio.get_funds()

    def get_balance(self) -> Account:
        return self.get_funds()

    def load_instruments(self) -> None:
        self.connection.load_instruments()

    def search(self, query: str) -> list[Instrument]:
        return self.connection.instruments.search(query)

    def stream(
        self,
        instrument_id: InstrumentId,
        on_quote: Callable[[Quote], None] | None = None,
    ) -> None:
        self.connection.streaming.stream(instrument_id, on_quote)

    def unstream(self, instrument_id: InstrumentId) -> None:
        self.connection.streaming.unstream(instrument_id)

    def stream_order(self, on_order: Callable[[Order], None] | None = None) -> None:
        self.connection.streaming.stream_order(on_order)

    def mass_status(self) -> BrokerSnapshot:
        return self.connection.mass_status()

    def token_status(self) -> dict[str, object]:
        """Token health for a liveness probe / warning before mid-session expiry."""
        return self.connection.token_status()

    def capabilities(self) -> BrokerCapabilities:
        return DHAN_CAPABILITIES
