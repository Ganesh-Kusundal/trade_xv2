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
from typing import Any

from ._session import *  # noqa: F401,F403
from .capabilities import *  # noqa: F401,F403
from .instrument_lookup import *  # noqa: F401,F403
from .market_data import *  # noqa: F401,F403
from .operations import *  # noqa: F401,F403
from .orders import *  # noqa: F401,F403
from .portfolio import *  # noqa: F401,F403


def safe_serialize(obj: object) -> object:
    """Best-effort JSON-safe view of a domain object."""
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    snap = getattr(obj, "snapshot", None)
    if callable(snap):
        return safe_serialize(snap())
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return safe_serialize(to_dict())
    if is_dataclass(obj):
        return {k: safe_serialize(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {k: safe_serialize(v) for k, v in vars(obj).items() if not k.startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [safe_serialize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items()}
    return obj


__all__ = [
    "safe_serialize",
    "_open",
    "_borrow_session",
    "status_from_session",
    "extensions_from_session",
    "run_connect",
    "get_quote",
    "get_history",
    "run_subscribe_probe",
    "get_depth",
    "get_depth30",
    "probe_depth_ws",
    "get_option_chain",
    "get_positions",
    "get_holdings",
    "get_funds",
    "get_orders",
    "_session_gateway",
    "_cap_value",
    "_caps_to_dict",
    "format_session_capabilities",
    "get_capabilities",
    "lookup_instrument",
    "lookup_security",
    "lookup_symbol",
    "get_news",
    "list_super_orders",
    "list_forever_orders",
    "place_order",
    "cancel_order",
    "modify_order",
    "run_mapping",
    "run_market_hours",
    "run_certify",
    "run_diagnose",
    "run_doctor",
    "run_health",
    "run_benchmark",
    "VerifyStep",
    "VerifyReport",
    "run_verify",
]
