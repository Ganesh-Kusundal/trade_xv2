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
    """30-level depth via the canonical ``depth_30`` extension (Upstox)."""
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        ext = inst.get_extension("depth_30") if hasattr(inst, "get_extension") else None
        if ext is None:
            raise RuntimeError(f"broker {broker!r} does not expose the depth_30 extension")
        full = getattr(ext, "full_depth", None)
        if not callable(full):
            raise RuntimeError(f"broker {broker!r} depth_30 extension has no full_depth()")
        return full()
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
    """Probe WS depth via the canonical depth extension; REST depth as fallback.

    Resolves the broker's depth extension by canonical level name
    (``depth_200`` / ``depth_30`` / ``depth_20``) so Dhan's 20/200-level feeds
    and Upstox's 30-level feed are reached identically — no raw
    ``depth20`` / ``depth_200`` facade-name guessing.
    """
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        # Most-specific canonical extension name at or above the requested level.
        # get_extension() already binds the extension to this instrument.
        for threshold, ext_name in ((200, "depth_200"), (30, "depth_30"), (20, "depth_20")):
            if levels >= threshold:
                ext = inst.get_extension(ext_name) if hasattr(inst, "get_extension") else None
                if ext is not None:
                    full = getattr(ext, "full_depth", None)
                    if callable(full):
                        return full()
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
