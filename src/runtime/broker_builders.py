"""Gateway builder functions — composition root only.

Each builder creates a gateway for a specific broker. These live in
``runtime/`` (the one layer permitted concrete broker imports) and are
lazily imported by ``infrastructure.gateway.factory._ensure_default_builders``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def create_dhan_gateway(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    from brokers.dhan.identity.factory import BrokerFactory

    resolved = Path(env_path) if env_path is not None else None
    return BrokerFactory().create(
        env_path=resolved,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
    )


def create_upstox_gateway(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    from brokers.upstox.factory import UpstoxBrokerFactory

    resolved = Path(env_path) if env_path is not None else None
    return UpstoxBrokerFactory().create(
        env_path=resolved,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
    )


def create_paper_gateway(
    env_path: Path | None = None,
    **kwargs: Any,
) -> Any | None:
    from brokers.paper import PaperGateway

    return PaperGateway()


def create_datalake_gateway(
    env_path: Path | None = None,
    *,
    root: str | None = None,
    **kwargs: Any,
) -> Any | None:
    from datalake.gateway import DataLakeGateway

    return DataLakeGateway(root=root)
