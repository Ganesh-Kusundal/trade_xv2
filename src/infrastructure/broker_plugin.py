"""BrokerPlugin — thin composition metadata per broker (UX-2).

Brokers self-register at package import. ``open_session`` reads plugins
instead of hard-coding broker ifs for defaults / env files / live flags.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BrokerPlugin:
    """Composition-root metadata for one broker id."""

    broker_id: str
    env_file: str | None = None
    default_mode: str = "market"  # sim | market | trade
    supported_modes: frozenset[str] = field(default_factory=lambda: frozenset({"market", "trade"}))
    is_live: bool = True
    # Optional factories (gateway via bootstrap_gateway / require_gateway)
    data_provider_factory: Callable[[Any], Any] | None = None
    execution_provider_factory: Callable[[Any], Any] | None = None
    # Capability declaration (DR-B3): the broker supplies a callable that
    # returns its ``BrokerCapabilities``.  The resilience layer calls this
    # directly instead of hard-coding broker names or doing importlib magic.
    capabilities_loader: Callable[[], Any] | None = None


_PLUGINS: dict[str, BrokerPlugin] = {}


def register_broker_plugin(plugin: BrokerPlugin) -> None:
    _PLUGINS[plugin.broker_id.lower().strip()] = plugin


def get_broker_plugin(broker_id: str) -> BrokerPlugin | None:
    return _PLUGINS.get((broker_id or "").lower().strip())


def list_broker_plugins() -> list[BrokerPlugin]:
    return list(_PLUGINS.values())


def ensure_core_plugins() -> None:
    """Idempotent defaults if packages have not registered yet.

    ``tradex/session.py`` calls this before any concrete broker package is
    guaranteed to have been imported (a fresh process calling
    ``tradex.connect("dhan")`` for the first time may reach here before
    anything else has imported ``brokers.dhan``), so this cannot simply
    defer to each broker's real self-registration
    (``brokers/{dhan,upstox,paper}/__init__.py`` all call
    ``register_broker_plugin`` themselves at import time) — that was tried
    and reverted: importing the broker packages from here transitively
    pulls in ``application.oms.*`` (historically ``brokers.dhan.portfolio
    .reconciliation``; engine now lives in ``domain.reconciliation_engine``)
    and breaks
    two real import-linter contracts (``Infrastructure independence``,
    ``Tradex public API broker isolation``). Duplicating the metadata here
    is the architecturally correct choice, not an oversight — it trades a
    (currently harmless, since the values match) risk of the two copies
    drifting apart for not letting ``infrastructure``/``tradex`` depend on
    concrete broker packages, which matters more. If this ever needs
    revisiting, the metadata itself (not the import graph) is where a
    single-source-of-truth fix belongs — e.g. a static registry module
    that both the broker packages and this fallback import, containing no
    business logic of its own.
    """
    if "paper" not in _PLUGINS:
        register_broker_plugin(
            BrokerPlugin(
                broker_id="paper",
                env_file=None,
                default_mode="sim",
                supported_modes=frozenset({"sim", "market", "trade"}),
                is_live=False,
            )
        )
    if "dhan" not in _PLUGINS:
        register_broker_plugin(
            BrokerPlugin(
                broker_id="dhan",
                env_file=".env.local",
                default_mode="market",
                supported_modes=frozenset({"market", "trade"}),
                is_live=True,
                capabilities_loader=None,  # broker __init__.py fills this
            )
        )
    if "upstox" not in _PLUGINS:
        register_broker_plugin(
            BrokerPlugin(
                broker_id="upstox",
                env_file=".env.upstox",
                default_mode="market",
                supported_modes=frozenset({"market", "trade"}),
                is_live=True,
                capabilities_loader=None,  # broker __init__.py fills this
            )
        )
    if "datalake" not in _PLUGINS:
        register_broker_plugin(
            BrokerPlugin(
                broker_id="datalake",
                env_file=None,
                default_mode="market",
                supported_modes=frozenset({"market"}),
                is_live=False,
            )
        )
