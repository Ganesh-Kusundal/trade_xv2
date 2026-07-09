"""Tests for UpstoxDataAdapter — skipped after adapter module deletion.

The ``brokers.upstox.adapter`` module (UpstoxDataAdapter) was deleted during
the broker consolidation phase. These tests will be rewritten when the
structural typing migration is complete and the upstox gateway is validated
against the ``BrokerAdapter`` protocol directly.
"""

from __future__ import annotations

import pytest

pytest.skip(
    "UpstoxDataAdapter was deleted; tests need rewriting against BrokerAdapter protocol",
    allow_module_level=True,
)
