"""Session factory — builds a ``BrokerSession`` from a broker id.

Reuses the existing plugin registry + entry-point discovery so adding a broker
is purely additive (a new plugin package that self-registers). No central
switch statement lives here.
"""

from __future__ import annotations

from typing import Any

from brokers.session.broker_session import BrokerSession
from infrastructure.broker_plugin import (
    get_broker_plugin,
    list_broker_plugins,
)


def available_brokers() -> list[str]:
    """Broker ids currently registered (built-in + discovered plugins)."""
    from infrastructure.broker_plugin import ensure_core_plugins

    ensure_core_plugins()
    try:
        from runtime.broker_discovery import discover_broker_plugins

        discover_broker_plugins()
    except Exception:
        pass
    return [p.broker_id for p in list_broker_plugins()]


def create_session(broker: str = "paper", **kwargs: Any) -> BrokerSession:
    """Create a :class:`BrokerSession` for ``broker``.

    Raises
    ------
    ValueError
        If the broker id is unknown (no registered plugin).
    """
    broker_id = (broker or "paper").lower().strip()
    if get_broker_plugin(broker_id) is None:
        from infrastructure.broker_plugin import ensure_core_plugins

        ensure_core_plugins()
    if get_broker_plugin(broker_id) is None:
        raise ValueError(
            f"Unknown broker {broker_id!r}. Available: {', '.join(available_brokers()) or 'none'}"
        )
    return BrokerSession(broker_id, **kwargs)
