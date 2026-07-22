"""ProcessKernel — sole composition root (ADR-0015 / WS-G).

New code should call :meth:`ProcessKernel.wire` or :meth:`ProcessKernel.boot`.
``runtime.factory`` remains a compatibility shim for ``build`` /
``build_from_broker_service`` until callers migrate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from runtime.composition import create_api_event_bus, wire_domain_port_sinks
from runtime.paper_session import PaperSession, build_paper_session
from runtime.wire_runtime_hooks import wire_runtime_hooks


class ProcessKernel:
    """Single process composition entry — wires sinks + hooks once, then delegates."""

    @staticmethod
    def wire() -> None:
        """Register domain port sinks and runtime hooks (idempotent)."""
        wire_domain_port_sinks()
        wire_runtime_hooks()

    @staticmethod
    def boot(mode: str, **kwargs: Any) -> Any:
        """Wire once, then build the runtime for ``mode``.

        Modes: ``api``, ``cli``, ``paper``, ``trade``.
        """
        ProcessKernel.wire()
        normalized = (mode or "").lower().strip()
        if normalized == "api":
            from runtime.api_compose import build_for_api

            return build_for_api(**kwargs)
        if normalized == "cli":
            from interface.ui.services.compose import build_runtime

            return build_runtime(**kwargs)
        if normalized == "paper":
            return bootstrap_platform(**kwargs)
        if normalized == "trade":
            broker_service = kwargs.pop("broker_service", None)
            if broker_service is None:
                raise ValueError("broker_service is required for ProcessKernel.boot('trade')")
            from runtime.factory import build

            return build(broker_service, mode="trade", **kwargs)
        raise ValueError(f"Unknown ProcessKernel boot mode: {mode!r}")

    @staticmethod
    def build_connect_oms(
        execution_provider: Any,
        *,
        event_bus: Any | None = None,
        broker_id: str = "paper",
        processed_trade_repository: Any | None = None,
    ) -> Any:
        """Minimal safe OMS for ``tradex.connect`` when no BrokerService is present.

        Paper/datalake may build an in-memory OMS; live brokers fail closed via
        ``build_oms_service`` (ENG-001).
        """
        ProcessKernel.wire()
        if event_bus is None:
            from infrastructure.bootstrap import build_event_bus
            from infrastructure.event_bus.processed_trade_repository import (
                ProcessedTradeRepository,
            )

            event_bus = build_event_bus()
            if processed_trade_repository is None:
                processed_trade_repository = ProcessedTradeRepository()

        from application.oms.session_bridge import build_oms_service

        return build_oms_service(
            execution_provider,
            event_bus=event_bus,
            broker_id=broker_id,
            processed_trade_repository=processed_trade_repository,
        )


def bootstrap_platform(
    total_capital: Decimal = Decimal("1000000.00"),
    gateway: Any = None,
) -> PaperSession:
    """Bootstrap a wired paper session with TradingContext + ExecutionEngine."""
    ProcessKernel.wire()
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
    "ProcessKernel",
    "Runtime",
    "bootstrap_platform",
    "build",
    "build_from_broker_service",
    "build_multi_strategy_runtime",
    "build_paper_session",
    "create_api_event_bus",
    "wire_domain_port_sinks",
]
