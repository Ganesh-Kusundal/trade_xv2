"""Paper market-coverage contract — offline structural walk via market_surfaces."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.common.contracts.market_coverage_contract import MarketCoverageContract
from brokers.providers.paper.paper_gateway import PaperGateway


@pytest.fixture()
def capabilities():
    return PaperGateway(initial_capital=Decimal("100000")).capabilities()


@pytest.fixture()
def live_gateway():
    pytest.skip("paper has no live gateway walk")


class TestPaperMarketCoverage(MarketCoverageContract):
    pass
