"""Dhan extended capabilities — broker-specific methods beyond MarketDataGateway ABC.

This module contains Dhan-specific functionality that extends beyond the
MarketDataGateway contract. These methods are exposed via the
``gateway.extended`` property to maintain architectural compliance.

This facade composes four focused sub-facades (orders, account, data,
positions) and re-exposes their methods for backward compatibility.

Usage::

    gateway = BrokerGateway(connection)

    # Broker-specific operations via extended
    expiries = gateway.extended.get_option_expiries("NIFTY", "NFO")
    contracts = gateway.extended.get_futures_contracts("GOLD", "MCX")
    errors = gateway.extended.validate_order(symbol="RELIANCE", ...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain import OrderResponse

from brokers.dhan.extended_account import DhanAccountCapabilities
from brokers.dhan.extended_data import DhanDataCapabilities
from brokers.dhan.extended_orders import DhanOrderCapabilities
from brokers.dhan.extended_positions import DhanPositionCapabilities

if TYPE_CHECKING:
    from brokers.dhan.streaming.connection import DhanConnection


class DhanExtendedCapabilities:
    """Dhan-specific capabilities beyond the MarketDataGateway ABC.

    This facade composes four focused sub-facades and re-exposes their
    public methods so existing callers keep working unchanged:

    - :class:`DhanOrderCapabilities` — super/forever orders, conditional triggers
    - :class:`DhanAccountCapabilities` — ledger, profile, IP, EDIS, TPIN
    - :class:`DhanDataCapabilities` — option chain, futures, expiries, alerts, validation
    - :class:`DhanPositionCapabilities` — positions, holdings, balance, exit, P&L exit
    """

    def __init__(self, conn: DhanConnection) -> None:
        self._conn = conn
        self.orders = DhanOrderCapabilities(conn)
        self.account = DhanAccountCapabilities(conn)
        self.data = DhanDataCapabilities(conn)
        self.positions = DhanPositionCapabilities(conn)

    @property
    def instruments(self) -> Any:
        """Dhan SymbolResolver (typed DhanInstrument lookups).

        For the broker-internal :class:`DhanInstrumentService` (load /
        canonical resolve / wire refs) use ``gateway._conn.instruments``.
        """
        return self._conn.instruments.resolver

    @property
    def identity(self) -> Any:
        """Access the Dhan identity provider (PR-A).

        The provider is the single source of truth for symbol→security_id
        resolution. Adapters and callers that need to build a Dhan HTTP
        payload must go through ``identity.resolve_ref(symbol, exchange)``
        rather than calling the resolver directly.
        """
        return self._conn.identity

    # ── Order capabilities (delegated) ───────────────────────────────

    def place_super_order(self, **kwargs: Any) -> Any:
        return self.orders.place_super_order(**kwargs)

    def modify_super_order(self, order_id: str, **kwargs: Any) -> Any:
        return self.orders.modify_super_order(order_id, **kwargs)

    def cancel_super_order_leg(self, order_id: str, leg_name: str) -> OrderResponse:
        return self.orders.cancel_super_order_leg(order_id, leg_name)

    def get_super_orders(self) -> list[Any]:
        return self.orders.get_super_orders()

    def place_forever_order(self, request: Any) -> Any:
        return self.orders.place_forever_order(request)

    def modify_forever_order(self, order_id: str, request: Any) -> Any:
        return self.orders.modify_forever_order(order_id, request)

    def cancel_forever_order(self, order_id: str) -> OrderResponse:
        return self.orders.cancel_forever_order(order_id)

    def get_all_forever_orders(self) -> list[Any]:
        return self.orders.get_all_forever_orders()

    def place_conditional_trigger(self, request: Any) -> Any:
        return self.orders.place_conditional_trigger(request)

    def modify_conditional_trigger(self, alert_id: str, request: Any) -> Any:
        return self.orders.modify_conditional_trigger(alert_id, request)

    def delete_conditional_trigger(self, alert_id: str) -> bool:
        return self.orders.delete_conditional_trigger(alert_id)

    def get_conditional_trigger(self, alert_id: str) -> Any:
        return self.orders.get_conditional_trigger(alert_id)

    def get_all_conditional_triggers(self) -> list[Any]:
        return self.orders.get_all_conditional_triggers()

    # ── Account capabilities (delegated) ─────────────────────────────

    def get_ledger(self, from_date: str, to_date: str) -> list[Any]:
        return self.account.get_ledger(from_date, to_date)

    def get_user_profile(self) -> Any:
        return self.account.get_user_profile()

    def set_ip(self, ip_address: str, ip_type: str) -> dict:
        return self.account.set_ip(ip_address, ip_type)

    def modify_ip(self, ip_address: str, ip_type: str) -> dict:
        return self.account.modify_ip(ip_address, ip_type)

    def get_ip(self) -> list[Any]:
        return self.account.get_ip()

    def generate_tpin(self) -> dict:
        return self.account.generate_tpin()

    def authorize_edis(self, isin: str, quantity: int, exchange: str) -> dict:
        return self.account.authorize_edis(isin, quantity, exchange)

    def check_edis_status(self, isin: str) -> dict:
        return self.account.check_edis_status(isin)

    # ── Position capabilities (delegated) ────────────────────────────

    def get_positions(self) -> list[Any]:
        return self.positions.get_positions()

    def get_holdings(self) -> list[Any]:
        return self.positions.get_holdings()

    def get_balance(self) -> Any:
        return self.positions.get_balance()

    def exit_all(self) -> Any:
        return self.positions.exit_all()

    def convert_position(
        self,
        symbol: str,
        *,
        exchange: str = "NSE",
        quantity: int,
        from_product_type: str,
        to_product_type: str,
        position_type: str = "LONG",
        security_id: str | None = None,
    ) -> dict[str, Any]:
        return self.positions.convert_position(
            symbol,
            exchange=exchange,
            quantity=quantity,
            from_product_type=from_product_type,
            to_product_type=to_product_type,
            position_type=position_type,
            security_id=security_id,
        )

    def configure_pnl_exit(
        self,
        *,
        profit_value: Any = None,
        loss_value: Any = None,
        product_types: list[str] | None = None,
        enable_kill_switch: bool = False,
    ) -> Any:
        return self.positions.configure_pnl_exit(
            profit_value=profit_value,
            loss_value=loss_value,
            product_types=product_types,
            enable_kill_switch=enable_kill_switch,
        )

    def stop_pnl_exit(self) -> Any:
        return self.positions.stop_pnl_exit()

    def get_pnl_exit(self) -> Any:
        return self.positions.get_pnl_exit()

    # ── Data capabilities (delegated) ────────────────────────────────

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        return self.data.get_expiries(underlying, exchange)

    def get_option_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        return self.data.get_option_expiries(underlying, exchange)

    def get_expired_options_data(
        self,
        security_id: int,
        expiry_flag: str,
        expiry_code: int,
        strike: str,
        option_type: str,
        from_date: str,
        to_date: str,
        required_data: list[str] | None = None,
        interval: int = 1,
    ) -> dict:
        return self.data.get_expired_options_data(
            security_id=security_id,
            expiry_flag=expiry_flag,
            expiry_code=expiry_code,
            strike=strike,
            option_type=option_type,
            from_date=from_date,
            to_date=to_date,
            required_data=required_data,
            interval=interval,
        )

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict:
        return self.data.get_option_chain(underlying, exchange, expiry)

    def get_futures_contracts(self, underlying: str, exchange: str = "NFO") -> list[dict]:
        return self.data.get_futures_contracts(underlying, exchange)

    def get_futures_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        return self.data.get_futures_expiries(underlying, exchange)

    def is_commodity(self, symbol: str) -> bool:
        return self.data.is_commodity(symbol)

    def validate_order(self, **kwargs: Any) -> list[str]:
        return self.data.validate_order(**kwargs)

    def get_alerts(self) -> list[Any]:
        return self.data.get_alerts()
