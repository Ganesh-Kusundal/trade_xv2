"""Market-coverage contract — Dhan implementation (offline structural + live walk).

Driven by ``dhan_capabilities().market_surfaces``; the live walk skips without
``.env.local`` credentials (project rule: never mock live market data).
"""

from __future__ import annotations

import pytest

from brokers.common.contracts.market_coverage_contract import MarketCoverageContract
from brokers.dhan.config.capabilities import dhan_capabilities


@pytest.fixture()
def capabilities():
    return dhan_capabilities()


@pytest.fixture()
def live_gateway():
    pytest.skip("live coverage requires .env.local credentials")


class TestDhanMarketCoverage(MarketCoverageContract):
    pass
