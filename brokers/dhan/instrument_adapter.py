"""Backward-compat shim — converters now live in ``brokers.dhan.data.instrument_adapter``."""
from brokers.dhan.data.instrument_adapter import from_instrument_id, to_instrument_id  # noqa: F401
