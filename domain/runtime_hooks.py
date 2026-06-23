"""Runtime hooks registered at composition root (no broker imports in domain)."""

from __future__ import annotations

from typing import Any, Callable

_oms_backtest_factory: Callable[..., Any] | None = None
_domain_event_factory: Callable[..., Any] | None = None


def register_oms_backtest_factory(factory: Callable[..., Any]) -> None:
    """Register factory used by analytics engines when ``trading_context`` is set."""
    global _oms_backtest_factory
    _oms_backtest_factory = factory


def register_domain_event_factory(factory: Callable[..., Any]) -> None:
    global _domain_event_factory
    _domain_event_factory = factory


def create_oms_backtest_adapter(trading_context: Any, **kwargs: Any) -> Any:
    if _oms_backtest_factory is None:
        raise RuntimeError(
            "OMS backtest factory not registered. "
            "Call register_oms_backtest_factory() at application startup."
        )
    return _oms_backtest_factory(trading_context, **kwargs)


def create_domain_event(**kwargs: Any) -> Any:
    if _domain_event_factory is None:
        raise RuntimeError("Domain event factory not registered.")
    return _domain_event_factory(**kwargs)


_trading_context_factory: Callable[..., Any] | None = None


def register_trading_context_factory(factory: Callable[..., Any]) -> None:
    global _trading_context_factory
    _trading_context_factory = factory


def create_trading_context(**kwargs: Any) -> Any:
    if _trading_context_factory is None:
        raise RuntimeError(
            "Trading context factory not registered. "
            "Call register_trading_context_factory() at application startup."
        )
    return _trading_context_factory(**kwargs)


__all__ = [
    "create_domain_event",
    "create_oms_backtest_adapter",
    "create_trading_context",
    "register_domain_event_factory",
    "register_oms_backtest_factory",
    "register_trading_context_factory",
]
