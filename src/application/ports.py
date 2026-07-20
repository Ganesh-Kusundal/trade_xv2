"""Application-layer ports for runtime services.

Execution-target wiring injected at startup so application code does not
import ``runtime.*`` directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_resolve_execution_target: Callable[..., Any] | None = None
_resolve_simulated_oms_adapter: Callable[..., Any] | None = None


def set_execution_target_resolver(
    resolve_target: Callable[..., Any],
    resolve_sim_adapter: Callable[..., Any],
) -> None:
    global _resolve_execution_target, _resolve_simulated_oms_adapter
    _resolve_execution_target = resolve_target
    _resolve_simulated_oms_adapter = resolve_sim_adapter


def resolve_execution_target(*args: Any, **kwargs: Any) -> Any:
    if _resolve_execution_target is None:
        raise RuntimeError(
            "Execution target resolver not wired. "
            "Call application.ports.set_execution_target_resolver() from runtime."
        )
    return _resolve_execution_target(*args, **kwargs)


def resolve_simulated_oms_adapter(*args: Any, **kwargs: Any) -> Any:
    if _resolve_simulated_oms_adapter is None:
        raise RuntimeError(
            "Simulated OMS adapter factory not wired. "
            "Call application.ports.set_execution_target_resolver() from runtime."
        )
    return _resolve_simulated_oms_adapter(*args, **kwargs)


def run_coro_sync(*args: Any, **kwargs: Any) -> Any:
    """Backward-compatible re-export — prefer domain.ports.async_bridge."""
    from domain.ports.async_bridge import run_coro_sync as _run

    return _run(*args, **kwargs)
