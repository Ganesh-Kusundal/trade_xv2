"""Interface composition wiring — BrokerService factory registration."""

from __future__ import annotations

from typing import Any, Callable

_BrokerServiceFactory: Callable[..., Any] | None = None
_wired = False


def register_broker_service_factory(factory: Callable[..., Any]) -> None:
    global _BrokerServiceFactory
    _BrokerServiceFactory = factory


def get_broker_service_factory() -> Callable[..., Any] | None:
    return _BrokerServiceFactory


def wire_interface_compose() -> None:
    """Register BrokerService factory + session openers (idempotent)."""
    global _wired
    if _wired:
        return

    from interface.ui.services.broker_service import BrokerService
    from runtime.api_compose import register_broker_service_factory as _register_api_factory
    from runtime.session_opener import set_session_opener as _set_runtime_opener

    register_broker_service_factory(BrokerService)
    _register_api_factory(BrokerService)

    def _open_session(*args: Any, **kwargs: Any) -> Any:
        from tradex.session import open_session

        return open_session(*args, **kwargs)

    _set_runtime_opener(_open_session)

    from application.portfolio.active_session import set_session_opener as _set_app_opener

    _set_app_opener(_open_session)
    _wired = True
