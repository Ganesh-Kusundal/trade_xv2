"""RuntimeKernel — sole composition root (ADR-0015).

New code should import from ``runtime.kernel``. ``runtime.factory`` remains a
compatibility shim for ``build`` / ``build_from_broker_service`` until callers migrate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from runtime.composition import create_api_event_bus, wire_domain_port_sinks
from runtime.paper_session import PaperSession, build_paper_session


def bootstrap_platform(
    total_capital: Decimal = Decimal("1000000.00"),
    gateway: Any = None,
) -> PaperSession:
    """Bootstrap a wired paper session with TradingContext + ExecutionEngine."""
    return build_paper_session(initial_capital=total_capital, gateway=gateway)


from runtime.factory import (  # noqa: E402
    BuildOptions,
    MultiStrategyRuntime,
    Runtime,
    build,
    build_from_broker_service,
    build_multi_strategy_runtime,
)

__all__ = [
    "BuildOptions",
    "MultiStrategyRuntime",
    "PaperSession",
    "Runtime",
    "bootstrap_platform",
    "build",
    "build_from_broker_service",
    "build_multi_strategy_runtime",
    "build_paper_session",
    "create_api_event_bus",
    "wire_domain_port_sinks",
]
