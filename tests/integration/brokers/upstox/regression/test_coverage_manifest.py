"""CI gate: every Upstox P0 capability has a registered regression case."""

from __future__ import annotations

import pytest

from tests.integration.brokers.upstox.regression.manifest import (
    MARKET_HOURS_CASES,
    OFF_MARKET_CASES,
    UPSTOX_REGRESSION_CASES,
)
from tests.support.brokers.regression_manifest import manifest_ids, required_p0_capabilities


@pytest.mark.architecture
def test_upstox_regression_manifest_has_unique_ids() -> None:
    ids = manifest_ids(UPSTOX_REGRESSION_CASES)
    assert len(ids) == len(UPSTOX_REGRESSION_CASES)


@pytest.mark.architecture
def test_upstox_market_hours_cases_non_empty() -> None:
    assert len(MARKET_HOURS_CASES) > 0, "MARKET_HOURS_CASES is empty"


@pytest.mark.architecture
def test_upstox_off_market_cases_non_empty() -> None:
    assert len(OFF_MARKET_CASES) > 0, "OFF_MARKET_CASES is empty"


@pytest.mark.architecture
def test_upstox_p0_capabilities_registered() -> None:
    required = {
        "quote",
        "ltp",
        "historical",
        "funds",
        "positions",
        "holdings",
        "orderbook",
        "search",
        "depth",
        "option_chain",
    }
    covered = required_p0_capabilities(UPSTOX_REGRESSION_CASES)
    missing = required - covered
    assert not missing, f"Missing Upstox P0 regression coverage: {missing}"


@pytest.mark.architecture
def test_upstox_manifest_tier_values_valid() -> None:
    valid = {"off_market_safe", "market_hours", "pre_prod", "sandbox"}
    for case in UPSTOX_REGRESSION_CASES:
        assert case.tier in valid, f"{case.id} has invalid tier {case.tier}"
