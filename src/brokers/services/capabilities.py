"""Capability services — introspect a broker's feature matrix and extensions."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from brokers.session import BrokerSession

from ._session import _borrow_session


def _session_gateway(session: BrokerSession) -> Any | None:
    """Resolve the wire gateway from a BrokerSession (internal)."""
    provider = session.provider
    return getattr(provider, "gateway", None)


def _cap_value(value: Any) -> Any:
    """JSON-safe conversion for capability matrix values."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, frozenset):
        if not value:
            return []
        sample = next(iter(value))
        if hasattr(sample, "__dataclass_fields__"):
            return [_cap_value(v) for v in value]
        return [str(v) for v in value]
    if isinstance(value, tuple):
        return [_cap_value(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return {k: _cap_value(getattr(value, k)) for k in value.__dataclass_fields__}
    if hasattr(value, "value"):  # Enum
        return value.value
    return str(value)


def _caps_to_dict(caps: Any) -> dict[str, Any]:
    if caps is None:
        return {}
    return {f.name: _cap_value(getattr(caps, f.name)) for f in fields(caps)}


def format_session_capabilities(session: BrokerSession, symbol: str = "RELIANCE") -> dict[str, Any]:
    """Full capability payload: matrix + extension names + market surfaces."""
    extensions = session.stock(symbol).capabilities()
    matrix: dict[str, Any] = {}
    gw = _session_gateway(session)
    if gw is not None:
        caps_fn = getattr(gw, "capabilities", None)
        if callable(caps_fn):
            matrix = _caps_to_dict(caps_fn())
        else:
            list_fn = getattr(gw, "list_capabilities", None)
            if callable(list_fn):
                desc = list_fn()
                matrix = _caps_to_dict(getattr(desc, "capabilities", desc))
    return {
        "broker_id": session.broker_id,
        "matrix": matrix,
        "extensions": extensions,
        "market_surfaces": matrix.get("market_surfaces", []),
    }


def get_capabilities(
    broker: str,
    symbol: str = "RELIANCE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return format_session_capabilities(s, symbol)
    finally:
        if close:
            s.close()


__all__ = [
    "_cap_value",
    "_caps_to_dict",
    "_session_gateway",
    "format_session_capabilities",
    "get_capabilities",
]
