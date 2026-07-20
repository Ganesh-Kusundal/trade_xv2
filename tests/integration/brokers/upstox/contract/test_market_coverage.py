"""Market-coverage contract — Upstox implementation (offline structural + live walk).

Driven by ``upstox_capabilities().market_surfaces``; the live walk skips without
``.env.local`` credentials (project rule: never mock live market data).
"""

from __future__ import annotations

import pytest

from brokers.common.contracts.market_coverage_contract import MarketCoverageContract
from brokers.upstox.capabilities.snapshot import upstox_capabilities


@pytest.fixture()
def capabilities():
    return upstox_capabilities()


class TestUpstoxMarketCoverage(MarketCoverageContract):
    pass
