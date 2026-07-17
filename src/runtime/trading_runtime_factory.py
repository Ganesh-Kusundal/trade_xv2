"""Deprecated — re-export from ``runtime.factory`` for backward compatibility.

All wiring logic now lives in :mod:`runtime.factory`.  This module re-exports
``Runtime`` and ``TradingRuntimeFactory`` so existing imports don't break.
Remove this file once zero call sites reference it.
"""

from __future__ import annotations

import warnings
from typing import Any

from runtime.factory import (  # noqa: F401 — re-exports
    BuildOptions,
    Runtime,
    build,
    build_from_broker_service,
)


class TradingRuntimeFactory:
    """Deprecated — use :func:`runtime.factory.build` instead."""

    def __init__(self, **kwargs: Any) -> None:
        warnings.warn(
            "TradingRuntimeFactory is deprecated; use runtime.factory.build()",
            DeprecationWarning,
            stacklevel=2,
        )
        self._opts = BuildOptions(**kwargs)

    def build_from_broker_service(self, broker_service: Any) -> Runtime:
        return build_from_broker_service(broker_service, options=self._opts)
