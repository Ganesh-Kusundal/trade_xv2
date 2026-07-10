"""Backward-compat facade — canonical: application/streaming/orchestrator.py"""

from tradex.runtime._deprecation import warn_facade
warn_facade(__name__, "application.streaming.orchestrator")
from application.streaming.orchestrator import *  # noqa
from application.streaming.tick_router import _parse_exchange_time  # re-export (private name, not in *)
