"""Backward-compat facade — canonical: application/streaming/orchestrator.py"""
from application.streaming.orchestrator import *  # noqa
from application.streaming.tick_router import _parse_exchange_time  # re-export (private name, not in *)
