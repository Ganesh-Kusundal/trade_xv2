"""Backward-compat facade — canonical: application/streaming/candle_aggregator.py"""

from tradex.runtime._deprecation import warn_facade
warn_facade(__name__, "application.streaming.candle_aggregator")
from application.streaming.candle_aggregator import *  # noqa
