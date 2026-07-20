"""Session — the composition root. Binds data, execution, and order service."""

from __future__ import annotations

import contextlib
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain._session_instruments import SessionInstrumentMixin
from domain._session_trading import SessionTradingMixin
from domain.ports.provider_registry import get_default_provider, set_default_provider
from domain.ports.session_context import (
    activate_session,
    clear_ambient_session_if_current,
    set_ambient_session,
)

if TYPE_CHECKING:
    from domain.ports.event_publisher import EventBusPort
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import DataProvider, ExecutionProvider


class Session(SessionTradingMixin, SessionInstrumentMixin):
    """Composition root. Binds data, optional execution, and order service (OMS)."""

    def __init__(
        self,
        provider: DataProvider,
        *,
        event_bus: EventBusPort | None = None,
        execution_provider: ExecutionProvider | None = None,
        order_service: OrderServicePort | None = None,
        status: Any | None = None,
    ) -> None:
        self._provider = provider
        self._event_bus = event_bus
        self._execution_provider = execution_provider
        self._order_service = order_service
        self._status = status
        self._account_view = None
        set_default_provider(provider)
        set_ambient_session(self)
        from domain.universe import Universe

        self._universe = Universe(
            provider,
            event_bus=event_bus,
            execution_provider=execution_provider,
            order_service=order_service,
        )

    @property
    def universe(self):
        return self._universe

    @property
    def provider(self) -> DataProvider:
        return self._provider

    @property
    def execution_provider(self) -> ExecutionProvider | None:
        return self._execution_provider

    @property
    def order_service(self) -> OrderServicePort | None:
        return self._order_service

    @property
    def event_bus(self) -> EventBusPort | None:
        return self._event_bus

    @property
    def status(self) -> Any | None:
        """Connect readiness (mode / phase / orders_enabled). Set by ``tradex.connect``."""
        return self._status

    def attach_status(self, status: Any) -> None:
        """Attach or replace session status (composition root only)."""
        self._status = status

    def describe(self) -> dict[str, Any]:
        """Stable session summary for CLI / logs."""
        if self._status is not None and hasattr(self._status, "describe"):
            return self._status.describe()
        return {
            "orders_enabled": self._order_service is not None,
            "has_execution": self._execution_provider is not None,
        }

    def attach_broker_facade(self, broker_id: str, extensions: list[Any]) -> None:
        """Wire typed broker capabilities onto instruments created from this session."""
        from domain.extensions.facade import BrokerFacade

        self._universe._broker_facade = BrokerFacade(broker_id, extensions)

    @property
    def account(self):
        """AccountView — positions / holdings / funds / Portfolio (no gateway)."""
        if not hasattr(self, "_account_view") or self._account_view is None:
            from domain.portfolio.account_view import AccountView

            self._account_view = AccountView(self._execution_provider)
        return self._account_view

    def orders(self) -> list[Any]:
        """Open/working orders from OMS book when available, else EP order book."""
        oms = self._order_service
        if oms is not None:
            mgr = getattr(oms, "order_manager", None)
            if mgr is not None:
                list_fn = getattr(mgr, "get_orders", None) or getattr(mgr, "list_orders", None)
                if callable(list_fn):
                    try:
                        return list(list_fn())
                    except TypeError:
                        return list(list_fn(include_terminal=False))
                if hasattr(mgr, "orders_map"):
                    orders_map = mgr.orders_map
                    if isinstance(orders_map, dict):
                        return list(orders_map.values())
        if self._execution_provider is not None:
            try:
                return list(self._execution_provider.get_order_book() or [])
            except Exception:
                return []
        return []

    def activate(self):
        """Nested-safe ambient activation (notebook multi-session)."""
        return activate_session(self)

    @property
    def dx(self) -> SessionDx:
        """Thin TradeHull-shaped aliases over this Session (optional DX layer)."""
        return SessionDx(self)

    def close(self) -> None:
        """Release default provider and ambient if still owned by this Session."""
        lifecycle = self._lifecycle if hasattr(self, "_lifecycle") else None
        if lifecycle is not None:
            try:
                stop = getattr(lifecycle, "stop_all", None)
                if callable(stop):
                    stop()
            except Exception:
                pass
            with contextlib.suppress(Exception):
                self._lifecycle = None
        recorder = self._session_recorder if hasattr(self, "_session_recorder") else None
        if recorder is not None:
            try:
                stop = getattr(recorder, "stop", None)
                if callable(stop):
                    stop()
            except Exception:
                pass
            with contextlib.suppress(Exception):
                self._session_recorder = None
        if get_default_provider() is self._provider:
            set_default_provider(None)
        clear_ambient_session_if_current(self)


class SessionDx:
    """Optional L1 DX facade — thin aliases, instrument OOP underneath."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_ltp_data(self, names: str | list[str] | tuple[str, ...]) -> dict[str, Decimal | None]:
        if isinstance(names, str):
            names = [names]
        return self._session.ltp_many(list(names))

    def get_quote_data(self, names: str | list[str] | tuple[str, ...]) -> dict[str, Any]:
        if isinstance(names, str):
            names = [names]
        return self._session.quote_many(list(names))

    def atm_strikes(self, underlying: str, expiry: int | date | str = 0):
        chain = self._session.option_chain(underlying, expiry=expiry)
        sel = chain.select_strikes("ATM")
        return sel.ce, sel.pe, sel.strike

    def otm_strikes(self, underlying: str, expiry: int | date | str = 0, steps: int = 1):
        chain = self._session.option_chain(underlying, expiry=expiry)
        sel = chain.select_strikes("OTM", steps=steps)
        return sel.ce, sel.pe, sel.ce_strike, sel.pe_strike

    def itm_strikes(self, underlying: str, expiry: int | date | str = 0, steps: int = 1):
        chain = self._session.option_chain(underlying, expiry=expiry)
        sel = chain.select_strikes("ITM", steps=steps)
        return sel.ce, sel.pe, sel.ce_strike, sel.pe_strike

    def resolve(self, name: str):
        return self._session.resolve(name)
