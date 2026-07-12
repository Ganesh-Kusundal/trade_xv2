"""Exchange registry — datalake's access point for the active exchange adapter.

ADR-005 / P5-2 (G3). The datalake reads exchange conventions ONLY through this
module, never from hardcoded constants. At startup, ``discover_exchanges()``
is called to load exchange plugins from the ``tradex.exchanges`` entry-point
group. Until an adapter is registered, :func:`get_active_adapter` raises
:class:`ExchangeNotConfigured`.
"""

from __future__ import annotations

import importlib
import logging
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from domain.exceptions import ExchangeNotConfigured

if TYPE_CHECKING:
    from domain.ports.exchange_adapter import ExchangeAdapter

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "tradex.exchanges"
_active_adapter: ExchangeAdapter | None = None
_discovered = False


def set_active_adapter(adapter: ExchangeAdapter) -> None:
    """Register the active exchange adapter (called by runtime/ at startup)."""
    global _active_adapter
    _active_adapter = adapter


def get_active_adapter() -> ExchangeAdapter:
    """Return the active exchange adapter.

    Raises :class:`ExchangeNotConfigured` if no adapter has been registered.
    """
    if _active_adapter is None and not _discovered:
        discover_exchanges()
    if _active_adapter is None:
        raise ExchangeNotConfigured(
            "No exchange adapter registered. Install an exchange plugin "
            "(e.g. ``pip install tradex[NSE]``) or call set_active_adapter()."
        )
    return _active_adapter


def get_active_exchange_code() -> str:
    """Shorthand: return the canonical exchange code (e.g. ``'NSE'``)."""
    return get_active_adapter().exchange


def discover_exchanges() -> list[str]:
    """Import every exchange package registered under ``tradex.exchanges``.

    Each exchange plugin module must expose a module-level ``ADAPTER``
    (an :class:`ExchangeAdapter` instance) and a ``CALENDAR``
    (a :class:`TradingCalendar` instance). The first discovered adapter
    becomes the active one.

    Returns the list of successfully discovered exchange ids.
    """
    global _active_adapter, _discovered
    _discovered = True
    discovered: list[str] = []
    for ep in entry_points(group=_ENTRY_POINT_GROUP):
        try:
            mod = importlib.import_module(ep.value)
        except Exception:
            logger.warning(
                "exchange_plugin_discovery_failed",
                extra={"exchange_id": ep.name, "exchange_module": ep.value},
                exc_info=True,
            )
            continue
        adapter = getattr(mod, "ADAPTER", None)
        if adapter is not None and _active_adapter is None:
            _active_adapter = adapter
            logger.info("exchange_plugin_loaded", extra={"exchange": adapter.exchange})
        discovered.append(ep.name)
    return discovered
