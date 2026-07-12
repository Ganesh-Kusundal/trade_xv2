"""Market data services — quotes, history, depth, and subscription probes."""

from __future__ import annotations

from typing import Any

from brokers.session import BrokerSession

from ._session import _borrow_session


def get_quote(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.stock(symbol, exchange=exchange).refresh()
    finally:
        if close:
            s.close()


def get_history(
    broker: str,
    symbol: str,
    *,
    timeframe: str = "1D",
    days: int = 5,
    exchange: str = "NSE",
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.history(s.stock(symbol, exchange=exchange), timeframe=timeframe, days=days)
    finally:
        if close:
            s.close()


def run_subscribe_probe(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> bool:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        handle = s.subscribe(inst)
        if handle is not None:
            s.unsubscribe(inst)
        return handle is not None
    finally:
        if close:
            s.close()


def get_depth(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.stock(symbol, exchange=exchange).depth()
    finally:
        if close:
            s.close()


def get_depth30(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    """Upstox 30-level depth via instrument.broker.depth30()."""
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        facade = getattr(inst, "broker", None)
        if facade is None:
            raise RuntimeError(f"broker {broker!r} has no instrument.broker facade")
        fn = getattr(facade, "depth30", None) or getattr(facade, "depth_30", None)
        if not callable(fn):
            raise RuntimeError(f"broker {broker!r} does not expose depth30")
        return fn()
    finally:
        if close:
            s.close()


def probe_depth_ws(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    levels: int = 20,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    """Probe WS depth extensions (20/200) when declared; REST depth as fallback."""
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        facade = getattr(inst, "broker", None)
        if facade is not None:
            if levels >= 200:
                fn = getattr(facade, "depth200", None) or getattr(facade, "depth_200", None)
                if callable(fn):
                    return fn()
            if levels >= 20:
                fn = getattr(facade, "depth20", None) or getattr(facade, "depth_20", None)
                if callable(fn):
                    return fn()
        return inst.depth()
    finally:
        if close:
            s.close()


def get_option_chain(
    broker: str,
    underlying: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.option_chain(underlying, exchange=exchange)
    finally:
        if close:
            s.close()


__all__ = [
    "get_quote",
    "get_history",
    "run_subscribe_probe",
    "get_depth",
    "get_depth30",
    "probe_depth_ws",
    "get_option_chain",
]
