"""Broker plugin discovery via the ``tradex.brokers`` entry-point group.

Composition root (``runtime/``): the one place allowed to import concrete
broker packages by name. This is the piece that was missing to make
"add a broker" a true out-of-tree plugin operation rather than requiring
the new broker's package to already be reachable from this repository's
own import graph (see
docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART4.md §3.2).

``infrastructure/broker_plugin.py``'s ``ensure_core_plugins()`` remains the
in-tree fallback for the three built-in brokers (paper, dhan, upstox) and
deliberately still hardcodes their metadata rather than importing them —
that was tried here and reverted (see that module's docstring and task #10
in this session's history) because ``infrastructure``/``tradex`` must not
depend on concrete broker packages, per two real import-linter contracts.
This module is different: it lives in ``runtime/``, which import-linter
already permits to import brokers, precisely because a composition root
is the one place structurally allowed to do so.

Entry points are module-only targets (``dhan = "brokers.dhan"``, not
``dhan = "brokers.dhan:DhanBroker"``) because each broker package already
self-registers via ``register_broker_plugin()`` etc. at import time —
discovery's job is just "import this module," not "instantiate this
class."
"""

from __future__ import annotations

import importlib
import logging
from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "tradex.brokers"


def discover_broker_plugins() -> list[str]:
    """Import every broker package registered under the ``tradex.brokers``
    entry-point group, triggering each one's self-registration.

    Returns the list of broker ids successfully discovered and imported.
    A single broker's import failure is logged and skipped rather than
    aborting discovery for the others — one broken third-party plugin
    must not prevent the built-in brokers (or other third-party plugins)
    from loading.
    """
    discovered: list[str] = []
    for ep in entry_points(group=_ENTRY_POINT_GROUP):
        try:
            importlib.import_module(ep.value)
        except Exception:
            logger.warning(
                "broker_plugin_discovery_failed",
                # "module" is a reserved LogRecord attribute name -- using
                # it here raises KeyError: "Attempt to overwrite 'module'
                # in LogRecord" at log time, not at test-write time, so
                # this was only caught by actually exercising the failure
                # path in a test.
                extra={"broker_id": ep.name, "broker_module": ep.value},
                exc_info=True,
            )
            continue
        discovered.append(ep.name)
    return discovered


def ensure_broker_module(broker_id: str) -> bool:
    """Import a single broker package by id via the ``tradex.brokers`` entry-point group.

    Triggers the package's self-registration side effects (each broker package
    calls ``register_broker_plugin()`` at import time) without any layer above
    ``infrastructure``/``brokers`` naming the concrete module.

    This is the sanctioned composition-root import path for layers that only
    need a broker package imported for its registration side effects (e.g.
    ``tradex.Session`` ensuring a broker is registered before use). Returns
    ``True`` if the broker was found and imported, ``False`` otherwise.
    """
    for ep in entry_points(group=_ENTRY_POINT_GROUP):
        if ep.name == broker_id:
            try:
                importlib.import_module(ep.value)
            except Exception:
                logger.warning(
                    "broker_plugin_import_failed",
                    extra={"broker_id": broker_id, "broker_module": ep.value},
                    exc_info=True,
                )
                return False
            return True
    return False


__all__ = ["discover_broker_plugins", "ensure_broker_module"]
