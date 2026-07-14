"""Runtime hooks registered at composition root (no broker imports in domain).

Module-level mutable globals replaced by frozen ``RuntimeHooks`` dataclass.
New code should use ``set_runtime_hooks(hooks)`` for dependency injection;
legacy ``register_*`` / ``create_*`` functions delegate to the module singleton
for backward compatibility.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class RuntimeHooks:
    """Immutable container for runtime factory callables.

    Use :func:`set_runtime_hooks` to register all factories at once
    from the composition root. Legacy callers can continue using the
    individual ``register_*`` functions.

    NOTE: the ``trading_context`` factory is intentionally NOT here — domain
    must not own a wiring concern. Analytics obtains it via
    ``runtime.replay_factory`` (composition root), preserving the
    analytics -> application.oms layering boundary. See audit REF-6.
    """

    oms_backtest_factory: Callable[..., Any] | None = None
    domain_event_factory: Callable[..., Any] | None = None


# ── Module singleton (backward-compatible) ──────────────────────────────
# All registrations happen at application startup; no concurrent callers.

_runtime_hooks = RuntimeHooks()


def set_runtime_hooks(hooks: RuntimeHooks) -> None:
    """Replace the module-level runtime hooks (preferred for DI)."""
    global _runtime_hooks  # intentional module singleton — backward-compatible DI
    _runtime_hooks = hooks


def register_oms_backtest_factory(factory: Callable[..., Any]) -> None:
    """Register factory used by analytics engines when ``trading_context`` is set."""
    global _runtime_hooks  # intentional module singleton — backward-compatible DI
    _runtime_hooks = replace(_runtime_hooks, oms_backtest_factory=factory)


def register_domain_event_factory(factory: Callable[..., Any]) -> None:
    """Register factory for creating domain events from analytics engines."""
    global _runtime_hooks  # intentional module singleton — backward-compatible DI
    _runtime_hooks = replace(_runtime_hooks, domain_event_factory=factory)


def create_oms_backtest_adapter(trading_context: Any, **kwargs: Any) -> Any:
    """Create an OMS backtest adapter via the registered factory."""
    if _runtime_hooks.oms_backtest_factory is None:
        raise RuntimeError(
            "OMS backtest factory not registered. "
            "Call register_oms_backtest_factory() at application startup."
        )
    return _runtime_hooks.oms_backtest_factory(trading_context, **kwargs)


def create_domain_event(**kwargs: Any) -> Any:
    """Create a domain event via the registered factory."""
    if _runtime_hooks.domain_event_factory is None:
        raise RuntimeError("Domain event factory not registered.")
    return _runtime_hooks.domain_event_factory(**kwargs)


__all__ = [
    "RuntimeHooks",
    "create_domain_event",
    "create_oms_backtest_adapter",
    "register_domain_event_factory",
    "register_oms_backtest_factory",
    "set_runtime_hooks",
]
