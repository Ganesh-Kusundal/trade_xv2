"""Sanctioned broker connect helpers for CLI / presentation layer.

All ``interface.ui.commands`` modules must use :func:`connect_live` or
:func:`connect_analytics` — never ``create_gateway`` or broker factories directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.ports.bootstrap import BootstrapResult
from infrastructure.gateway.factory import bootstrap_gateway, require_gateway


def connect_live(
    broker: str,
    *,
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any:
    """Live connect: auth probe + at most one remint; raises if not ready."""
    return require_gateway(
        broker,
        env_path=env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
    )


def connect_analytics(
    broker: str,
    *,
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> BootstrapResult:
    """Analytics connect: transport only, explicit skip of network auth probe."""
    return bootstrap_gateway(
        broker,
        env_path=env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
        skip_auth_probe=True,
    )


def try_connect_live(
    broker: str,
    *,
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    **kwargs: Any,
) -> Any | None:
    """Like :func:`connect_live` but returns ``None`` instead of raising."""
    try:
        return connect_live(
            broker,
            env_path=env_path,
            load_instruments=load_instruments,
            **kwargs,
        )
    except Exception:
        return None


__all__ = ["connect_analytics", "connect_live", "try_connect_live"]
