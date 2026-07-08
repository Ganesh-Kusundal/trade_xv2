"""Instrument Aggregate — deprecated, use domain.instruments.instrument.Instrument instead.

This module is kept for backward compatibility.
InstrumentAggregate is now an alias for Instrument, which has absorbed
the thread-safety and extension features from the aggregate.
"""

from __future__ import annotations

import warnings

from domain.instruments.instrument import Instrument

warnings.warn(
    "domain.aggregates.instrument.InstrumentAggregate is deprecated; "
    "use 'from domain.instruments.instrument import Instrument' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Backward-compatible alias
InstrumentAggregate = Instrument

__all__ = ["InstrumentAggregate"]
