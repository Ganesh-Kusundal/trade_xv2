"""Shared broker operations — single code path for SDK, CLI, MCP, self-test.

This module is now a thin backward-compatibility facade. The actual
implementations live in the focused submodules under ``brokers.services``:

- ``_session``          — session open/borrow/status helpers
- ``market_data``       — quotes, history, depth, subscription probes
- ``portfolio``         — positions, holdings, funds, orders
- ``capabilities``      — capability matrix + extension introspection
- ``instrument_lookup`` — symbol → instrument metadata
- ``orders``            — order placement/cancellation plus news & order lists
- ``operations``        — certification, diagnostics, health, self-test

All public names remain importable from ``brokers.services.core``.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from ._session import (
    _borrow_session,
    _open,
    extensions_from_session,
    run_connect,
    status_from_session,
)
from .capabilities import (
    _cap_value,
    _caps_to_dict,
    _session_gateway,
    format_session_capabilities,
    get_capabilities,
)
from .instrument_lookup import (
    lookup_instrument,
    lookup_security,
    lookup_symbol,
)
from .market_data import (
    get_depth,
    get_depth30,
    get_history,
    get_history_batch,
    get_option_chain,
    get_quote,
    probe_depth_ws,
    run_subscribe_probe,
)
from .operations import (
    VerifyReport,
    VerifyStep,
    run_benchmark,
    run_certify,
    run_diagnose,
    run_doctor,
    run_health,
    run_mapping,
    run_market_hours,
    run_verify,
)
from .orders import (
    cancel_order,
    get_news,
    list_forever_orders,
    list_super_orders,
    modify_order,
    place_order,
)
from .portfolio import (
    get_funds,
    get_holdings,
    get_orders,
    get_positions,
)


def safe_serialize(obj: object, *, _depth: int = 0, max_depth: int = 10) -> object:
    """Best-effort JSON-safe view of a domain object.

    *max_depth* caps recursion to prevent stack overflow on circular references.
    Objects beyond the limit are replaced with their type name.
    """
    if _depth > max_depth:
        return f"<{type(obj).__name__}>"
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    snap = getattr(obj, "snapshot", None)
    if callable(snap):
        return safe_serialize(snap(), _depth=_depth + 1, max_depth=max_depth)
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return safe_serialize(to_dict(), _depth=_depth + 1, max_depth=max_depth)
    if is_dataclass(obj):
        return {
            k: safe_serialize(v, _depth=_depth + 1, max_depth=max_depth)
            for k, v in asdict(obj).items()
        }
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {
            k: safe_serialize(v, _depth=_depth + 1, max_depth=max_depth)
            for k, v in vars(obj).items()
            if not k.startswith("_")
        }
    if isinstance(obj, list | tuple):
        return [safe_serialize(v, _depth=_depth + 1, max_depth=max_depth) for v in obj]
    if isinstance(obj, dict):
        return {
            k: safe_serialize(v, _depth=_depth + 1, max_depth=max_depth) for k, v in obj.items()
        }
    return obj


__all__ = [
    "VerifyReport",
    "VerifyStep",
    "_borrow_session",
    "_cap_value",
    "_caps_to_dict",
    "_open",
    "_session_gateway",
    "cancel_order",
    "extensions_from_session",
    "format_session_capabilities",
    "get_capabilities",
    "get_depth",
    "get_depth30",
    "get_funds",
    "get_history",
    "get_history_batch",
    "get_holdings",
    "get_news",
    "get_option_chain",
    "get_orders",
    "get_positions",
    "get_quote",
    "list_forever_orders",
    "list_super_orders",
    "lookup_instrument",
    "lookup_security",
    "lookup_symbol",
    "modify_order",
    "place_order",
    "probe_depth_ws",
    "run_benchmark",
    "run_certify",
    "run_connect",
    "run_diagnose",
    "run_doctor",
    "run_health",
    "run_mapping",
    "run_market_hours",
    "run_subscribe_probe",
    "run_verify",
    "safe_serialize",
    "status_from_session",
]
