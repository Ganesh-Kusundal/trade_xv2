"""Canonical constants for the broker-agnostic core.

**DEPRECATED**: This module now re-exports from ``brokers.common.core.constants/``
package. The monolithic constants.py has been split into focused sub-modules:

- ``constants/timeouts.py`` — Stop timeouts, HTTP timeouts, sleep intervals
- ``constants/resilience.py`` — Retry, circuit breaker, backoff configuration
- ``constants/auth.py`` — Token lifecycle and authentication constants
- ``constants/risk.py`` — Risk thresholds, position limits, capital defaults
- ``constants/market.py`` — Market hours, exchanges, tick sizes, timezone
- ``constants/observability.py`` — HTTP server configuration

All constants are re-exported here for backward compatibility. New code should
import directly from the sub-modules (e.g., ``from brokers.common.core.constants.timeouts import DEFAULT_STOP_TIMEOUT_SECONDS``).

Rules of use
------------
* Broker-specific segments live in the broker's own ``segments.py`` or
  ``segment_mapper.py`` (e.g. ``brokers/dhan/segments.py``,
  ``brokers/upstox/instruments/segment_mapper.py``).
* Wire-format exchange codes (the values brokers send on the wire) are
  re-exported from :mod:`brokers.common.core.exchange_segments` once that
  module is introduced. Until then, the *defaults* — the segments the
  system falls back to when an exchange identifier is missing or
  unknown — are centralised here.
* Time-based constants are in seconds (with ``_MS`` / ``_MIN`` suffix
  where the unit is non-obvious).
* Money-related constants are :class:`decimal.Decimal`, never ``float``.

Anything added to this file MUST also be added to the
``test_constants_uniqueness`` AST test so future drift is caught at PR
time.
"""
from __future__ import annotations

# Re-export all constants from the constants/ package for backward compatibility
from brokers.common.core.constants import *  # noqa: F401, F403
from brokers.common.core.constants import __all__  # noqa: F401
