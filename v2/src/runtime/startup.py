"""Startup sequence — initialize/start lifecycle; freeze environment."""

from __future__ import annotations

import logging
from dataclasses import replace

from config.schema import Environment
from runtime.runtime import Runtime
from shared.errors import LifecycleError

_log = logging.getLogger(__name__)


def boot(runtime: Runtime) -> Runtime:
    """initialize_all → start_all; LIVE authenticate; abort if risk unbound; freeze."""
    if runtime.risk is None:
        raise LifecycleError("boot aborted: risk not bound")
    if runtime.environment_frozen:
        raise LifecycleError("boot aborted: environment already frozen")

    if runtime.environment is Environment.LIVE:
        adapter = runtime.broker_adapter
        if adapter is None:
            raise LifecycleError("boot aborted: LIVE requires broker_adapter")
        connect = getattr(adapter, "connect", None)
        if connect is not None:
            connect()
        auth = getattr(adapter, "authenticate", None)
        if auth is None or not auth():
            raise LifecycleError("boot aborted: LIVE authenticate() failed")
        load = getattr(adapter, "load_instruments", None)
        if load is not None:
            try:
                load()
            except Exception as exc:
                # ponytail: instrument master CDN often flaky; auth+funds is the connect gate
                _log.warning("load_instruments failed (continuing): %s", exc)

    runtime.lifecycle.initialize_all()
    runtime.lifecycle.start_all()
    return replace(runtime, environment_frozen=True)
